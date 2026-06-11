# Tasks — add-force-surrogate-sweep-runner

TDD throughout: each implementation task writes its failing tests **first** (citing the spec
scenario), then the minimal code to pass. **Commit each tests-first + implementation pair as a
single commit — never push the intermediate "tests-only" state** (CI's test job fails on exit 1;
only exit 5 = *no tests collected* is tolerated; an `ImportError` at collection is exit 2 — also
red). All tests are cluster-free (CC-2): they run against the committed
`examples/prelim_sweep/sweep_manifest.json`, the committed `tests/fixtures/synthetic_ib_particle.csv`
(for the 29-col header), and synthetic CSVs the test writes into `tmp_path` — with **no** RunAI, GPU,
container, or plotfiles. The runner is **stdlib-only**: no new dependency, no `uv.lock` change.

> **Import-source rule (CI-ordering, BLOCKING — review finding).** The package-level re-export
> (`force_surrogate/__init__.py`) lands in **task 7**, bundled with the `run_sweep` commit. Until
> then, **every test in tasks 1, 3, 5, and 8 imports from the submodule**
> `from mosquito_cfd.force_surrogate.runner import …`, **never** the package top-level — otherwise
> commits 1–2 fail collection (`ImportError`, exit 2 → red CI). Task 7's re-export test (and task 8's
> for `build_wsl_command`) then assert the package-level import works.

> **Cross-platform CSV writes (review finding).** Every synthetic CSV a test writes into `tmp_path`
> is written **LF-explicit** (`open(..., newline="")` or `write_bytes`) so row counts match on
> Windows (dev) and Linux (CI). Layout assertions compare `Path` objects, never `/`-joined strings.

## 1. Command construction (`runner.py`)

1. [x] **Tests first** (`tests/test_force_surrogate_runner.py`; **submodule imports**), citing spec *Per-configuration cluster run command construction*:
   - For `s35_f085_p30` (`input_file=inputs/inputs.3d.s35_f085_p30`), `build_run_command(config, workspace="sweep-runner")` returns `["runai","workspace","exec","sweep-runner","--","sh","-c",<inner>]`; `<inner>` sets cwd to `/workspace/runs/s35_f085_p30`, stages `wing.vertex` into it, and runs `mpirun --allow-run-as-root -np 1 <DEFAULT_IAMREX_BINARY> /workspace/inputs/inputs.3d.s35_f085_p30` (scenario *Command targets the per-config run directory and deck*).
   - Iterating all 27 committed-manifest configs yields 27 commands with distinct run dirs ending in each `name` and deck paths ending in each `input_file` (scenario *Every corpus configuration yields a distinct, correctly-targeted command*).
   - `build_run_command` reads/writes no file and imports no cluster client (scenario *Command construction is pure*).
   - A config dict missing `input_file` raises a clear `ValueError` naming the config/key (not a bare `KeyError`).
2. [x] Implement `build_run_command` + the module constants (`DEFAULT_CONTAINER_WORKSPACE`, `DEFAULT_RUNS_SUBDIR`, `DEFAULT_IAMREX_BINARY`, `DEFAULT_WING_VERTEX`, `IB_PARTICLE_CSV`, `DEFAULT_COMPLETION_THRESHOLD`) and the `ExecResult`/`Completion`/`RunOutcome` dataclasses in `runner.py`. Google-style docstrings. Run green.

## 2. Completion check (`runner.py`)

