# Force-surrogate kinematic sweep (`prelim_sweep`)

A reproducible corpus of **27 IAMReX input decks** over the *Aedes aegypti*-anchored kinematic
grid, generated for the Track B force-only surrogate (see
[`docs/force_surrogate/roadmap.md`](../../docs/force_surrogate/roadmap.md), row #2). These decks are
the input side of the eventual predicted-vs-CFD evidence figure; the
[Argo sweep workflow](../../cluster/argo/README.md) runs them on the cluster, PR4 extracts forces,
PR5 trains, PR6 plots.

**Force-only (CC-6):** every deck sets `amr.plot_int = -1` — no field plotfiles (forces come from
the IB-particle CSV), which sidesteps the velocity-field-in-plotfiles issue entirely.

## What's here

| File | Contents |
|---|---|
| `inputs/inputs.3d.s{φ}_f{f*×100}_p{α}` | 27 decks, one per grid point (e.g. `inputs.3d.s35_f085_p30`). |
| `sweep_manifest.json` | Deterministic config description: per-config kinematics, `nu_star`, `reynolds`, `max_step`/`stop_time`, `plot_int`, train/holdout `split`; plus grid levels and the holdout seed. |
| `sweep_manifest.units.json` | Units of the measured columns (dimensionless / deg). |
| `sweep_provenance.json` | git commit, base-inputs SHA256, and the caller-supplied timestamp (kept **separate** from the manifest so the non-reproducible git SHA cannot defeat byte-identity). |
| `generate_sweep.py` | Thin driver; all logic lives in `mosquito_cfd.force_surrogate.sweep`. |

## The grid

Levels and their *Aedes* grounding (Bomphrey et al. 2017, *Nature* 544:92–95) are the
source-attributed `AEDES_*` constants in
[`force_surrogate/constants.py`](../../src/mosquito_cfd/force_surrogate/constants.py); per-config
Reynolds numbers are in `sweep_manifest.json` — they are not re-tabulated here to avoid drift.
Summary: stroke amplitude φ ∈ {35, 45, 55}°, dimensionless frequency f\* ∈ {0.85, 1.0, 1.15}
(≈ 609/717/825 Hz), pitch amplitude α ∈ {30, 45, 60}° → 27 configs.

> **Note on the kinematics.** The validated demo (`examples/flapping_wing/`) uses a **70°** stroke —
> a generic large-amplitude case, *not* the mosquito value. This sweep deliberately re-anchors on the
> *Aedes* stroke (≈39°, Bomphrey 2017), which the {35, 45, 55}° levels bracket.

## Reynolds policy (CC-7: ν\* held fixed)

Viscosity `ns.vel_visc_coef = ν* = 0.115` is **held fixed** across all 27 configs, so the Reynolds
number (≈ 43–90) varies as a deterministic function of the swept φ and f\*. This keeps the
(φ, f\*, α) → force map well-posed (Re is a function of the inputs, not a hidden variable) and keeps
every deck differing from the validated base in only the swept/derived keys. Per-config Re is
recorded in the manifest. (See `design.md` D1 of the `add-force-surrogate-sweep-config` change.)

## Run duration

Each deck covers **2 whole wingbeats**: `stop_time = 2 / f*`, `max_step = round(stop_time / 5e-4)`
(the validated `dt`). So low-frequency configs run longer in steps, guaranteeing whole periodic
cycles for force extraction.

## Held-out configs (CC-4)

6 configs (seeded, drawn from grid **non-corners** so the figure measures interpolation) are labelled
`split = "holdout"` in the manifest. The label only excludes them from *training* — all 27 are still
generated and run, since the held-out set is the CFD ground truth.

## Regenerating

```bash
uv run python examples/prelim_sweep/generate_sweep.py   # run from the repo root
```

Regeneration is **byte-identical** (fixed seed + fixed caller timestamp); the test
`test_committed_sweep_matches_regeneration` enforces this. Re-running into an existing directory
prunes any stale decks first, so a shrunk config set never leaves orphans.

> **Naming resolution.** Deck file names (`inputs.3d.s{φ}_f{f*×100}_p{α}`) encode **whole-degree**
> stroke/pitch and **0.01-resolution** f\*. Configs finer than that (e.g. φ=42.5° or f\*=1.005) would
> collide on the same name; the generator detects this and raises before writing, rather than
> silently overwriting a deck. Widening the grid to sub-degree resolution requires changing the
> naming scheme.

## Running the sweep on the cluster

Both paths write each run's IB-particle force CSV to `runs/<name>/IB_Particle_1.csv` — exactly the
per-config layout `scripts/extract_forces.py --input-dir runs/` consumes (no glue) — plus a portable
per-run `run_metadata.json` pinned to the container **digest**. The raw `runs/` tree is **not**
committed (`.gitignore`d); the committed corpus + provenance land via `dataset.parquet` (below).

### Production: Argo workflow

The corpus is produced cluster-side by **[Argo Workflows](../../cluster/argo/README.md)** — one A40
pod per config whose main process is `mpirun`, with built-in retries and no laptop/VPN dependency.
This is the production path; see [`cluster/argo/README.md`](../../cluster/argo/README.md) for the
submit/monitor flow and the post-merge digest-pin preconditions.

### Local/dev fallback (`scripts/run_sweep.py`)

`scripts/run_sweep.py` (library `mosquito_cfd.force_surrogate.runner`) is a **local/dev fallback**,
not the production path: it drives each config from the laptop via `runai workspace exec` into one
long-lived A40 workspace. That exec stream blocks for ~10 min/config and **drops intermittently** —
on the first full run it dropped after config 2 and left an orphaned `amr3d` holding 34 GB of the
A40, so configs 3–27 crashed on a busy GPU (**1 of 27** completed). Use it only for a one-off
single config or when you have no Argo access; for the full corpus, use the Argo workflow above. It
resumes a partial corpus (skips configs whose CSV already passes the completion check).

#### 1. Stage `wing.vertex` at the mount root

`prelim_sweep` ships none, and the decks reference it relatively
(`particle_inputs.geometry_file = wing.vertex`; `radius = 1.5` is already in every deck). Use the
validated **dimensionless** wing:

```bash
# either reuse the validated file …
cp examples/flapping_wing/wing.vertex Z:/users/eberrigan/mosquito-cfd/examples/prelim_sweep/wing.vertex
# … or regenerate it (must be dimensionless: span 3, chord 1)
uv run generate-wing-planform --span 3.0 --chord 1.0 --spacing 0.05 \
    --output Z:/users/eberrigan/mosquito-cfd/examples/prelim_sweep/wing.vertex
```

#### 2. Submit one long-lived A40 workspace

Mount the **`prelim_sweep`** dir at `/workspace` (`,readwrite` is mandatory) and keep the container
alive with `sleep infinity` so the driver can exec into it 27 times:

```bash
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && \
  /home/elizabeth/.runai/bin/runai workspace submit force-sweep \
    -p talmo-lab \
    --image ghcr.io/talmolab/mosquito-cfd:fp64 \
    --image-pull-policy Always \
    --gpu-devices-request 1 \
    --preemptible \
    --host-path path=/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep,mount=/workspace,readwrite \
    -- bash -c 'sleep infinity'"
```

The mount maps the **same** directory three ways — keep them consistent with step 3 (the canonical
copy of this mapping lives in
[`openspec/runai-dev-workflow.md`](../../openspec/runai-dev-workflow.md#workspace-mount-mapping)):

| View | Path |
|---|---|
| Windows host (`--output-root`/`wing.vertex` staging) | `Z:\users\eberrigan\mosquito-cfd\examples\prelim_sweep\` |
| Cluster NFS (`--host-path path=`) | `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep/` |
| Inside container (`--container-workspace`, default) | `/workspace/` |

#### 3. Run the driver (loops `runai workspace exec`)

Get the pinned digest from the `docker.yml` build run's job summary ("FP64 image digest"), then run
the driver with `--workspace` = the name you submitted and `--output-root` = the **host** view of
`runs/` (same dir the container sees as `/workspace/runs`):

```bash
uv run python scripts/run_sweep.py \
    --manifest examples/prelim_sweep/sweep_manifest.json \
    --output-root Z:/users/eberrigan/mosquito-cfd/examples/prelim_sweep/runs \
    --workspace force-sweep \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp <iso-8601>
```

The driver wraps each launch with the RunAI/WSL/`KUBECONFIG` invocation (overridable via
`--kubeconfig`/`--runai-binary`); see
[`openspec/runai-dev-workflow.md`](../../openspec/runai-dev-workflow.md) for the underlying cluster
workflow and `runai` CLI details. A re-run resumes (skips already-complete configs); the driver
exits non-zero if any config failed. When the corpus is done, free the GPU with
`runai workspace delete force-sweep`.

Each launched config writes the solver's captured stdout/stderr to `runs/<name>/run.log` (referenced
from `run_metadata.json`), so a failed or anomalous config is debuggable from its own output — `tail`
it between configs to watch progress or diagnose a failure.

> **Force-CSV name.** `IB_Particle_1.csv` (PR4's contract) is **verified against the real IAMReX
> output** of the A40 corpus — the committed `dataset.parquet` was extracted from
> `runs/<name>/IB_Particle_1.csv`. The `--csv-name` flag stays overridable should a future run write
> forces under a different name.

## Dataset (`dataset.parquet`)

PR4's extractor (`scripts/extract_forces.py`, library `mosquito_cfd.force_surrogate.dataset`)
turns each config's IB-particle force CSV into a tidy table — **one row per (config, timestep)** —
of kinematics + phase + normalized force/moment coefficients + raw forces/moments, joined to this
sweep's `reynolds` and train/holdout `split`. Forces come from the IB-particle CSV **only**
(`amr.plot_int = -1`, CC-6); no plotfiles.

| File | Status | Contents |
|---|---|---|
| `dataset.units.json` | **committed** | The column→unit contract (the schema sidecar). Pure metadata — no force values — so a consumer (PR5) has a `read_units_sidecar`-validatable contract to develop against. |
| `dataset.parquet` | **committed** | The data — the 27-config corpus extracted to one row per (config, timestep). PR4 deliberately deferred this until a real corpus existed (committing the synthetic test fixture, with a required `sha256:` digest in `run_metadata.json`, would have misrepresented synthetic numbers as real CFD output with false provenance); it landed once the cluster Argo sweep (PR #16) produced all 27 runs. |
| `run_metadata.json` | **committed** | Provenance for the dataset build (pinned `:fp64` container digest of the CFD image, caller timestamp, local build host / git SHA, manifest input hash, any `dropped_configs`). Each CFD run's own A40 provenance lives in its `runs/<name>/run_metadata.json` (not committed — the `runs/` tree is gitignored). |

The **normative column schema** is the `force-surrogate` spec's *"Columns are the documented
schema"* scenario; the units are in the committed `dataset.units.json` — neither is re-listed here
to avoid drift.

**Phase and cycle selection (read before training).** Every timestep is kept and tagged:

- `phase = (time · f*) mod 1 ∈ [0, 1)` — fraction through the current wingbeat.
- `wingbeat = floor(time · f*)` — integer cycle index; **`0` is the startup transient**.

The extractor does **not** drop the startup beat. **Filter to the converged last beat yourself**
— with the current 2-wingbeat corpus that is `wingbeat ≥ 1`. (Keeping all rows avoids the silent
masking trap; the consumer decides the window explicitly.)

`phase`/`wingbeat` are deterministic functions of the `time` value **as written in the CSV**. A
single timestep that lands exactly on a beat boundary (`time · f* = k`) can fall on either side by
one step depending on how the solver records `time` (e.g. accumulated solver time may sit one ULP
below `k`). This affects at most one boundary row and is immaterial to converged-beat filtering, but
do not assume beat boundaries align to an exact `phase = 0.0` row.

### Regenerating

```bash
uv run python scripts/extract_forces.py \
    --manifest examples/prelim_sweep/sweep_manifest.json \
    --input-dir <runs-dir> \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp <iso-8601> \
    --out examples/prelim_sweep/dataset.parquet \
    --units examples/prelim_sweep/dataset.units.json \
    --metadata examples/prelim_sweep/run_metadata.json
```

## Surrogate (`metrics.json`, predictions, checkpoint)

PR5's trainer (`scripts/train_surrogate.py`, library `mosquito_cfd.force_surrogate.train`) learns
the **kinematics(+phase) → force-coefficient** map from `dataset.parquet` with a **PhysicsNeMo**
regressor and evaluates it on the **held-out configurations** (CC-4). Inputs are the three swept
kinematic knobs + a cyclic `(sin, cos)(2π·phase)` encoding (Reynolds excluded — derivable under the
ν\*-fixed policy); targets are all six `CF_*` coefficients; only the converged beat (`wingbeat ≥ 1`)
is used. Force-coefficients only — no field/plotfile reading, DoMINO, or RL (CC-6).

The four artifacts live under **`surrogate/`** (a subdirectory so the surrogate's `run_metadata.json`
does not collide with the dataset build's `run_metadata.json` one level up):

| File | Status | Contents |
|---|---|---|
| `surrogate/metrics.json` | **committed** | Per-target / aggregate / per-config RMSE/MAE/R² on the 6 holdout configs + an inference latency/throughput block + a reproducibility block. |
| `surrogate/holdout_predictions.parquet` | **committed** | Per holdout (config, timestep): `CF_*_true`/`CF_*_pred` — the versioned input to the PR6 figure. |
| `surrogate/surrogate.pt` | **committed** | The trained checkpoint (state dict + the train-fit standardizer stats). Binary (`*.pt` pinned in `.gitattributes`). |
| `surrogate/run_metadata.json` | **committed** | Provenance: the dataset corpus's pinned `:fp64` digest, git SHA, host/GPU, seeds, resolved `torch`/`physicsnemo` versions. |

The **normative schemas** for `metrics.json` and the predictions table are the `force-surrogate`
spec scenarios *"metrics.json carries per-target, aggregate, per-config, and inference keys"* and
*"Predictions parquet schema"* — neither is re-listed here to avoid drift.

> **Read the `config_resolved` block, not just the aggregate R² (CC-4).** The pointwise aggregate
> R² (~0.98) is **~99.9% the within-beat force waveform** — a smooth periodic shape shared by every
> config — so it overstates the kinematics→force-*map* skill. `metrics.json` also reports, per
> target, `config_resolved.config_mean_r2` (R² on the per-config **cycle-mean** — the phase-removed
> config-to-config skill, ~0.75–0.94) and `within_config_variance_fraction` (how waveform-driven the
> aggregate is). The PR6 figure caption uses the honest config-resolved number, not the aggregate.

**Training is local — the RTX A5000 (24 GB, FP32/TF32) via WSL2 + `uv`, *not* RunAI.** The GPU
deps are an opt-in group:

```bash
uv sync --group train          # installs PhysicsNeMo + CUDA torch + wandb (Linux/WSL2 only)
uv run python scripts/train_surrogate.py \
    --dataset examples/prelim_sweep/dataset.parquet \
    --out-dir examples/prelim_sweep/surrogate \
    --docker-digest "$(python -c 'import json,sys;print(json.load(open("examples/prelim_sweep/run_metadata.json"))["docker_image"])')" \
    --timestamp <iso-8601> \
    --device cuda --wandb online        # --wandb defaults to "disabled" (CI/rerun-safe)
```

`--wandb online` logs the run to Weights & Biases; the default `disabled` is a no-op (no login
needed) and `metrics.json` is always written from local state regardless of wandb.

**Reproducibility (honest scope).** Seeds + `torch.use_deterministic_algorithms` are set. The
**torch-free CPU helper chain** (features/split/standardizer/metrics) is **bitwise-reproducible**
and CI-tested; the GPU run is **seeded but not bitwise** (cuDNN/TF32), so `metrics.json` records
`reproducibility.bitwise == "cpu_only"`.

**Tests.** CPU-tier tests are cluster-free and gate CI. The GPU tier (PhysicsNeMo construction, a
seeded loss-decrease, and the full train→predict→`metrics.json` round-trip) is marked
`@pytest.mark.gpu`, auto-skipped when CUDA/PhysicsNeMo are unavailable, and run on the A5000 with:

```bash
uv run pytest -m gpu        # operator-only; CI runs `-m "not gpu"`
```
