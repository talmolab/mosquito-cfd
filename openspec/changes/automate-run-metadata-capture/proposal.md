## Why

`examples/prelim_sweep_fine_pilot/run_metadata_<config>.json` (3 files, from the just-merged
`add-fine-grid-training-pilot` / PR #58) are hand-assembled after each cluster run, following the
`run_metadata_t3c.json` precedent. PR #58's review caught a `final_time` bug in **all 3** files
(recorded the deck's `stop_time` instead of the force CSV's actual last row — IB-particle CSVs
always end exactly one `dt` short of `stop_time`, a systematic writer convention) and a git-hash
format inconsistency (2 of 3 used a truncated 7-char SHA instead of the full 40-char one). Both
were caught and fixed only because a 5-agent review happened to re-derive every value from the
committed artifacts and compare.

The upcoming full 27-config fine-grid corpus regeneration (a separate, already-scoped follow-on
change) will produce 9x as many of these files. Fixing this class of bug by hand each time doesn't
scale — the same review effort would need to repeat 27 times to catch the same mistakes. A
pod-side automated writer already exists
(`src/mosquito_cfd/force_surrogate/run_one_config.py`'s `_write_run_metadata`, invoked via
`capture_surrogate_run_metadata` on every cluster attempt) but its output is gitignored, missing
a `timing` block entirely, and uses a different schema than what actually gets committed — so a
human re-derives and re-types the committed file from scratch instead of the automation being
trusted as the source of truth.

## What Changes

Add a new post-run CLI (`scripts/generate_run_metadata.py`) that assembles a committed
`run_metadata_<config>.json` entirely from existing artifacts — no field is hand-typed:

- The pod's own already-produced `run_metadata.json` (git commit/branch/dirty, validated docker
  image digest, hardware, `orchestration.{workflow_uid,pod,node,retry}` — all already wired
  in-pod via Argo template vars / the Kubernetes downward API).
- The committed force CSV's actual **last row** for `final_time`/`timesteps` — never the deck's
  `stop_time` (fixes the exact bug the PR #58 review caught 3/3 times).
- `run.log` for the AMReX end-of-run Arena max-used figure.
- The sweep manifest / deck for kinematics (stroke/frequency/pitch/Reynolds), grid, `fixed_dt`,
  `max_step` — sourced, not re-derived or hand-copied.
- One read-only Argo workflow-status query (`argo get <workflow-name> -o json`, works after
  completion) for `wall_time_s`, computed from the workflow's persisted start/finish timestamps.
- A required `--tier` CLI argument (a single known label per invocation, e.g.
  `fine-grid-corpus-full`) — not a re-derivation of run-specific data, so not "hand-authoring" in
  the sense the bugs above were.

The output schema is **normalized**, not backward-compatible with today's two inconsistent
lineages (t3c/t3b/t2a vs. the 3 pilot files): fixes the `docker_image`/`image_digest` field
inversion (the t3c-lineage schema stores a mutable tag under `docker_image` and the digest
separately, while the code that actually validates digests stores the digest under
`docker_image` — schema and code disagree), and replaces the free-text `run_platform` narrative
with structured, independently-derived fields (`stability`, `arena_max_mib`, `node`, `gpu_model`).
One optional `notes` field remains for genuinely exceptional human commentary (e.g. explaining an
unusual truncated final step) but is never required for a normal run.

## Non-goals

- Does not touch `sweep.py`, `generate_sweep()`/`generate_pilot.py` deck generation,
  `cluster/argo/workflow-templates/*.yaml`, or submit any cluster jobs.
- Does not modify `run_one_config.py`'s pod runtime behavior or add any new Argo template
  variables/CLI args to it. A real alternative (instrumenting the pod directly with a wall-clock
  timer and a `--workflow-name` arg) was considered and explicitly declined in favor of the
  post-run CLI, to keep this change fully cluster-execution-code-free and independently testable
  without a live cluster.
- Does not retroactively fix `examples/flapping_wing/run_metadata_{t3c,t3b,t2a}.json` (older
  lineage, different tier, not blocking the upcoming corpus work).
- Does not itself regenerate the full 27-config corpus — that is a separate, already-scoped
  follow-on change that will depend on this one's output schema.

## Impact

- Affected specs: `run-metadata` (new capability — no prior spec file existed).
- Affected code: new `scripts/generate_run_metadata.py` + supporting parsing functions (CSV
  last-row reader, `run.log` Arena-max parser, Argo status-query wrapper, schema assembler). No
  changes to `run_one_config.py`, `sweep.py`, or any Argo template.
- New tests: `tests/test_generate_run_metadata.py`, TDD against fixture data derived from the
  already-committed, already-corrected 3 pilot `run_metadata_*.json` files and their CSVs — no
  live cluster/Argo/RunAI access needed to write or run these tests.
- Whether the 3 already-committed pilot files are regenerated through the new tool (to prove
  real-world round-trip equivalence) is decided during implementation — see `design.md` open
  question.