3. [x] **Tests first** (`test_force_surrogate_runner.py` additions; **submodule imports**), citing spec *Run completion verification*, reusing `IB_PARTICLE_COLUMNS` from `dataset.py` to build synthetic CSVs in `tmp_path`:
   - Full-length CSV (correct header + `max_step` rows) → `complete`, `rows==max_step`, `reason=="ok"`.
   - Header-only CSV → incomplete, `reason=="empty"`; short CSV (`rows < max_step*threshold`) → incomplete, `reason=="short"`.
   - Missing path → incomplete, `reason=="missing"`; wrong header → `reason=="bad_header"`.
   - **Boundary** (scenario *Row-count threshold boundary is exact*): with `max_step=4706, threshold=0.99` (`ceil=4659`), a CSV with exactly 4659 rows → `ok`; exactly 4658 → `short`. A `\r\n`-lined CSV and a CSV **with** a trailing newline both count the same as the LF/no-trailing case (no phantom data row). **The `\r\n` case MUST be written via `write_bytes`** (or `open(..., newline="")`) so the carriage returns are exact on Windows and Linux — a plain `write_text` would translate newlines and invalidate the case.
4. [x] Implement `check_completion(csv_path, max_step, *, threshold=DEFAULT_COMPLETION_THRESHOLD) -> Completion`: compare first line to `IB_PARTICLE_COLUMNS`; count data rows via `sum(1 for _ in f) - 1` (universal-newline open) or `len(text.splitlines()) - 1` — **never** a raw `\n`-tally; `complete = header_ok and rows >= math.ceil(max_step*threshold)`. Run green.

## 3. Sweep orchestration: validation, provenance, resume, failure (`runner.py`)

5. [x] **Tests first** for `run_sweep` (`test_force_surrogate_runner.py` additions; **submodule imports**), citing spec *Per-configuration output layout…*, *Per-run cluster provenance…*, *Idempotent resume…*, *Sweep input validation is fail-fast*, *Failed runs are isolated and surfaced*, *Cluster-free injected executor seam*. Use a **fake executor** that records `(command, cwd)` and writes a synthetic full-length `IB_Particle_1.csv` into `cwd`:
   - **Output layout**: each CSV is at `output_root/<name>/IB_Particle_1.csv` and equals (as a `Path`) the path `scripts/extract_forces.py` resolves from `--input-dir output_root` (round-trip on the `{name -> input-dir/<name>/IB_Particle_1.csv}` rule).
   - **Provenance**: each `run_metadata.json` records `docker_image` = the `sha256:` digest, `timestamp` verbatim, the config name, and `deck_sha256`. **Portability**: walk every nested string value — none matches `^[A-Za-z]:\\` or starts with `/hpi/`; assert there is **no** `inputs.file` key (deck supplied via `extra=`, not `inputs_file=`). A **mutable tag / missing digest** raises `ValueError` **before** any executor call (assert the fake recorded **zero** commands).
   - **Validation (fail-fast)**: a config missing `input_file`/`max_step` raises `ValueError` naming it before any command (assert zero recorded commands); duplicate config names raise (inherited from `load_manifest_configs`); an empty-`configs` manifest returns `[]`. `run_sweep` returns **one `RunOutcome` per config**.
   - **Resume**: with one config's CSV pre-written full-length and `resume=True`, that config is `status=="skipped"` with **no** command recorded for it; the rest are `status=="completed"`. With resume disabled, a command **is** recorded for the pre-complete config. With a config's CSV **present but short**, resume **re-runs** it (a command is recorded, `status != "skipped"`). **Skipped-metadata untouched**: pre-write a sentinel `run_metadata.json` (e.g. `{"sentinel": true}`) into the already-complete config's dir; after `resume=True` assert it is **byte-unchanged** (skipped configs are never re-stamped) and that **no** `run_metadata.json` is created for a skipped config that lacked one.
   - **Failed runs**: a fake executor returning `ExecResult(returncode=1)` for one config → that config `status=="failed"`, logged, the others still run; a fake returning `returncode=0` but writing a **header-only/short** CSV → `status=="failed"` (post-run `check_completion` is authoritative — assert it is NOT `completed`). `run_metadata.json` is written for `completed` and `failed` configs (with the `status`), not for `skipped`.
   - **Seam (read/write linchpin)**: the fake executor records `(command, cwd)` and writes its synthetic CSV into the `cwd` it is **handed** (not a recomputed path). Assert (as a `Path`) the recorded `cwd` for each config equals `output_root / <name>` — the host per-config dir the mount maps the container run cwd to — so the fake's write target is exactly where `check_completion` later reads; a `run_sweep` that passes the wrong `cwd` (e.g. the container `/workspace/runs/<name>` or bare `output_root`) fails.
   - **Force-only + subprocess-free**: recorded commands match `build_run_command` per config and reference only the deck + IB CSV (no plotfile path); `run_sweep` accepts no plotfile argument. Assert the **library module** is subprocess-free: `import mosquito_cfd.force_surrogate.runner as r; assert "subprocess" not in inspect.getsource(r)` (do **not** apply to the driver). **Use a fixture-derived manifest in `tmp_path`** for the validation/duplicate/empty/missing-key cases (the committed corpus is valid).
