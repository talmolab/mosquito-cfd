# Tasks — full 27-config fine-grid corpus scaffolding

TDD throughout: each implementation task names the **test written first** and the behavior it
verifies **before** the code exists. `uv` for all Python. Branch: `add-fine-grid-corpus-full` (off
`main`). Everything in this proposal is **cluster-free** — no GPU time, no live Argo submission.
The actual 27-config cluster run is a separate, later, explicitly-confirmed step, not part of
this task list.

---

## 1. Full-corpus deck-generation script (TDD, cluster-free)

- [ ] 1.1 **Test first (config count and grid defaults):** in a new `tests/test_full_corpus_deck.py`
  add `test_full_corpus_uses_default_27_config_grid`. Call `generate_sweep(BASE_INPUTS, tmp_path,
  timestamp=...)` with no `configs=`/`n_holdout=` override (importing `BASE_INPUTS` from the new
  script) and assert `len(manifest["configs"]) == 27`, the 3 kinematic axes match
  `build_kinematic_grid()`'s own output, `manifest["holdout"]["n_holdout"] == 6`, and
  `manifest["holdout"]["config_names"]` is non-empty (contrasts with the pilot's forced
  `n_holdout=0`). Fails: script/constants don't exist yet.
- [ ] 1.2 **Test first (byte-reproducibility):** add
  `test_full_corpus_decks_are_byte_reproducible_from_generate_sweep(tmp_path)`. Call
  `generate_sweep()` twice into two `tmp_path` dirs with identical arguments; assert byte-identical
  decks and `sweep_manifest.json`. Mirrors the pilot's and the original coarse corpus's existing
  reproducibility guarantee.
- [ ] 1.3 **Test first (isolation guard, unit):** add
  `test_validate_output_dir_rejects_coarse_corpus_and_pilot_dir`. Call the new script's
  `_validate_output_dir` directly against both `examples/prelim_sweep/` and
  `examples/prelim_sweep_fine_pilot/`; assert `pytest.raises(ValueError)` for each. Assert the
  script's own real `OUTPUT_DIR` is **not** rejected.
- [ ] 1.4 **Test first (isolation guard, CLI wiring):** add
  `test_generate_full_corpus_main_rejects_frozen_paths_via_cli(tmp_path, monkeypatch)`.
  Monkeypatch **both** `full_corpus._FROZEN_CORPUS_DIR` (the coarse corpus) and
  `full_corpus._PILOT_DIR` (the pilot directory) to `tmp_path` decoys (two separate patches, two
  separate assertions — not "the script's frozen-path constants" ambiguously), call
  `main(["--output", str(decoy)])` for each decoy in turn, assert `pytest.raises(SystemExit)` for
  both — exercises the full CLI wiring (guard → `parser.error` → `SystemExit`) without ever
  touching the real frozen directories.
- [ ] 1.5 **Test first (static path inequality):** add
  `test_full_corpus_output_dir_and_workspace_differ_from_coarse_and_pilot`. Statically assert the
  script's `OUTPUT_DIR`/`WORKSPACE_HOSTPATH` constants differ from both
  `examples/prelim_sweep/`'s and `examples/prelim_sweep_fine_pilot/`'s equivalents — no real
  generation invoked.
- [ ] 1.6 **Implement** `examples/prelim_sweep_fine/generate_full_corpus.py`: `BASE_INPUTS =
  Path("examples/prelim_sweep_fine_pilot/base_inputs.3d.fine")` (reused, not copied), `OUTPUT_DIR =
  Path("examples/prelim_sweep_fine")`, `WORKSPACE_HOSTPATH =
  "/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine"`, module constants
  `_FROZEN_CORPUS_DIR = Path("examples/prelim_sweep")` and `_PILOT_DIR =
  Path("examples/prelim_sweep_fine_pilot")` (named explicitly to match task 1.3/1.4's monkeypatch
  targets), `_validate_output_dir` rejecting both, `argparse` `--output`/`--timestamp` (same shape
  as `generate_pilot.py`), calling `generate_sweep(BASE_INPUTS, args.output,
  timestamp=args.timestamp)` with no other kwargs. All of 1.1–1.5 pass.
- [ ] 1.7 **Verify:** `uv run pytest tests/test_full_corpus_deck.py -v`.

---

## 2. Generate and commit the 27-config decks/manifest (cluster-free)

