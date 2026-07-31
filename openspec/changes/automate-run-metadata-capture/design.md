# Design: automate run-metadata capture

**Revision note (post-review):** a 5-agent `/review-openspec` found the original draft's D2
evidence table was factually backwards (both existing lineages actually share the schema this
proposal fixes, not two genuinely different shapes), that normalizing the schema conflicts with a
**live** `force-surrogate` spec requirement pinning the 3 committed pilot files to
`run_metadata_t3c.json`'s schema, that the module-location question (task 1.3's `scripts/` vs
`src/` hedge) needs resolving now, and that the proposal's "gitignored" premise for pod-side
artifacts doesn't hold for the pilot tier's NFS tree. All fixed below (D2, D4, D5, D6). The
"decide during implementation" framing for regenerating the 3 pilot files is also gone — that's
now a hard non-goal (D4), not an open question.

## D1 — Post-run CLI, not pod instrumentation

Two real options were considered for where the automated generator plugs in:

1. **Post-run CLI** (chosen): reads already-existing artifacts (the pod's own gitignored-once-D6-
   lands `run_metadata.json`, the committed force CSV, `run.log`, the sweep manifest/deck) plus
   one read-only Argo workflow-status query for wall-clock timing. Touches no cluster-execution
   code.
2. **Instrument `run_one_config.py`**: add a wall-clock timer around the `mpi_runner` call and a
   `--workflow-name` CLI arg, so the pod's own `run_metadata.json` is already schema-complete and
   just needs copying/renaming to commit.

Chosen (1) because it keeps this change fully cluster-execution-code-free and unit-testable
without any live cluster access — the pod's runtime behavior (and the Argo WorkflowTemplate that
drives 27 real GPU jobs in the follow-on) stays untouched and unproven-code-free.

**Argo workflow garbage-collection risk (added post-review):** the completed-workflow status
query this tool depends on reads a **decaying** resource — Argo installations commonly garbage-
collect completed `Workflow` objects after a retention window, and no `ttlStrategy` is configured
in this repo's templates one way or the other. Unlike the NFS `runs/` cleanup risk (D4/the old
task 8, now deferred), this asymmetry wasn't previously documented. Mitigation: the CLI accepts an
optional `--wall-time-s` manual override so an operator who already has the number (e.g. from a
submission-time note or a monitoring session that happened before GC) can supply it directly
instead of the tool hard-failing; the CLI's `--help` and the script's module docstring state
plainly that `generate_run_metadata.py` must be run **before** the source workflow is
garbage-collected, or with `--wall-time-s` supplied manually. No `ttlStrategy`/retention window is
actually configured anywhere in this repo's Argo templates today (confirmed by grep), so this is a
documented, plausible-but-unconfirmed risk, not an observed failure — the override exists as a
rare-case fallback, not the expected path; operators should still run this tool promptly after a
config completes rather than relying on the override as routine practice.

**Operator-only scope (added post-review):** this tool is explicitly never invoked from CI (CI's
`ubuntu-latest` runner has no `argo`/cluster access, matching the rest of this repo's cluster-
facing scripts). The script's module docstring states this explicitly so a future contributor
doesn't wire it into `ci.yml` by analogy with the lint/test jobs.

## D2 — Schema normalization, not backward compatibility