6. [x] Implement `run_sweep(...)`: **fail-fast** up front — validate the digest (one `capture_surrogate_run_metadata` guard call), `load_manifest_configs` (duplicate names), and each config's `input_file`/`max_step` presence — **before** the loop. Then per config: `check_completion` for resume-skip, else `executor(build_run_command(...), cwd=host_run_dir)`, re-verify completion (authoritative), set `status`, and for completed/failed write `run_metadata.json` via `capture_surrogate_run_metadata` with portable `extra` (`config`, repo-relative `deck`, `deck_sha256` via `hash_file`, `command`, `ib_particle_csv` relative, `rows`, `max_step`, `status`). Return `list[RunOutcome]`. Log skips/failures (`logging`, never silent). Run green.
7. [x] **Re-export** `build_run_command`, `check_completion`, `run_sweep`, `ExecResult`, `RunOutcome`, `Completion` from `force_surrogate/__init__.py` in the same commit (the **6** symbols that exist by now — **NOT** `build_wsl_command`, which task 8 implements; re-exporting it here would `ImportError` the whole package at this commit); add a test asserting each imports from the **package top-level** `mosquito_cfd.force_surrogate`.

## 4. WSL command wrapping (pure, library) + thin driver

8. [x] **Tests first** for `build_wsl_command` (`test_force_surrogate_runner.py` additions; **submodule import**), citing spec *Cluster-free injected executor seam*: `build_wsl_command(command, kubeconfig="~/.kube/cfg", runai_binary="/home/u/.runai/bin/runai")` returns the `["wsl","-e","bash","-c", <payload>]` form where `<payload>` exports `KUBECONFIG=~/.kube/cfg` and invokes the **absolute** `runai` binary (not bare `runai`). **Adversarial quoting** (so a naive `" ".join` fails): use a `command` containing a shell-metachar arg, e.g. `["runai","workspace","exec","ws","--","sh","-c","echo hi && cd /workspace/runs/s35_f085_p30"]`; assert the payload `shlex.split`s back so the reconstructed inner argv equals the original `command` (the `sh -c "echo hi && …"` grouping survives — a naive space-join that drops it FAILS), and the `runai` token is the absolute path, not split. Pure — no subprocess. **Implement `build_wsl_command` in `runner.py` AND append it to `force_surrogate/__init__.py`'s re-exports (+ extend the top-level-import test) in this same commit** (deferred from task 7 so the package never imports an undefined symbol).
9. [x] **Driver smoke test first** (`tests/test_force_surrogate_run_sweep_driver.py`), mirroring PR4's `test_force_surrogate_driver.py` (`importlib.util.spec_from_file_location`): build a fixture-derived manifest + `output_root` tree in `tmp_path`; run `main([...], executor=<fake>)` (the driver accepts an injected executor for testing) with an obviously-synthetic sentinel `--docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:0000…0000` + fixed `--timestamp`; assert exit 0, per-config `IB_Particle_1.csv` + `run_metadata.json` written. A **second** resume invocation (cumulative fake command-recording) issues **zero new commands** for the already-complete configs. A run where the fake fails one config makes `main()` exit **non-zero**. Assert the smoke test never imports/touches WSL/RunAI. Then implement `scripts/run_sweep.py` (no logic): argparse `--manifest --output-root --workspace --docker-digest --timestamp [--no-resume] [--threshold] [--container-workspace] [--wing-vertex] [--iamrex-binary] [--kubeconfig] [--runai-binary]`; `main(argv, *, executor=None)` builds the **real** WSL executor when `executor is None` (calls the tested `build_wsl_command` then the single `subprocess.run` — the ONLY `subprocess`/`KUBECONFIG`/operator-path site), else uses the injected one; calls `run_sweep(...)`; prints a per-config summary; returns/exits non-zero if any `RunOutcome.status == "failed"`. Google-style docstring with the `uv run python scripts/run_sweep.py …` operator example. Run green.