- [ ] 2.1 Run `uv run python examples/prelim_sweep_fine/generate_full_corpus.py --timestamp
  <fixed-ISO8601>` from the repo root (fixed timestamp, never wall-clock, for byte-reproducible
  provenance — same convention as the pilot's `DEFAULT_TIMESTAMP`).
- [ ] 2.2 **Verify before committing:** run `git status --porcelain examples/prelim_sweep/
  examples/prelim_sweep_fine_pilot/` and confirm it prints **nothing** — a passive, one-time
  sanity check (mirrors the pilot's `design.md` note on why this isn't a repeatable automated
  test against the real frozen path). Non-empty output means the guard failed to prevent
  cross-contamination; stop and investigate before proceeding to 2.3.
- [ ] 2.3 Commit `examples/prelim_sweep_fine/inputs/inputs.3d.*` (27 decks),
  `sweep_manifest.json`, `sweep_manifest.units.json`, `sweep_provenance.json`. Confirm via `git
  ls-files examples/prelim_sweep_fine/` that exactly the expected file set is tracked (no stray
  `runs/` content leaking in — that directory is already covered by the generalized
  `examples/prelim_sweep*/runs/` `.gitignore` pattern, verify with `git check-ignore -v
  examples/prelim_sweep_fine/runs/placeholder` if in doubt).

---

## 3. `submit_workflow.sh --parallelism` flag (TDD, cluster-free)

- [ ] 3.1 **Test first:** create `tests/test_submit_workflow_parallelism.py`. In a `tmp_path`
  fixture, write an executable stub named `argo` (`#!/bin/sh` — trivial and **non-blocking**: it
  must not replicate real `argo submit --watch`'s blocking behavior, or the test hangs) that
  captures **`$2`** specifically (the real invocation shape is `argo submit "$workflow_file" -n
  "$NAMESPACE" --watch --parameter ...` — the workflow-file path is always the token right after
  the literal `submit`, never the last argument) by copying it to a captured path, then exits `0`
  ignoring everything else:
  ```sh
  #!/bin/sh
  cp "$2" "$CAPTURE_FILE"
  exit 0
  ```
  Prepend the stub's directory to `PATH`. Invoke `submit_workflow.sh full --image
  "ghcr.io/x@sha256:$(python3 -c "print('a'*64)")"` (a well-formed but fake digest, satisfying
  `require_image`'s precondition — `full` calls it before ever reaching the sed/argo step) via
  `subprocess.run(..., env=...)`. Assert, across separate sub-tests:
  1. `--parallelism 1` → the stub's captured file contains `parallelism: 1`.
  2. flag omitted → the stub's captured file is **byte-identical to
     `cluster/argo/workflows/force-surrogate-sweep.yaml` itself** (true no-op — no temp file
     content differs from the committed file, proving the script did not sed-patch at all, not
     just that it happened to reproduce `3`).
  3. `--parallelism 0`, `-1`, and `abc` each exit non-zero with a clear message, **and the stub is
     never invoked at all** (assert via a stub-invocation marker file that doesn't get created).
  4. In all four cases (1–3), `cluster/argo/workflows/force-surrogate-sweep.yaml`'s `sha256` on
     disk is identical before and after the script runs.
  5. **Failed-substitution path**: set the `WORKFLOW` env var (task 3.2's new testability seam) to
     a `tmp_path` copy of the real workflow file with its `parallelism:` line deleted; invoke
     `full --parallelism 1` against it; assert a non-zero exit with a clear "expected exactly
     one..." message, and that the stub is never invoked — this exercises the 0-match `die` path
     that the real committed file (which always has exactly one match) cannot exercise on its own.
  Fails: flag doesn't exist yet.
- [ ] 3.2 **Implement**: parse `--parallelism` alongside the existing `--image`/`--namespace`/etc.
  flags with **no default** (empty sentinel = flag not given). Change the `WORKFLOW` assignment to
  respect a pre-set environment variable (`WORKFLOW="${WORKFLOW:-$(cd "$SCRIPT_DIR/../workflows"
  && pwd)/force-surrogate-sweep.yaml}"`, matching the script's existing `"${VAR:-default}"` idiom)
  so task 3.1.5 can inject a mangled copy without touching the real file. In the `full` command: if
  `--parallelism` was given, validate it matches `^[1-9][0-9]*$` (`die` otherwise), grep-count
  exactly one `^  parallelism: [0-9]\+$` line in `$WORKFLOW` **using `|| true`** on the `grep -c`
  assignment (required under this script's `set -euo pipefail` — a zero-match `grep -c` exits
  non-zero, and without `|| true` that kills the script before the `die` message below ever runs,
  silently defeating the loud-failure guarantee), `die` if not exactly one, `sed`-patch a `mktemp`
  copy with that anchored pattern, grep-verify the substitution landed (`die` if not), `trap 'rm -f
  "$tmp"' EXIT`, and pass the temp path to `argo submit` in place of `$WORKFLOW`. If
  `--parallelism` was not given, pass `$WORKFLOW` straight through unpatched — no temp file, no sed
  call. Also edit the usage header comment block (lines 2-18) to document `--parallelism` under
  the `full` command's description. 3.1 passes.