**Corrected (the original draft table was wrong here — verified against the actual committed
files, not just against what the code's `capture_surrogate_run_metadata` function does):**

| | t3c/t3b/t2a (`examples/flapping_wing/`) | pilot (`examples/prelim_sweep_fine_pilot/`) |
|---|---|---|
| Docker identity | `docker_image` (tag) + `image_digest` (separate key) | **same split** — `docker_image` (tag) + `image_digest` (separate key) |
| Provenance narrative | `image_tag`, `image_build`, `iamrex_commit` (free text) | none |
| Run context | `run_platform` (free-text narrative), `analysis_host` | `run_platform` (free-text narrative), `kinematics`, `orchestration`, `tier` |

Both committed lineages actually use the **same** tag+separate-digest split — this is not a
cross-lineage inconsistency, it's a **schema-vs-code mismatch**: the code that actually validates
image identity (`capture_surrogate_run_metadata` / `sidecar.validate_image_digest`) stores a
single validated `sha256:...` digest under the key `docker_image`, but every hand-assembled
committed file instead puts a mutable *tag* under `docker_image` and the real digest under a
separate `image_digest` key. That's the actual bug being fixed: the hand-authoring process
silently diverged from what the automation would have produced. Chosen: **normalize** to one
clean, fully-structured schema — a single digest-validated `docker_image` field, matching the
code — for all **future** runs (fixing the mismatch by construction) rather than preserving either
lineage's shape.

The free-text `run_platform` narrative is replaced with structured, independently-derived fields:
- `stability`: `"stable_at_<fixed_dt>"`, derived **purely from `fixed_dt` itself** — no separate
  hand-set `dt_reduced` flag is read or trusted. Concretely: the sweep's nominal `fixed_dt` is
  `5e-4` (a known constant from `sweep.py`); if a config's manifest-sourced `fixed_dt` differs from
  that nominal value, `stability` records that the CFL fallback was used, formatted generically as
  `"stable_at_{fixed_dt}_fallback"` (e.g. `"stable_at_2.5e-4_fallback"` for the one fallback value
  seen to date — the format generalizes to any future fallback value, not just this one),
  otherwise `"stable_at_5e-4"`. This was flagged in review as the one field whose derivation the
  original draft left vague ("may depend on a previously hand-set flag") — fixed by deriving it
  from a value (`fixed_dt`) this tool already sources mechanically (D3), not from any separate
  boolean.
- `arena_max_mib`: parsed from the AMReX end-of-run "The Arena" line in `run.log`.
- `node`, `gpu_model`: from the pod's own `run_metadata.json` (`orchestration.node`) and hardware
  probe respectively.

One optional `notes` field remains for genuinely exceptional human commentary (e.g. explaining an
unusual truncated final step, as seen in `s35_f085_p45`'s benign last-step DT truncation) — it
must be omittable and is never required for a normal run.

## D3 — Sourcing kinematics/grid/fixed_dt from the manifest, not re-deriving them

`stroke_amp_deg`, `frequency_fstar`, `pitch_amp_deg`, `reynolds`, `amr.n_cell` (grid), and
`fixed_dt` are already present, per-config, in the committed `sweep_manifest.json` (or readable
directly from the generated deck file). The generator reads them from there rather than requiring
them as CLI arguments or re-deriving them from the CSV. `stability` (D2) is derived from the same
sourced `fixed_dt` value, not a separate input.

## D4 — The 3 committed pilot files are NOT touched by this change (hard non-goal, not deferred)

**Corrected (this was "decide during implementation" in the original draft — review found that
framing unsafe):** `openspec/specs/force-surrogate/spec.md`'s requirement "Fine-grid pilot
per-config run metadata is committed with provenance" **normatively pins** the 3 committed
`run_metadata_<config>.json` files to "the same schema as `run_metadata_t3c.json`" — i.e. the
exact split-field schema D2 is normalizing away. Regenerating those 3 files under the new schema
in this change would silently violate a live, already-archived spec requirement, and would also
break `tests/test_fine_pilot_deck.py::test_pilot_run_metadata_schema` (`_REQUIRED_METADATA_FIELDS`
hard-requires both `docker_image` and `image_digest`). Both the documentation and git-workflow
reviewers independently flagged the same underlying risk: these 3 files were the sole subject of
PR #58's dedicated 5-agent review (which caught the `final_time`/truncated-SHA bugs in all 3), and
silently re-touching them as a buried sub-step of an unrelated "new tool" PR reintroduces exactly
the failure mode this change exists to prevent — a value change nobody explicitly re-diffs.

**Decision:** this change does not read, run against, or modify the 3 committed pilot files as a
deliverable. It only produces schema-normalized output for the **new, not-yet-generated** files
the full 27-config corpus follow-on will create. If a future change wants to regenerate the 3
pilot files through this tool for real-world round-trip validation, that change must (a) add a
`MODIFIED Requirements` delta to `force-surrogate/spec.md` retiring or updating the "same schema
as `run_metadata_t3c.json`" clause, and (b) update `test_pilot_run_metadata_schema`'s
`_REQUIRED_METADATA_FIELDS` accordingly — as its own explicit, reviewable change, not a side
effect of this one.

The TDD oracle (fixture-driven reproduction of one pilot config's already-known-correct values,
per the "generator is testable without live cluster or Argo access" requirement / task 7.4) still
uses the 3 pilot files as **read-only ground truth data** for
test fixtures — that's reading committed test data, not modifying the files themselves, and
doesn't touch the spec requirement above.

## D5 — Module location: logic in `src/`, thin CLI in `scripts/`

**New (review found the original tasks.md left this open, making the Impact section incomplete):**
the actual parsing/validation/assembly logic (CSV last-row reader, `run.log` parser, manifest
sourcing, digest/git validation, Argo status wrapper, schema assembler) lives in a new module,
`src/mosquito_cfd/force_surrogate/metadata_capture.py` — importable and unit-testable, and able to
`import` `sidecar.validate_image_digest` directly rather than duplicating its regex.
`scripts/generate_run_metadata.py` is a thin argparse CLI wrapper over that module, matching the
existing convention of `scripts/run_sweep.py`/`extract_forces.py`/`train_surrogate.py` (bare
scripts, no `[project.scripts]` entry — confirmed consistent with this repo's pattern; only
`generate-wing-planform` has a console-script entry, for a different reason: it's a general-purpose
package CLI, not a one-off cluster-adjacent driver).

## D6 — `.gitignore` gap: the pilot tier's `runs/` tree isn't actually excluded

**New (review caught this contradicting the proposal's stated premise):** `.gitignore` only
excludes `examples/prelim_sweep/runs/` (the frozen coarse corpus's tier). It does **not** exclude
`examples/prelim_sweep_fine_pilot/runs/` — verified via `git check-ignore -v`, no match — nor will
it exclude the upcoming full-corpus follow-on's own `runs/` tree (`examples/prelim_sweep_fine/` or
similar). This change's core premise (pod-side `run_metadata.json`/`run.log` are NFS-only,
uncommitted intermediate artifacts this tool reads as input) silently doesn't hold for the tier it
was designed against. Fix: generalize the pattern to `examples/prelim_sweep*/runs/`, covering the
pilot tier and any future fine-grid-corpus tier, closing a real risk of accidentally committing an
entire per-attempt `runs/` corpus.