## 5. CC-1 follow-up: surface the build digest (`docker.yml`)

10. [x] Add an `id:` to the **fp64** `Build and push FP64 image` step in `.github/workflows/docker.yml` (a fresh id, e.g. `build_fp64` — **must not** collide with the existing `id: build-args` at line 100), then a following **guarded** step that writes the full pin reference to `$GITHUB_STEP_SUMMARY` (workflow-level `env: REGISTRY/IMAGE_NAME` are already visible in `run:` as `$REGISTRY`/`$IMAGE_NAME`, so no per-step `env:` is needed). The snippet is fenced with four backticks here so its inner ```` ``` ```` code-fence lines render:

````yaml
    - name: Emit FP64 image digest to job summary
      if: ${{ steps.build_fp64.outputs.digest != '' }}
      run: |
        echo "## FP64 image digest" >> "$GITHUB_STEP_SUMMARY"
        echo '```' >> "$GITHUB_STEP_SUMMARY"
        echo "${REGISTRY}/${IMAGE_NAME}@${{ steps.build_fp64.outputs.digest }}" >> "$GITHUB_STEP_SUMMARY"
        echo '```' >> "$GITHUB_STEP_SUMMARY"
````

    Verify by reading the workflow back (no CI run needed): the fp64 job references `steps.build_fp64.outputs.digest`, emits the **full `ghcr.io/…@sha256:` pin form** (not a bare digest — PR1's wrapper accepts a bare `sha256:` but the cluster can't pull it), and the `if:` guards the `push:false` dispatch case (digest blank → step skipped, no blank summary line). The fp32/python jobs are independent (no `needs:`); no Dockerfile changes → no hadolint impact. (D2.)

## 6. Integration: gitignore, docs

11. [x] Add `examples/prelim_sweep/runs/` to `.gitignore` (the run tree + per-run `run_metadata.json` stay untracked; `IB_Particle_*.csv` is already globally ignored). Confirm a faked `run_sweep` into that path leaves `git status` clean for tracked files.
12. [x] Add a **runner section** to `examples/prelim_sweep/README.md`: the one-line operator launch + resume command as a `uv run python scripts/run_sweep.py …` invocation (mirroring the `extract_forces.py` block; full `--docker-digest ghcr.io/…@sha256:…` pin form; **not** raw `runai`); the **actionable `wing.vertex` staging step** (prelim_sweep ships none — `cp examples/flapping_wing/wing.vertex <mount-root>/` or `uv run generate-wing-planform --span 3.0 --chord 1.0 --spacing 0.05 --output <mount-root>/wing.vertex`, the dimensionless wing); the "`particle_inputs.radius = 1.5` already in every deck" note; and the pointer that `runs/<name>/IB_Particle_1.csv` is exactly what `extract_forces.py --input-dir <runs-dir>` consumes. **Cross-reference** `openspec/runai-dev-workflow.md` for the WSL/`KUBECONFIG`/`runai` wrapper + mount-mapping table — do **not** duplicate them. Update **both** the root `README.md` and `openspec/project.md` `scripts/` lines to mention `run_sweep.py` alongside `extract_forces.py` (lock-step). **Extend in place** the `docs/force_surrogate/roadmap.md` Inputs/Outputs "Intermediate" bullet (append the `scripts/run_sweep.py → runs/<name>/IB_Particle_1.csv` production note), not a parallel restatement (status checkbox flips on merge via `/cleanup-merged`, not here).

