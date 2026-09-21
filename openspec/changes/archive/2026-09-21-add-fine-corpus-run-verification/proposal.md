# Make the fine-grid corpus run verifiable

## Why

The completed 27-config fine-grid cluster run (PR #91) is not publication-grade: 15 of 27 configs
were CFL-limited and 9 stopped mid-wingbeat, because `max_step` assumes the nominal `dt` while
`ns.cfl` silently reduces the realized step at 256³ (#92). The metadata schema cannot detect this and
asserts `stable_at_5e-4` regardless (#93), and the extractor double-counts `ns.init_iter`
initialization rows, corrupting row counts and `time` ordering for every config (#94). Every existing
check passed, because the pipeline validates internal consistency only — never a run against its
manifest or a physical invariant (#20). This change adds that external verification, removes the
root cause by raising `ns.cfl` so the validated timestep binds, and fixes two compounding Argo
orchestration gaps (#95, #90) before the corpus can merge.

## What Changes

### Root cause: let the validated timestep bind (#92)

- **ADD** `ns.cfl` as an optional per-config targeted rewrite key in the deck generator, with the
  same pass-through-by-default semantics `ns.init_iter` already has, so corpora that don't opt in
  regenerate byte-identically.
- Generate the fine corpus with `ns.cfl = 0.6`. The worst config requires 0.490; 0.6 leaves 22%
  margin where 0.5 would leave 2%.
- Threading it through the generator, rather than editing the base deck, preserves the requirement
  that the fine base deck differ from the frozen coarse base deck in `amr.n_cell` only.

This returns all 27 configs to the **validated** `dt = 5e-4` that the other 12 and the entire van
Veen validation chain already used — the CFL limiter had been pushing 15 of them *below* it. It also
makes the corpus uniform: same dt, same `rows == max_step`, same `cycles_completed` everywhere.

### Run-observed metadata (#93)

- **ADD** observation fields derived from the run's own output: `realized_dt` (`min`, `mean`, `max`,
  `frac_below_nominal`), `interior_dt_below_nominal`, `cycles_completed`, `reached_stop_time`.
- **MODIFY** `stability` to reflect observed behaviour, adding `cfl_limited_at_*` values.
- **ADD** an auditable record for every mandatory runbook gate in `sweep_provenance.cluster_run`,
  including the CC-F1 outcome, the value it gated on, the submitted `parallelism`, and the effective
  `activeDeadlineSeconds`.

`realized_dt` is read from `run.log`'s per-step `DT` at full precision, **not** by differencing the
force CSV: the CSV writes `time` at six significant figures, which quantizes a differenced timestep
to ~±2% of nominal and yields values above the `ns.fixed_dt` ceiling the solver cannot have taken.
It is summarized by `min` and `frac_below_nominal`, never the median — the median is provably blind
here (see `design.md` D3).

### Extractor (#94)

- **MODIFY** `_extract_config` to deduplicate on `iStep` with `keep="last"`, restoring
  `len(df) == max_step`. `keep="last"` is required: the first `t=0` row is all-zero forces.
- Provably a **no-op** on the coarse corpus (`init_iter = None`, zero duplicates) — asserted, not
  assumed, so the frozen-corpus guarantee holds.

### Orchestration (#95, #90)

- **MODIFY** the committed `activeDeadlineSeconds` in both workflows (the smoke copy is unpatchable
  by any flag), sized to cover the auto-scale formula *and* two preemption retries of the longest
  config — because fixing #90 is what makes retries actually fire.
- **MODIFY** `retryStrategy.retryPolicy` to `"Always"`, the only value covering both application
  failure and pod deletion.
- Re-derive `PER_CONFIG_HOURS`, whose comment still cites the superseded `vb8t5` run.

### Verification (#20 + acceptance gate)

- **ADD** cluster-free guard tests over an explicit **registry** of committed corpora, reconciling
  each artifact against its manifest and against physical invariants rather than against itself.
- **ADD** a post-run acceptance gate that runs after metadata generation and before
  `extract_forces.py`, so a defective run cannot reach a committed parquet. Its physical check is a
  **normalized** symmetry ratio (~150× separation), not an absolute mean (~1.3×). An absent gate
  result is a hard failure.

## Impact

**BREAKING** — three committed contracts change; each has a named downstream consumer, updated in
the same change:

- `dataset.parquet` row count per configuration drops by `init_iter` for field-capture corpora.
- `timing.timesteps` changes from the raw CSV row count to the distinct-timestep count.
- `stability` gains `cfl_limited_at_*` values that deliberately do not match a `stable_at_` prefix,
  so `/submit-cluster-sweep` Step 4 and `openspec/project.md`'s duplicate of that check fail closed
  until updated.

- **Affected specs:** `force-surrogate` (run duration, targeted keys, manifest schema, dataset
  extraction, Argo orchestration, retryStrategy, plus three new requirements), `run-metadata`
  (observed fields, `stability`, row-count cross-check).
- **Affected code:** `force_surrogate/sweep.py`, `force_surrogate/dataset.py`,
  `force_surrogate/metadata_capture.py`, `examples/prelim_sweep_fine/generate_full_corpus.py`,
  `cluster/argo/workflows/*.yaml`, `cluster/argo/workflow-templates/*.yaml`,
  `cluster/argo/scripts/submit_workflow.sh`.
- **New files:** an acceptance-gate module plus a thin CLI driver under `scripts/`, a corpus-guard
  test module, a corpus registry, a minimal synthetic 2-config corpus fixture for the gate tests,
  new force CSVs, `run.log` samples and pod-side metadata fixtures, and
  `examples/prelim_sweep_fine/README.md`.
- **Affected docs:** `.claude/commands/submit-cluster-sweep.md` (Step 4, a new acceptance step, and a
  pilot-invalidation trigger), `openspec/project.md` (its duplicate of the now-vacuous Step 4 check,
  plus reconciling its existing "CFL at fine 256³ grid" note with the corrected `fixed_dt`/`ns.cfl`
  mechanism, the local stability-probe recipe, and the external-reconciliation principle),
  `docs/CHANGELOG.md`, `examples/prelim_sweep/README.md` (its unscoped whole-wingbeat guarantee),
  `docs/force_surrogate/fine-grid-pilot-report.md` (an erratum confirming its existing forward-looking
  caveat — not adding a missing one), `docs/field_surrogate/roadmap.md` (CC-F3's dependence on the
  corrected run), `tests/fixtures/run_metadata/README.md` (its fixture-coupling documentation).
- **Prevention:** the change repoints the **smoke pre-flight at the CFL-worst configuration** rather
  than the first one in the grid. It currently defaults to `s35_f085_p30` — the mildest config in the
  sweep — so the step that exists to catch problems before the 27-way fan-out is aimed at the one
  configuration that structurally cannot reveal this class. Pointed at the worst case, it would have
  caught #92 for ~2.4 GPU-h instead of ~65. The accompanying documentation tasks move the lessons out
  of this change's `design.md`, which is archived on merge — precisely how the original error
  propagated: the false claim that `ns.fixed_dt` overrides `ns.cfl` has sat in an archived design
  document since August.
- **Not affected:** the coarse corpus `examples/prelim_sweep/` stays byte-identical — opt-in
  defaults plus a no-op dedup, both asserted. FP64 throughout; no Docker, CI or dependency changes.
- **Sequencing:** lands on `main` first with no corpus. PR #91 is held open; after this merges, one
  full config is re-run and gated as a mandatory stability precondition (design D4), then the
  remaining 26 configs are re-run, metadata regenerated, the parquet rebuilt, and #91 updated and
  merged last. `main` never contains a knowingly-defective corpus.
- **Closes:** #92, #93, #94, #95, #90, #20.
