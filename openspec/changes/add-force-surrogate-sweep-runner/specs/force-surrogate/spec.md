## ADDED Requirements

### Requirement: Per-configuration cluster run command construction

The force-surrogate module SHALL build, as a **pure function** of a sweep configuration, the
RunAI `workspace exec` command that runs one configuration's force-only CFD through the pinned
container. The command SHALL wrap the validated IAMReX launch
(`mpirun --allow-run-as-root -np 1 <iamrex_binary> <deck>`) with the per-configuration container
run directory `<container_workspace>/<runs_subdir>/<name>` as the working directory (so IAMReX
writes its IB-particle CSV there), SHALL stage `wing.vertex` into that working directory (the
deck's `particle_inputs.geometry_file = wing.vertex` is resolved relative to the working
directory), and SHALL reference the deck by its `input_file` path under the container workspace.
Command construction SHALL perform no I/O and SHALL NOT import `subprocess` or any cluster client.

#### Scenario: Command targets the per-config run directory and deck

- **Given** a config `{name: "s35_f085_p30", input_file: "inputs/inputs.3d.s35_f085_p30", max_step: 4706}` and `workspace = "sweep-runner"`
- **When** `build_run_command` is called with the default container workspace `/workspace`
- **Then** it returns `["runai", "workspace", "exec", "sweep-runner", "--", "sh", "-c", <inner>]`
- **And** `<inner>` sets the working directory to `/workspace/runs/s35_f085_p30`, copies the staged `wing.vertex` into that directory, and runs `mpirun --allow-run-as-root -np 1 <iamrex_binary> /workspace/inputs/inputs.3d.s35_f085_p30`

#### Scenario: Every corpus configuration yields a distinct, correctly-targeted command

- **Given** the committed `examples/prelim_sweep/sweep_manifest.json` (27 configs)
- **When** `build_run_command` is called for each config
- **Then** it produces 27 commands, each whose run directory ends in that config's `name` and whose deck path ends in that config's `input_file`, with no two commands sharing a run directory

#### Scenario: Command construction is pure (no cluster, no I/O)

- **Given** a single config dict
- **When** `build_run_command` is called with no cluster, GPU, or container present
- **Then** it returns the command list without reading or writing any file and without invoking RunAI

### Requirement: Per-configuration output layout matches the dataset driver contract

The runner SHALL write each configuration's IB-particle force CSV to
`<output-root>/<name>/IB_Particle_1.csv` — the **exact** path that the merged dataset driver
(`scripts/extract_forces.py`) resolves from its `--input-dir <output-root>`. This guarantees the
PR4 extractor consumes the runner's output with no glue. The CSV filename SHALL be the IAMReX
per-run name `IB_Particle_1.csv`.

#### Scenario: Runner output is the path the extractor reads

- **Given** an `output-root` and a config named `s45_f100_p45`
- **When** the runner completes that config
- **Then** its CSV is at `<output-root>/s45_f100_p45/IB_Particle_1.csv`
- **And** this equals the path `scripts/extract_forces.py` resolves for that config from `--input-dir <output-root>` (`<input-dir>/<name>/IB_Particle_1.csv`)

### Requirement: Per-run cluster provenance with pinned digest

Each completed configuration run SHALL emit a `run_metadata.json` via the force-surrogate
provenance helper `capture_surrogate_run_metadata`, requiring a pinned container **digest**
(containing `sha256:`) and a **caller-supplied** timestamp (CC-1). The metadata SHALL record the
digest, the timestamp verbatim, and portable provenance (the configuration name, the deck's
manifest-relative path — its `input_file`, the same portable identifier PR4 uses — and its SHA256,
and the exact logical command), and SHALL NOT record absolute host mount paths. A missing or mutable-tag digest SHALL be rejected **before** any
container run is launched.

#### Scenario: Provenance records the pinned digest and caller timestamp

- **Given** a container image reference containing `sha256:` and a caller-supplied ISO-8601 timestamp
- **When** a configuration run completes
- **Then** its `<output-root>/<name>/run_metadata.json` records the digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, the config name, and the deck's SHA256

#### Scenario: Mutable tag rejected up front

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** `run_sweep` is called
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) before any configuration's run command is issued to the executor

#### Scenario: Recorded provenance is portable

