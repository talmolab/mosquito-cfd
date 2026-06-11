# Design — add-force-surrogate-sweep-runner

**Roadmap:** `docs/force_surrogate/roadmap.md` row #3 (PR3). **Branch/change-id:** `add-force-surrogate-sweep-runner`. **Issue:** [#8](https://github.com/talmolab/mosquito-cfd/issues/8). Builds on PR1's published `force-surrogate` foundation (`capture_surrogate_run_metadata`), PR2's committed `examples/prelim_sweep/` corpus + `sweep_manifest.json`, and PR4's merged `scripts/extract_forces.py` driver contract (`<input-dir>/<config_name>/IB_Particle_1.csv`).

## API surface

```python
# src/mosquito_cfd/force_surrogate/runner.py  (new — pure logic; the cluster call is injected)

DEFAULT_CONTAINER_WORKSPACE = "/workspace"
DEFAULT_RUNS_SUBDIR = "runs"
DEFAULT_IAMREX_BINARY = "/opt/cfd/IAMReX/Tutorials/FlowPastSphere/amr3d.gnu.MPI.CUDA.ex"
DEFAULT_WING_VERTEX = "/workspace/wing.vertex"
IB_PARTICLE_CSV = "IB_Particle_1.csv"          # PR4's per-run output name
DEFAULT_COMPLETION_THRESHOLD = 0.99

@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

# Executor = Callable[..., ExecResult];  executor(command: list[str], *, cwd: Path) -> ExecResult

@dataclass(frozen=True)
class Completion:
    complete: bool
    rows: int
    reason: str            # "ok" | "missing" | "empty" | "short" | "bad_header"

@dataclass(frozen=True)
class RunOutcome:
    name: str
    status: str            # "completed" | "skipped" | "failed"
    csv_path: Path
    rows: int
    metadata_path: Path | None

def build_run_command(config, *, workspace, container_workspace=DEFAULT_CONTAINER_WORKSPACE,
                      runs_subdir=DEFAULT_RUNS_SUBDIR, wing_vertex=DEFAULT_WING_VERTEX,
                      iamrex_binary=DEFAULT_IAMREX_BINARY) -> list[str]: ...

def build_wsl_command(command, *, kubeconfig, runai_binary) -> list[str]:
    """PURE wrap of a logical runai command for WSL: `wsl -e bash -c "export KUBECONFIG=...;
    <abs runai path> <args>"`. No subprocess — unit-tested. The driver's real executor calls
    this then hands the result to subprocess.run (the only line outside CI coverage)."""

def check_completion(csv_path, max_step, *, threshold=DEFAULT_COMPLETION_THRESHOLD) -> Completion: ...

def run_sweep(manifest_path, output_root, *, docker_digest, timestamp, executor, workspace,
              resume=True, threshold=DEFAULT_COMPLETION_THRESHOLD,
              container_workspace=DEFAULT_CONTAINER_WORKSPACE, runs_subdir=DEFAULT_RUNS_SUBDIR,
              wing_vertex=DEFAULT_WING_VERTEX, iamrex_binary=DEFAULT_IAMREX_BINARY,
              ) -> list[RunOutcome]: ...

# scripts/run_sweep.py  (thin driver — the ONLY place subprocess.run lives)
#   main(argv, *, executor=None)  # executor injectable for the cluster-free smoke test
#   --manifest examples/prelim_sweep/sweep_manifest.json
#   --output-root <cluster-mount runs dir>  --workspace <runai workspace name>
#   --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:...  --timestamp <iso>
#   [--no-resume] [--threshold 0.99] [--container-workspace /workspace] [--wing-vertex ...]
#   [--iamrex-binary ...] [--kubeconfig ...] [--runai-binary ...]
```

`run_sweep` validates the corpus **fail-fast** before launching anything: the pinned digest (via
the lightweight `validate_image_digest` regex guard — no git/hardware probe), each config's
`input_file`/`max_step` presence **and a positive `max_step`** (the published
`load_manifest_configs` validator does **not** require these — a bare `KeyError` deep in the loop,
or a never-completable `max_step ≤ 0`, would otherwise waste A40 time), and duplicate names (which
would collide on `<output-root>/<name>/`). It returns one `RunOutcome` per config,
`status ∈ {"completed","skipped","failed"}`. A run is **`failed`** when the executor returns nonzero,
**the executor raises** (caught per-config so a transient cluster/WSL error does not abort the
65-minute corpus), **or** the post-run `check_completion` still reports incomplete (the completion
re-check is **authoritative** over the return code); a failed run is logged and recorded but does
**not** abort the corpus, and `run_metadata.json` is written for every config whose executor was
invoked (`completed` and `failed`) with its `status` (plus the `rows`/`max_step`/`threshold` that
decided the verdict) — a `skipped` config keeps its prior metadata. The driver exits non-zero if any
outcome is `failed`.

The library is **pure**: `build_run_command` and `check_completion` do focused work; `run_sweep` does filesystem reads/writes on the **host mount** (the per-config dir, the CSV, the metadata JSON) but delegates the actual container launch to the injected `executor`. The library imports **no** `subprocess`, no RunAI client, and nothing host-specific — so every test runs cluster-free against `tmp_path` + the committed fixtures (CC-2).

## Key decisions

### D1. Sequential loop in one long-lived A40 container
27 configs × ~2.4 min ≈ **65 min** unattended on one A40 workspace (submitted once with `; sleep infinity`, then driven by 27 `runai workspace exec` calls). **Rationale:** (a) one container ⇒ one image digest ⇒ a single coherent provenance record for the corpus; (b) the lab RunAI quota is **A40-only and preemptible** — 27 concurrent workspaces would not be admitted and would fragment completion tracking; (c) the plan (task B2) explicitly wants the corpus to "bake as unattended wall-clock while you write." **Rejected:** one-workspace-per-config (parallel) — faster in principle but quota-infeasible and provenance-fragmenting. The *library* is agnostic to this: `run_sweep` issues one `executor` call per config in manifest order; whether the executor targets a pre-submitted long-lived workspace (the driver's choice) is a driver concern.

### D2. Explicit operator `--docker-digest`, plus a `docker.yml` digest-emit step
The foundation wrapper `capture_surrogate_run_metadata` **requires** a content-addressable `sha256:` digest and **rejects** a mutable tag (PR1). Two ways to obtain the digest: (a) the operator passes it explicitly, or (b) resolve it from the registry at runtime. We choose **(a)** — identical to PR4's `extract_forces.py --docker-digest` contract — because it keeps the tested core free of any network/registry/tooling dependency (cluster-free, CC-2) and makes the pinned image an explicit, auditable operator input. **Rejected (b):** runtime registry resolution (e.g. `docker buildx imagetools inspect` / `crane`) couples the core to a live registry and an external binary.

The roadmap's **CC-1 PR3 follow-up** is included here: `docker.yml` today publishes the `:fp64` image **by tag only** and never surfaces a `sha256:`. We add an `id:` to the existing FP64 `build-push-action` step (a fresh id, e.g. `build_fp64` — **not** colliding with the existing `id: build-args`) and a following step that writes its `outputs.digest` to `$GITHUB_STEP_SUMMARY`. Two correctness details, made **normative** in the task (so the read-back acceptance check cannot pass a broken step):
- **Empty-digest guard.** `build-push-action` only populates `outputs.digest` when the image is **pushed**; on a `workflow_dispatch` with `push: false` the digest is blank. The summary step is guarded `if: steps.build_fp64.outputs.digest != ''` so it never emits a blank line.
- **Full pin form.** The summary emits the **complete content-addressable reference** `ghcr.io/talmolab/mosquito-cfd@<digest>`, not the bare `sha256:...`. The PR1 wrapper only checks for the `sha256:` substring, so a bare digest would *validate* but not be `pull`-able — the operator must paste a reference the cluster can actually pull. The README `--docker-digest` examples use the same `…@sha256:` form.

This closes the loop between "the wrapper requires a digest" and "where does the operator get one." (Small, self-contained CI change; no solver/Dockerfile impact; runs only on push-to-main/tags, never on PRs.)

### D3. Idempotent resume keyed on the completion check
A40 allocations are **preemptible**; a corpus run can die partway. Before issuing a config's command, `run_sweep` calls `check_completion` on its existing `IB_Particle_1.csv`; if it already passes, the config is **skipped** (`status="skipped"`, no `executor` call, a logged `INFO`). So a re-run resumes a partial corpus and only spends A40 time on the incomplete configs. This pairs with PR4's `allow_missing`: if the operator extracts before the corpus is complete, the still-missing configs are auditable downstream. Resume is **on by default** (`resume=True`); `--no-resume` forces a full re-run. The skip is never silent (honors the roadmap "no silent caps" standard).

### D4. `--output-root`, portable provenance, no committed cluster artifacts
The per-config dirs live under the **cluster mount** (`--output-root`, default `examples/prelim_sweep/runs/`), which the container sees as `/workspace/runs/<name>` and the host (Windows) sees as `Z:\...\prelim_sweep\runs\<name>` — the same bytes via the CIFS/NFS mount. The library is given the **host** `output_root` (for the CSV check + metadata write) and the **container** workspace prefix (for the command); it never conflates them.

**Raw IB CSVs are not git-committed** (intermediate, large; `.gitignore` already ignores `IB_Particle_*.csv` globally). This PR also ignores `examples/prelim_sweep/runs/` so the run tree + per-run `run_metadata.json` stay untracked. The committed corpus + provenance land via **PR4's `dataset.parquet` + its `run_metadata.json`** when the real A40 run happens — so this *tested-code* PR plants **no fabricated cluster artifacts** (scientific-honesty parity with PR4's D10: a fixture-derived CSV with a sentinel digest must never masquerade as real CFD output).

Per-run `run_metadata.json` records **portable** fields only — the config name, the pinned digest (`docker_image`), the caller timestamp, the deck's **manifest-relative** path (its `input_file`, the same portable id PR4 uses) + its SHA256 (`hash_file`), and the **exact logical command** (which uses portable `/workspace` container paths). It deliberately does **not** pass `inputs_file=`/`output_dir=` to `capture_run_metadata` (those would record absolute host paths); instead the portable deck id + hash + command go through `extra=`. `git`/`hardware` (commit, hostname) come from the base capture and carry no mount paths. The recorded `git.commit` is the **host/driver** repo commit, not the solver's: the **IAMReX/AMReX commit is pinned content-addressably by the `docker_image` digest** and is recoverable by introspecting that exact image — deliberately *not* re-recorded from the host's `docker/build-args.env`, which could drift from (and so misrepresent) the pinned image's actual build args. `run_metadata.json` is **per-run cluster output, not a committed artifact**, so it is intentionally **not** byte-reproducible (it carries a fresh `run_id` UUID, host commit, and hostname).

### D5. Injected `executor` seam — the honest mock boundary
The one impure action — launching the container — is the injected `executor(command, *, cwd) -> ExecResult`. The **real** executor (in `scripts/run_sweep.py`) wraps the library command with WSL + `export KUBECONFIG=...` + the operator's absolute `runai` binary path **via the pure, unit-tested `build_wsl_command` helper** (which lives in the **library** so the wrapping is covered + linted), then hands the result to `subprocess.run`. This shrinks the genuinely-untested surface to the single irreducible `subprocess.run(...)` shell-out line; the WSL/`KUBECONFIG` string construction is tested exactly as `build_run_command` is. The **fake** executor (in tests) records the command it was handed and, to simulate a successful IAMReX run, writes a synthetic `IB_Particle_1.csv` of `max_step` rows into `cwd` (the host per-config dir). Tests therefore assert **both** sides honestly: the *command* (the science — `mpirun`, the deck, the staged `wing.vertex`, the run cwd) **and** the *side-effect layout* (`<output-root>/<name>/IB_Particle_1.csv` + `run_metadata.json`). No test touches RunAI/GPU. The subprocess-free guarantee is asserted on the **library module only** (`"subprocess" not in inspect.getsource(mosquito_cfd.force_surrogate.runner)`) — **not** on `scripts/run_sweep.py`, which legitimately imports `subprocess` for its real executor; the driver smoke test instead asserts it ran *without invoking* WSL/RunAI (via the injected fake). `cwd` is the **host** per-config dir (where the mount maps the container run cwd); the library locates the CSV at `output_root/<name>/IB_Particle_1.csv` directly (it does not rely on `cwd` to find outputs — `cwd` is purely the executor's working directory + the fake's write target).

### D6. The command, exactly
`build_run_command(config)` returns:

```
["runai", "workspace", "exec", <workspace>, "--", "sh", "-c", <inner>]
```

with `<inner>` (single shell string, `set -e` so a staging failure aborts the run):

```
set -e; mkdir -p <CRUN>; cp <WING> <CRUN>/wing.vertex; cd <CRUN>; \
mpirun --allow-run-as-root -np 1 <BIN> <DECK>
```

- `<CRUN>` = `<container_workspace>/<runs_subdir>/<name>` (e.g. `/workspace/runs/s35_f085_p30`) — the run cwd, so IAMReX writes `IB_Particle_1.csv` there (mounted → `output_root/<name>/`).
- `<WING>` = `wing_vertex` (default `/workspace/wing.vertex`) → copied into the run cwd because the deck's `particle_inputs.geometry_file = wing.vertex` is resolved **relative to cwd** (and `particle_inputs.radius = 1.5` is already in every deck). **The operator must stage `wing.vertex` at the mount root first** — `examples/prelim_sweep/` ships **no** vertex file (only `examples/flapping_wing/wing.vertex` exists). It must be the **dimensionless-domain** wing (`--span 3.0 --chord 1.0 --spacing 0.05`, per the validated regeneration), staged by either `cp examples/flapping_wing/wing.vertex <mount-root>/wing.vertex` or `uv run generate-wing-planform --span 3.0 --chord 1.0 --spacing 0.05 --output <mount-root>/wing.vertex`. The README runner section documents this explicitly so the launch is actionable and the operator cannot silently stage a wrong-scale file.
- `<DECK>` = `<container_workspace>/<config["input_file"]>` (e.g. `/workspace/inputs/inputs.3d.s35_f085_p30`) — referenced by absolute mount path; IAMReX reads it fine.
- `<BIN>` = `iamrex_binary` (default the CUDA executable baked into the image at `/opt/cfd/IAMReX/Tutorials/FlowPastSphere/`).

The launch pattern mirrors the validated [`openspec/runai-dev-workflow.md:29-31`](../../../openspec/runai-dev-workflow.md), with the crucial difference that **cwd is the per-config mounted dir** (not the Tutorials dir) so the IB-particle CSV lands on the mount rather than in ephemeral container storage.

### D7. Completion check — header + row count
`check_completion(csv_path, max_step, threshold)` reads the CSV's **first line** and compares the comma-split header to `IB_PARTICLE_COLUMNS` (the 29-col schema, **reused** from `dataset.py` — single source, never re-listed), then counts data rows (`total_lines − 1`). It returns `complete = header_ok and rows >= ceil(max_step * threshold)`, with `reason ∈ {ok, missing, empty, short, bad_header}`. Default `threshold = 0.99` tolerates a small off-by-one in how IAMReX records the final/initial step while still flagging a crashed (short) or empty run. A **missing** path is incomplete (not an error — that is the resume/`allow_missing` signal), distinguishing it from PR4's hard-fail semantics on a missing *path* at extraction time. The check is dependency-light (plain file read; no pandas), so it is cheap on a real ~4700-row CSV.

**Row-count robustness (cross-platform).** The count is computed so a CSV is counted identically on Windows (dev) and Linux (CI): the file is opened in a way that does not double-count `\r\n`, and a **trailing newline does not add a phantom data row** (e.g. `sum(1 for _ in f) - 1` over a file opened with universal-newline handling, or `len(text.splitlines()) - 1` — never a raw `\n`-tally). Tests write synthetic CSVs with explicit LF (`newline=""`/bytes) and include a `\r\n`-lined and a trailing-newline case so the threshold-boundary (D7 `ceil`) cannot be broken by a line-ending off-by-one.

### D8. No new dependency
The runner is **stdlib-only** (`dataclasses`, `pathlib`, `logging`, `shlex`/string building, `json` via the reused helpers). It adds **no** third-party package, so `pyproject.toml`/`uv.lock` are unchanged and `uv sync --frozen` is unaffected. `subprocess` appears **only** in the driver's real executor.

## Test strategy (TDD, cluster-free — CC-2)

All tests run against the committed `sweep_manifest.json` + `tests/fixtures/synthetic_ib_particle.csv` (for the header schema) + synthetic CSVs the test writes into `tmp_path`. No cluster, GPU, container, or plotfiles.

1. **Command construction** (`build_run_command`): for a representative config the returned list is `["runai","workspace","exec",<ws>,"--","sh","-c",<inner>]`; `<inner>` contains the per-config run cwd `/workspace/runs/<name>`, stages `wing.vertex` into it, and runs `mpirun --allow-run-as-root -np 1 <binary> /workspace/<input_file>`. Iterating all 27 manifest configs yields 27 distinct commands whose run cwds and deck paths match each config name.
2. **Completion check** (`check_completion`): a full-length synthetic CSV (`max_step` rows, correct header) → `complete`, `reason="ok"`; a **header-only** CSV → incomplete `reason="empty"`; a **short** CSV (rows `< max_step*threshold`) → incomplete `reason="short"`; a **missing** path → incomplete `reason="missing"`; a wrong header → `reason="bad_header"`. **Boundary:** exactly `ceil(max_step*threshold)` rows passes and one fewer fails (use a non-integer `max_step*threshold`, e.g. `4706*0.99→4659`); a `\r\n`-lined CSV and a trailing-newline CSV both count correctly (no phantom row).
3. **Output layout matches the PR4 driver contract**: after a faked successful `run_sweep`, the CSV lands at `output_root/<name>/IB_Particle_1.csv` — the **same path** PR4's `extract_forces.py` resolves from `--input-dir output_root` (a round-trip assertion that reuses PR4's `{name → input-dir/<name>/IB_Particle_1.csv}` rule). Compare `Path` objects (not `/`-joined strings) so the assertion is not `\`-vs-`/` fragile on Windows.
4. **Provenance**: each completed config writes `output_root/<name>/run_metadata.json` recording the supplied `docker_image` digest and the `timestamp` **verbatim**, plus `extra` fields (`config`, portable `deck` path, `deck_sha256`, the `command`); a **missing/mutable** digest raises `ValueError` **up front** (inherited from `capture_surrogate_run_metadata`) before any `executor` call. **Portability (positive + negative):** walk every nested string value and assert none matches `^[A-Za-z]:\\` or starts with `/hpi/`, and assert there is **no** `inputs.file` key (the deck is supplied via `extra=`, never `inputs_file=`, since the base capture would otherwise record an absolute path).
5. **Validation (fail-fast)**: a config missing `input_file` or `max_step` raises `ValueError` naming the config+key before any executor call (the published validator does not require these); duplicate names raise (collide on `output_root/<name>/`); an empty manifest returns `[]`.
6. **Resume**: a config whose CSV already passes the check is `status="skipped"` with **no command issued** (asserted against the fake executor's recorded-command list); with resume disabled it **is** re-run; a config whose CSV is **present but short** is **re-run** (not skipped) — resume keys on completeness, not existence.
7. **Failed runs**: a fake executor returning `returncode=1` → that config `status="failed"`, logged, the rest still run; a fake returning `returncode=0` but writing a header-only/short CSV → `status="failed"` (post-run re-check authoritative); `run_sweep` returns one outcome per config.
8. **Injected-executor seam / force-only guard**: `run_sweep` runs to completion with a fake executor; assert the **library module** is subprocess-free (`"subprocess" not in inspect.getsource(mosquito_cfd.force_surrogate.runner)` — **not** applied to the driver, which legitimately imports it); the command references only the force-only deck + the IB CSV (no plotfile/field path), and `run_sweep` accepts no plotfile argument.
9. **WSL wrapping** (`build_wsl_command`, pure): wraps a logical `runai` command into the `wsl -e bash -c "export KUBECONFIG=…; <abs runai> …"` form with the inner command correctly quoted — unit-tested with no subprocess, so the only untested line is the driver's `subprocess.run`.
10. **Driver smoke test** (`scripts/run_sweep.py`, via `importlib.util.spec_from_file_location`, mirroring PR4's `test_force_surrogate_driver.py`): `main(argv, *, executor=<fake>)` over a fixture-derived tree in `tmp_path` exits 0, writes the per-config CSVs + `run_metadata.json`; a second resume invocation issues **zero new commands** (assert the fake's recorded-command list); a run with a failing config makes `main()` exit **non-zero** — all **without** invoking WSL/RunAI.

**Driver executor testability:** the real WSL/`subprocess` executor is the one genuinely cluster-bound seam. `main(argv, *, executor=None)` accepts an injected executor so the smoke test substitutes a fake; the production path (no injection) builds the WSL executor by calling the **tested** `build_wsl_command` and then the single `subprocess.run` line — the only thing outside CI coverage. This mirrors how PR2/PR4 kept the genuinely-cluster/GPU-bound shell out of the tested core.

## Docs touched (anti-drift)

- `examples/prelim_sweep/README.md` gains a **runner section**: the one-line operator launch + resume command as a **`uv run python scripts/run_sweep.py …`** invocation (mirroring the existing `extract_forces.py` regenerate block — **not** a raw `runai` command, which the driver wraps internally), with the `--docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:…` full pin form; the **actionable `wing.vertex` staging step** (`examples/prelim_sweep/` ships none — `cp examples/flapping_wing/wing.vertex <mount-root>/` or regenerate dimensionless `--span 3.0 --chord 1.0 --spacing 0.05`); the "`particle_inputs.radius = 1.5` already in every deck" note; and a pointer that the produced `runs/<name>/IB_Particle_1.csv` is exactly what `extract_forces.py --input-dir <runs-dir>` consumes. It **cross-references** `openspec/runai-dev-workflow.md` for the WSL+`KUBECONFIG`+`runai` wrapper and the mount-mapping table rather than duplicating them.
- `README.md` (root) and `openspec/project.md` `scripts/` lines both mention `run_sweep.py` alongside `extract_forces.py` (kept in lock-step so the two "scripts/ exemplar" lines never diverge).
- `docs/force_surrogate/roadmap.md` — **extend the existing** Inputs/Outputs "Intermediate: one IB-particle force CSV per sweep config (A40 runs)" bullet **in place** (append "→ produced by `scripts/run_sweep.py` into `examples/prelim_sweep/runs/<name>/IB_Particle_1.csv`"), not a parallel restatement; status checkbox flips on merge via `/cleanup-merged`, not here.
- `.gitignore` gains `examples/prelim_sweep/runs/`.