- [ ] 3.3 **Verify:** run the new test suite. Confirm `cluster/argo/scripts/submit_workflow.sh
  help` actually prints the new `--parallelism` documentation (assert `"--parallelism" in
  stdout`, not a manual eyeball check) — if the header grew past line 18, re-check and bump the
  `help` case's hardcoded `sed -n '2,22p'` range so the new line isn't truncated or doesn't spill
  into the executable code below it.
- [ ] 3.4 **Update CI lint scope:** add `examples/prelim_sweep_fine/` to both hardcoded path lists
  in `.github/workflows/ci.yml`'s `ruff check` and `ruff format --check` lines, and to the
  load-bearing comment (lines 19-22) that enumerates those directories (the comment already warns
  a new example directory must be added here, but only mentions the two `run:` lines, not itself —
  update it too so its own enumeration doesn't go stale) — without the `run:` line change,
  `generate_full_corpus.py` is never linted in CI despite a local unscoped `uv run ruff check .`
  passing (false-green).

---

## 4. OpenSpec spec delta

- [ ] 4.1 Add `openspec/changes/add-fine-grid-corpus-full/specs/force-surrogate/spec.md` with
  `## ADDED Requirements` covering: full-corpus deck generation reuses `generate_sweep()`
  unmodified with default grid/holdout, full-corpus artifacts are isolated from both the coarse
  corpus and the pilot, and Argo sweep-submission parallelism is overridable without mutating the
  committed workflow file. Each requirement has at least one `#### Scenario:` block.
- [ ] 4.2 `openspec validate add-fine-grid-corpus-full --strict` passes with zero errors.
- [ ] 4.3 **Update `openspec/project.md`**: add a bullet under `### Implemented` noting the
  27-config fine-grid deck/manifest corpus is committed at `examples/prelim_sweep_fine/` (decks
  only, no CFD output yet), and a bullet under `### Pending` noting the deferred ~2.55-day live
  cluster run requires separate explicit confirmation — matching the precedent set by
  `automate-run-metadata-capture`, which added its own "Implemented" bullet here on landing (the
  other directly-preceding related change, `add-fine-grid-training-pilot`, did **not** add a
  `project.md` bullet — checked `git log --all -- openspec/project.md` directly rather than
  assuming both did). This task lands with commit 3 (task group 6), not commit 1, since the
  "Implemented" bullet describes artifacts (the committed corpus) that don't exist until commit 3.

---

## 5. Verification

- [ ] 5.1 `uv run ruff check .` and `uv run ruff format --check .` clean.
- [ ] 5.2 `uv run pytest tests/test_full_corpus_deck.py tests/test_submit_workflow_parallelism.py
  -v` — all new tests pass.
- [ ] 5.3 Full suite `uv run pytest` is green (no regressions in existing pilot/coarse-corpus
  tests — in particular, confirm `tests/test_fine_pilot_deck.py` and the coarse-corpus
  reproducibility tests still pass unchanged, proving this change didn't perturb either).
- [ ] 5.4 `openspec validate --all --strict` — only pre-existing, unrelated failures (if any)
  remain; nothing newly introduced by this change.

---

## 6. Commit & PR discipline

- [ ] 6.1 Commit grouping, each individually green under **local** verification (`uv run pytest`
  / `ruff`; this repo squash-merges to `main`, so GitHub Actions only evaluates the PR's tip, not
  each intermediate commit — local verification is what actually guarantees each step below is
  green, not a GitHub check):
  1. `chore(openspec): add fine-grid-corpus-full` — the OpenSpec change directory only.
  2. `feat(force-surrogate): full 27-config fine-grid deck generation` —
     `generate_full_corpus.py` + `tests/test_full_corpus_deck.py` + the `ci.yml` lint-path
     addition (task 1 + task 3.4, grouped here since both concern this new script's path).
  3. `feat(force-surrogate): commit full fine-grid corpus decks + manifest` —
     `examples/prelim_sweep_fine/` generated output + `openspec/project.md` bullets (task 2 +
     task 4.3, grouped together since the doc bullet describes exactly this commit's artifacts —
     landing the bullet any earlier would describe a corpus that doesn't exist yet in the
     intermediate diff).
  4. `feat(cluster): submit_workflow.sh --parallelism flag` — the flag + usage-header doc + its
     test (task 3.1-3.3).
  Adjust if squashing turns out cleaner, but each commit that lands must be locally green — no
  "fix previous commit" follow-ups needed to reach green.
- [ ] 6.2 PR body does not reference any issue with a closing keyword unless actually closing it —
  grep the body + all commit messages with `grep -inE '(clos|fix|resolv)[a-z]*:?\s*#[0-9]+'`
  (**case-insensitive `-i`** — this repo's real history capitalizes closing keywords, e.g.
  `Closes #40`, and a case-sensitive grep would miss them) before opening, per the
  negated-closing-keyword gotcha from prior changes in this repo.
- [ ] 6.3 Single PR, opened after the full commit sequence is locally green.