- **Given** a completed run's `run_metadata.json`
- **When** every nested string value is inspected
- **Then** no value is an absolute host mount path (none matches a `^[A-Za-z]:\\` drive-letter path nor starts with `/hpi/`); the **deck** is identified by its manifest-relative path (`deck`, the config's `input_file`) plus its SHA256 (`deck_sha256`), while the recorded **command** embeds portable container (`/workspace/...`) paths — two intentionally different fields
- **And** the metadata has no `inputs.file` key (the deck id is supplied via `extra=`, not via `inputs_file=`, because the base capture records an absolute `inputs.file` path when given `inputs_file=`)

### Requirement: Run completion verification

The runner SHALL verify each configuration's IB-particle CSV is complete: the file SHALL exist,
its header SHALL equal the documented 29-column IB-particle schema (`IB_PARTICLE_COLUMNS`, reused
from the dataset module — not re-listed), and its data-row count SHALL be at least
`max_step · threshold` (default threshold 0.99, configurable). A missing, empty (header-only), or
short CSV SHALL be flagged incomplete with a distinguishing reason; a full-length CSV SHALL pass.

#### Scenario: Full-length CSV passes

- **Given** an IB-particle CSV with the correct 29-column header and `max_step` data rows
- **When** `check_completion` is called with that config's `max_step`
- **Then** it reports complete with `rows == max_step` and `reason == "ok"`

#### Scenario: Empty and short CSVs are flagged incomplete

- **Given** a header-only CSV (zero data rows), and separately a CSV with fewer than `max_step · threshold` data rows
- **When** `check_completion` is called
- **Then** the header-only CSV is incomplete with `reason == "empty"` and the short CSV is incomplete with `reason == "short"`

#### Scenario: Missing CSV and wrong header are distinguished

- **Given** a config whose CSV **path does not exist**, and separately a CSV whose first line is not the 29-column schema
- **When** `check_completion` is called
- **Then** the missing path is incomplete with `reason == "missing"` (not an error — this is the resume signal) and the mis-headed CSV is incomplete with `reason == "bad_header"`

#### Scenario: Row-count threshold boundary is exact

- **Given** a `max_step` and `threshold` whose product is non-integer (e.g. `max_step = 4706`, `threshold = 0.99` → `ceil(max_step · threshold) = 4659`)
- **When** `check_completion` is called on a CSV with exactly `ceil(max_step · threshold)` data rows, and separately on one with exactly one fewer
- **Then** the first is complete (`reason == "ok"`) and the second is incomplete (`reason == "short"`) — the boundary is `rows >= ceil(max_step · threshold)`, pinning the off-by-one
- **And** the data-row count is correct whether or not the CSV ends in a trailing newline, and whether its line ending is `\n` or `\r\n` (a trailing newline is not counted as an extra data row)

### Requirement: Idempotent resume of a partial corpus

The runner SHALL skip any configuration whose IB-particle CSV already passes the completion check,
so that re-running over a partially-completed corpus resumes rather than recomputes (the A40
allocation is preemptible). The skip SHALL be logged and reported, never silent, and SHALL pair
with the dataset extractor's `allow_missing` so a still-incomplete corpus is auditable downstream.
Resume SHALL be enabled by default and disable-able by the caller.

#### Scenario: Already-complete configuration is skipped, the rest run

- **Given** an `output-root` in which one config's `IB_Particle_1.csv` already passes the completion check and the others are absent, with `resume=True`
- **When** `run_sweep` is called
- **Then** the already-complete config has `status == "skipped"` and **no** run command is issued to the executor for it
- **And** every other config has a run command issued and (on a successful executor) `status == "completed"`

#### Scenario: Resume can be disabled

- **Given** the same already-complete config with resume disabled
- **When** `run_sweep` is called
- **Then** a run command **is** issued for that config (it is re-run, not skipped)

#### Scenario: A partial (short) CSV is re-run, not skipped

- **Given** an `output-root` where one config's `IB_Particle_1.csv` exists but has fewer than `max_step · threshold` rows (a preempted run), with `resume=True`
- **When** `run_sweep` is called
- **Then** that config is **re-run** (a command is issued, `status != "skipped"`) — resume skips only configs that pass the completion check, never configs whose CSV is merely present, so a preempted partial run is correctly resumed rather than mistaken for complete

### Requirement: Cluster-free injected executor seam (force-only)

The runner SHALL take the container launch as an **injected executor** so all of its logic is
testable without RunAI, a GPU, or a container (CC-2). The executor SHALL be a callable
`executor(command, *, cwd) -> ExecResult`; the tested library SHALL NOT import `subprocess` or a
cluster client (those live only in the thin driver's real executor). The runner SHALL operate
**force-only** (CC-6): it launches only the force-only decks (`amr.plot_int = -1`) and reads/writes
only the IB-particle CSV — it neither accepts nor requires any plotfile or velocity/pressure-field
path.

#### Scenario: Full sweep runs against an injected fake executor

- **Given** a fake executor that records each command and writes a synthetic full-length `IB_Particle_1.csv` into the per-config directory
- **When** `run_sweep` is called over a manifest with no cluster, GPU, or container present
- **Then** it completes, the recorded commands match `build_run_command` for each config, and each config's CSV + `run_metadata.json` are written under `<output-root>/<name>/`

#### Scenario: No plotfile or field path is consumed or produced

- **Given** the runner inputs
- **When** `run_sweep` is called
- **Then** it requires only the manifest, the output root, and the executor — it neither accepts nor requires a plotfile/field path — and the constructed commands reference only the force-only deck and the IB-particle CSV (no plotfile output)

### Requirement: Sweep input validation is fail-fast

The runner SHALL validate the sweep before launching any container run, so a malformed corpus
never wastes A40 time or surfaces a bare `KeyError` deep in the loop. `run_sweep` SHALL return one
`RunOutcome` per configuration, SHALL reject a configuration missing the keys it consumes
(`input_file`, `max_step`) with a clear `ValueError` naming the configuration and the missing key
(the published manifest validator does not require these keys), SHALL reject duplicate configuration
names (which would collide on the same `<output-root>/<name>/` directory), and SHALL handle an empty
manifest without error. All such validation SHALL occur **before** any run command is issued to the
executor.

#### Scenario: One outcome per configuration

- **Given** a manifest with `N` configurations and a successful executor
- **When** `run_sweep` is called
- **Then** it returns exactly `N` `RunOutcome`s, one per configuration in manifest order

#### Scenario: Configuration missing a consumed key is rejected before any run

- **Given** a manifest configuration lacking `input_file` (or lacking `max_step`)
- **When** `run_sweep` is called
- **Then** it raises `ValueError` naming the configuration and the missing key, and **no** run command is issued to the executor (a bare `KeyError` is never surfaced, because the published `load_manifest_configs` validator does not require `input_file`/`max_step`)

#### Scenario: Duplicate configuration names are rejected before any run

- **Given** a manifest with two configurations sharing a `name`
- **When** `run_sweep` is called
- **Then** it raises `ValueError` (inherited from `load_manifest_configs`) before any run command is issued — two configs with the same name would otherwise collide on `<output-root>/<name>/`

#### Scenario: Empty manifest yields no outcomes

- **Given** a manifest whose `configs` list is empty
- **When** `run_sweep` is called
- **Then** it returns `[]` without error and issues no run command

### Requirement: Failed runs are isolated and surfaced

The runner SHALL record a configuration whose run does not produce a complete CSV — the executor
returns a nonzero `returncode`, or the executor returns zero but the post-run completion check still
reports incomplete (short/empty CSV) — with `status == "failed"`. It SHALL log every failure (never
silent) and SHALL NOT abort the remaining configurations (so one bad config does not lose the
65-minute corpus; resume retries it on a later run). The post-run completion check SHALL be
authoritative over the executor return code. The thin driver SHALL exit non-zero if any
configuration's outcome is `failed`.

#### Scenario: Nonzero executor return is recorded as failed and the sweep continues

- **Given** a fake executor that returns `ExecResult(returncode=1)` for one configuration and succeeds for the rest
- **When** `run_sweep` is called
- **Then** that configuration's outcome is `status == "failed"`, the failure is logged, every other configuration still runs, and `run_sweep` returns one outcome per configuration

#### Scenario: A run that completes but leaves a short CSV is failed

- **Given** a fake executor that returns `ExecResult(returncode=0)` but writes a header-only (or short) `IB_Particle_1.csv`
- **When** `run_sweep` is called
- **Then** that configuration's outcome is `status == "failed"` — the post-run completion re-check is authoritative, not the return code — and its failure is logged

#### Scenario: Driver exits non-zero when any configuration failed

- **Given** a run in which at least one configuration's outcome is `failed`
- **When** the thin driver `scripts/run_sweep.py` `main()` returns
- **Then** its exit code is non-zero, so an operator's unattended corpus run surfaces the incomplete corpus rather than reporting success
