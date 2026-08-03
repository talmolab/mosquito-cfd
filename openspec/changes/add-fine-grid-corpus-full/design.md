# Design: full 27-config fine-grid corpus scaffolding

Condensed decision log, mirroring `add-fine-grid-training-pilot`'s own `design.md` format. This
proposal is scaffolding only — the actual cluster submission is a separate, later, explicitly
confirmed step (see `proposal.md` Non-goals).

## D1 — Reuse `generate_sweep()` unmodified, with no `configs=`/`n_holdout=` override

The pilot's `generate_pilot.py` had to pass `configs=PILOT_CONFIGS, n_holdout=0` because 3
configs can't support the default `N_HOLDOUT=6` (not enough non-corner points). The full corpus
has no such constraint: `configs=None` defaults to `build_kinematic_grid()`'s full 27-point
Aedes grid (`AEDES_STROKE_AMP_DEG × AEDES_FREQUENCY_FSTAR × AEDES_PITCH_AMP_DEG` =
3×3×3=27), and `n_holdout=6` (`N_HOLDOUT`'s own default) is valid against 27 configs — this is
exactly the same grid/holdout combination `examples/prelim_sweep/`'s frozen coarse corpus already
uses, just against a different base deck. `generate_full_corpus.py` therefore calls
`generate_sweep(BASE_INPUTS, args.output, timestamp=args.timestamp)` with no other keyword
arguments — zero code changes to `sweep.py`, and no new selection logic to test beyond "the
defaults are used."

## D2 — New output directory, existing base deck; never touch the coarse corpus or the pilot

`examples/prelim_sweep_fine/` is a new sibling directory — never
`examples/prelim_sweep/` (frozen coarse corpus) or `examples/prelim_sweep_fine_pilot/` (pilot,
already committed). Unlike the pilot, this change does **not** introduce a new base deck:
`BASE_INPUTS` points directly at the pilot's already-committed, already-deck-invariance-tested
`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` — reused as-is, not copied. This avoids a
second deck-invariance test entirely (that guarantee is already established and tested for the
pilot's base deck); the isolation guard this change needs is purely a directory-identity check
(`_validate_output_dir`), same mechanism as the pilot's, extended to reject both the coarse
corpus's path and the pilot's own path.

## D3 — Commit the generated decks/manifest now; CFD outputs later

Checked `git ls-files examples/prelim_sweep_fine_pilot/` before assuming anything: the pilot
committed its 3 decks, `sweep_manifest.json`, `sweep_manifest.units.json`, and
`sweep_provenance.json` directly — only `runs/` (the heavy per-config CFD output directory) is
gitignored, via a pattern already generalized to `examples/prelim_sweep*/runs/`
(`automate-run-metadata-capture` D6). So this proposal's own deliverable is not just the script —
it's the script **and** its committed 27-deck/manifest output, exactly mirroring the pilot's
Phase 1. `examples/prelim_sweep_fine/runs/` needs no new `.gitignore` entry; it's already covered.

## D4 — `submit_workflow.sh --parallelism`: sed-patch a temp copy ONLY when passed; true no-op otherwise

`argo submit --help` (checked directly on the cluster CLI) has no flag that overrides
`spec.parallelism` — it is a hardcoded `int` field with no `{{...}}` templating support (already
documented in a comment in `force-surrogate-sweep.yaml`). The alternative — hand-editing
`parallelism: 3` to `1` in the committed workflow file before submitting and reverting afterward
— is exactly the kind of manual, easy-to-forget step this proposal exists to avoid.

**Revised after review**: an earlier draft of this section had the flag default to `3` and always
sed-patch, meaning the shell script would carry its own hardcoded copy of "3" independent of
`force-surrogate-sweep.yaml`'s actual committed value — a second source of truth that could
silently drift (e.g. an operator bumps the YAML's `parallelism` for an unrelated reason, and every
plain `full` invocation thereafter silently reverts it via the script's stale default). Fixed: the
flag has **no default value at all**. When `--parallelism` is *omitted*, `full` passes `$WORKFLOW`
straight through unpatched, exactly as it does today — the committed YAML remains the single
source of truth. Only when `--parallelism N` is *explicitly passed* does the script sed-patch a
temp copy:

```bash
PARALLELISM=""   # empty = flag not given = pass $WORKFLOW through unpatched
...
--parallelism) PARALLELISM="$2"; shift 2;;
...
full)
  require_image
  workflow_file="$WORKFLOW"
  if [[ -n "$PARALLELISM" ]]; then
    [[ "$PARALLELISM" =~ ^[1-9][0-9]*$ ]] || die "--parallelism must be a positive integer (got: $PARALLELISM)"
    # `|| true` is required: under this script's `set -euo pipefail`, a plain assignment from a
    # command that exits non-zero (grep -c on ZERO matches exits 1) is NOT exempt from errexit —
    # verified directly: without `|| true`, the zero-match case kills the script right here with a
    # bare exit 1, never reaching the die() message below, silently defeating the "fails loudly"
    # guarantee this check exists to provide.
    n_matches=$(grep -c '^  parallelism: [0-9]\+$' "$WORKFLOW" || true)
    [[ "$n_matches" -eq 1 ]] || die "expected exactly one top-level 'parallelism:' line in $WORKFLOW, found $n_matches"
    tmp="$(mktemp --suffix=.yaml)"
    trap 'rm -f "$tmp"' EXIT
    sed -E "s/^(  parallelism: )[0-9]+\$/\1${PARALLELISM}/" "$WORKFLOW" > "$tmp"
    grep -q "^  parallelism: ${PARALLELISM}\$" "$tmp" || die "parallelism patch did not apply as expected"
    workflow_file="$tmp"
  fi
  argo submit "$workflow_file" -n "$NAMESPACE" --watch \
    --parameter image="$IMAGE" ...   # unchanged, same --parameter list as today
```

**Testability seam**: `$WORKFLOW` is currently assigned unconditionally
(`WORKFLOW="$(cd "$SCRIPT_DIR/../workflows" && pwd)/force-surrogate-sweep.yaml"`), so a test cannot
point the script at a mangled copy to exercise the "reformatted `parallelism:` line" `die` path
(spec.md's "A failed substitution is never silently submitted" scenario). Fix: change the
assignment to respect a pre-set environment variable, matching the script's own existing
`"${VAR:-default}"` idiom already used for `NAMESPACE`/`IMAGE`/etc.:
`WORKFLOW="${WORKFLOW:-$(cd "$SCRIPT_DIR/../workflows" && pwd)/force-surrogate-sweep.yaml}"`.
Normal invocations are unaffected (no one currently sets a `WORKFLOW` env var); a test can set
`WORKFLOW=/tmp/mangled-copy.yaml` before invoking the script to exercise the `die` path without
ever touching the real committed file.

Key properties, each directly answering a review finding:
- **Anchored, self-verifying substitution** (not a bare unanchored `sed`): the pattern is anchored
  to the known 2-space top-level indent (so a future nested/task-level `parallelism` field, if one
  is ever added, is not accidentally matched too), pre-checked for exactly one match, and
  post-checked that the substitution actually landed — a future reformat of that line fails loudly
  (`die`) rather than silently submitting the unpatched default.
- **Input validation**: a non-positive or non-integer `--parallelism` (`0`, `-1`, `abc`) is
  rejected by regex before any file is touched or `argo submit` is called.
- **Temp-file cleanup**: `trap 'rm -f "$tmp"' EXIT` — no leaked files in `/tmp`/WSL's temp dir.
  `mktemp` itself is collision-free across concurrent operators (kernel-atomic unique naming), so
  no separate collision-handling is needed beyond the trap.
- **Positional argument, matching the script's existing convention**: `argo submit
  "$workflow_file" ...` — not `-f <path>` (an earlier draft of this section incorrectly said `-f`;
  the script already passes `$WORKFLOW` positionally today, and the patched call preserves that
  exact style, just substituting the resolved `workflow_file` variable).
- **Usage header is updated, not just "confirmed"**: task 3.2 edits the header comment block
  (`submit_workflow.sh` lines 2-18, printed by the `help` command) to document `--parallelism`
  under the `full` command's description. Since `help` prints a hardcoded `sed -n '2,22p'` range,
  adding a header line means re-checking (and bumping if needed) that range so `help` doesn't
  truncate the new documentation or spill further into the executable code below it (lines 19-22
  already bleed into `help` output today — pre-existing, not introduced by this change, but a
  reason to re-verify the exact bound rather than assume it still fits).

This proposal's own planned future use is `--parallelism 1` (serial) for the eventual live
submission, decided independently of this change (quota pressure + unverified preemption/retry
path — see `proposal.md` `## Why`), not something this change itself needs to choose.

## D5 — CFL fallback for the 18 untested configs stays fully manual (no new tooling)

The pilot only stress-tested pitch=45° (3 of 27 kinematic points); pitch=30°/60° (18 configs)
have never run at fine resolution. There is currently **no automated divergence-detection or
dt-fallback mechanism anywhere in the codebase** (confirmed: `check_completion()` only checks row
count against `max_step`, with no CFL/NaN-specific logic; a repo-wide grep for `CFL`/`2.5e-4`
found zero code hits — the fallback exists only as operator prose in the pilot's own `design.md`
D6). Decision: do not build fallback tooling in this proposal. If/when a config actually diverges
during the future live run, the exact same manual runbook the pilot's D6 already specifies
applies:

1. Hand-maintain a second base deck (e.g. `base_inputs.3d.fine_dt2` or an in-place documented
   override) with `ns.fixed_dt = 0.00025` — `render_inputs()` never touches `ns.fixed_dt`, so this
   is unavoidably a base-deck-level change, not a per-config manifest field.
2. Regenerate just that one config's deck: `generate_sweep(base_inputs_path=<the dt=2.5e-4 base
   deck>, output_dir=..., configs=[that_one_config], dt=2.5e-4)` — `dt` recomputes `max_step`/
   `stop_time` consistently (doubling `max_step`, per the pilot's own precedent).
3. Re-submit only that config through `force-surrogate-single-config` (not the whole 27-config
   fan-out), same as the pilot's `smoke` pattern.

This is deliberately unautomated: the pilot's own evidence is that 0 of 3 tested configs needed
it, so building a general-purpose fallback mechanism now would be speculative complexity for a
path that may see zero, one, or a handful of the 18 untested configs need it — and even then, a
handful of one-off manual re-submissions is far cheaper than a new code path with its own tests
and failure modes.

## D6 — Test design (mirrors the pilot's `tests/test_fine_pilot_deck.py`)

- **Config-count and grid-default scenario**: `generate_full_corpus.py`'s call produces exactly
  27 configs matching `build_kinematic_grid()`'s output, and `manifest["holdout"]["n_holdout"] ==
  6` with a non-empty `config_names` list (unlike the pilot's forced `n_holdout=0` — this is the
  one behavioral difference from the pilot's own test suite worth a dedicated assertion).
- **Byte-reproducibility**: two `tmp_path` calls to `generate_sweep()` with identical arguments
  produce byte-identical decks and manifest — same pattern as the pilot and the original coarse
  corpus.
- **Isolation guard**: `_validate_output_dir` unit test (rejects the coarse corpus's path AND the
  pilot's own path, named explicitly — not "constants" ambiguously) plus a monkeypatched-constant
  CLI-wiring test (same shape as the pilot's
  `test_generate_pilot_main_rejects_frozen_corpus_output_via_cli`), and a static check that
  `OUTPUT_DIR`/`WORKSPACE_HOSTPATH` differ from both the coarse corpus's and the pilot's.
- **`submit_workflow.sh --parallelism`** (revised after review — committing to one concrete,
  CI-feasible approach rather than the two disjoint options an earlier draft floated): a
  `subprocess`-based Python test that puts a stub executable named `argo` ahead of the real one on
  `PATH`. The real invocation shape is `argo submit "$workflow_file" -n "$NAMESPACE" --watch
  --parameter ... [more --parameter pairs]` (`submit_workflow.sh`'s existing `full`/`smoke` cases)
  — the workflow-file path is always the **second** token (`$2`, right after the literal
  `submit`), never the last argument (an earlier draft of this sketch tried to grab "the last
  argument," which is actually `--parameter pod-memory-request=...`'s value — wrong, and using
  invalid `${$#}` syntax besides). The stub must capture `$2` specifically, and must not attempt to
  replicate real `argo submit --watch`'s blocking behavior, or the test would hang:
  ```sh
  #!/bin/sh
  # argv: submit <workflow-file> -n <namespace> --watch --parameter ...
  cp "$2" "$CAPTURE_FILE"
  exit 0
  ```
  The test:
  1. Invokes `submit_workflow.sh full --image
     ghcr.io/x@sha256:$(python -c "print('a'*64)") --parallelism 1` with the stub's directory
     prepended to `PATH` (satisfying `require_image`'s precondition with a fake but well-formed
     digest, since `full` calls `require_image` before ever reaching the sed/argo step).
  2. Asserts the captured file the stub received contains `parallelism: 1`.
  3. Repeats with `--parallelism` omitted; asserts the captured file is byte-identical to
     `cluster/argo/workflows/force-surrogate-sweep.yaml` itself (no temp file involved at all —
     this is the assertion that actually distinguishes "true no-op" from "hardcoded-default
     re-patch," per D4's revision).
  4. Asserts `cluster/argo/workflows/force-surrogate-sweep.yaml`'s `sha256` on disk is identical
     before and after both invocations.
  5. Asserts `--parallelism 0`, `--parallelism -1`, and `--parallelism abc` all fail fast (nonzero
     exit, clear message) with no temp file created and no stub invocation at all (assert via a
     stub-invocation marker file that doesn't get created).
  6. Sets the `WORKFLOW` env var (per D4's new testability seam) to a `tmp_path` copy of the real
     workflow file with its `parallelism:` line deleted, invokes `full --parallelism 1` against
     it, and asserts a non-zero exit with a clear "expected exactly one" message — exercising the
     0-match `die` path (spec.md's "A failed substitution is never silently submitted" scenario),
     which is otherwise untested since the real committed file always has exactly one match.
  This avoids the `argo lint`-stubbing question entirely: `full` never calls `argo lint` (only the
  separate `lint` command does), so the stub only needs to intercept `argo submit`.

## D7 — Documentation this change must actually touch (found by review, not in the original scope draft)

Three doc-drift risks a review caught, each with a precedent this proposal should follow rather
than skip:

- **`.github/workflows/ci.yml`'s lint job hardcodes explicit paths**, not a repo-wide glob: `uv
  run ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/`
  (and the matching `ruff format --check` line) — the file's own comment warns a new example
  directory must be added to both lines. Without adding `examples/prelim_sweep_fine/` here,
  `generate_full_corpus.py` would never be linted in CI even though a local, unscoped `uv run ruff
  check .` (task 5.1) would pass — a false-green gap. Task 3.4 adds it.
- **`openspec/project.md`'s "Current State" section** — both directly-preceding related changes
  (`add-fine-grid-training-pilot`, `automate-run-metadata-capture`) added a bullet here when they
  landed; this change should too (a committed-corpus bullet under "Implemented", a
  deferred-live-run bullet under "Pending" — the ~2.55-day cluster action currently has no record
  outside a closed OpenSpec change's `proposal.md`, which is exactly the "docs belong in
  `project.md`" pattern this repo already established). Task 4.3 adds it.
- **`submit_workflow.sh`'s usage header** — covered under D4 above; task 3.2 edits it directly
  rather than task 3.3 treating it as pre-existing to "confirm."

`cluster/argo/README.md` mentioning the new flag would be nice but is lower-priority operator
documentation, not spec-load-bearing; left as a follow-up rather than a task here.

## Open questions — resolved

- **Output directory / tier label**: `examples/prelim_sweep_fine/` / `fine-grid-corpus-full` —
  both already appear in `scripts/generate_run_metadata.py`'s own docstring example, written
  ahead of this proposal specifically to anticipate it. Keeping that consistency rather than
  choosing new names.
- **fp64 image digest**: `sha256:df5ec74805be63bc9dbdf854d205bcfc6ad7e07b87e092e0162a6818020e007d`
  as of 2026-08-03 (post `automate-run-metadata-capture` merge) — this proposal makes no code
  changes that would trigger a new image build, but the digest **will** change again once this
  proposal's own PR merges (every push to `main` rebuilds `:fp64`). Whoever submits the future
  live run must re-verify the digest at submission time via the `docker.yml` "Emit FP64 image
  digest to job summary" step on the latest successful main-branch build — never reuse a
  memorized value.