## 7. Lint, coverage, validation

13. [x] `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/` and `uv run ruff format --check` clean (the new `runner.py`/`run_sweep.py` land in already-linted paths — PR4 widened CI to `scripts/`; no `ci.yml` change needed). `uv run pytest` green; `uv run pytest --cov` reports coverage for `runner.py`.
14. [x] `openspec validate add-force-surrogate-sweep-runner --strict` passes.
15. [x] Re-read `proposal.md`/`design.md`/`spec.md` vs the implementation; reconcile any drift (update docs + add a `### Why N instead of M?` note if the implementation had to deviate).

### Why 5 commits instead of 9, and "manifest-relative" instead of "repository-relative"

- **Commit granularity (no behavioral change).** The per-task commit plan (1–9) was collapsed into
  5 green commits — A: the whole `runner.py` + its 27 tests + `__init__` re-exports (incl.
  `build_wsl_command`); B: driver + smoke tests; C: `docker.yml`; D: `.gitignore`; E: docs. Landing
  the full library + re-exports in **one** commit sidesteps the task-7-vs-8 re-export-ordering hazard
  entirely (the package never imports an undefined symbol), and every commit is independently green.
  The behavior, API, and spec are unchanged.
- **Provenance `deck` field.** The runner records the deck as the manifest's `input_file`
  (manifest-relative, e.g. `inputs/inputs.3d.<name>`) — the same portable identifier PR4's
  `extract_forces.py` keys on — rather than a repo-root-relative path. `spec.md`/`design.md` were
  updated from "repository-relative" to "manifest-relative" to match. The portability guarantee (no
  absolute mount path) is unchanged.
- **subprocess-free assertion.** Implemented via AST of `runner.py`'s imports (not a raw `"subprocess"`
  substring), because the module **docstring legitimately mentions** subprocess (explaining it does
  not import it) — a substring check would false-positive. The assertion is strictly stronger.

### Pre-PR self-review hardening (`/review-pr` findings)

The pre-merge subagent code review (no BLOCKING) surfaced fixes folded in before opening the PR
(spec updated to match):

- **Executor-raises resilience.** The real WSL/`subprocess` executor can *raise* (e.g. `wsl` not
  found, transient cluster `OSError`), not just return nonzero — which would abort the unattended
  65-minute corpus. `run_sweep` now catches the exception per-config, records `status="failed"`, and
  continues. New requirement scenario *An executor that raises is isolated as failed* + test.
- **`validate_image_digest` extraction.** The up-front digest fail-fast previously ran a full
  `capture_surrogate_run_metadata` (git + `nvidia-smi` + `nvcc` subprocesses) just to validate a
  regex, discarding the result. Extracted a pure `validate_image_digest` in `sidecar.py` (reused by
  the capture; behaviour unchanged) and call it for the fail-fast.
- **`max_step > 0` fail-fast.** A non-positive `max_step` can never satisfy the completion check;
  rejected up front rather than burning an A40 slot. New scenario + test.
- **Provenance completeness.** `run_metadata.json` now records the `threshold` that decided the
  `completed`/`failed` verdict (so the verdict is self-describing).
- **Header strictness documented.** `check_completion`'s exact-order 29-col header gate is the
  *producer*-side strict check (PR4 reads name-based downstream); commented in-code as intentional.
- **Driver typing + dead `# noqa`.** Annotated the driver's executor factory/`main` and removed a
  `# noqa: S603` for a rule (`S`) not in the ruff select set.
- **Coverage.** Added a truly-0-byte-CSV test → `runner.py` 100%.
