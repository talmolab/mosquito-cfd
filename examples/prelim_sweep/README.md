# Force-surrogate kinematic sweep (`prelim_sweep`)

A reproducible corpus of **27 IAMReX input decks** over the *Aedes aegypti*-anchored kinematic
grid, generated for the Track B force-only surrogate (see
[`docs/force_surrogate/roadmap.md`](../../docs/force_surrogate/roadmap.md), row #2). These decks are
the input side of the eventual predicted-vs-CFD evidence figure; PR3 runs them on the cluster, PR4
extracts forces, PR5 trains, PR6 plots.

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

## Running the sweep on the cluster (PR3)

`scripts/run_sweep.py` (library `mosquito_cfd.force_surrogate.runner`) loops this corpus through
the pinned `:fp64` container on **one** RunAI A40 workspace, writing each run's IB-particle force
CSV to `runs/<name>/IB_Particle_1.csv` — exactly the per-config layout
`scripts/extract_forces.py --input-dir runs/` consumes (no glue). It resumes a partial corpus
(skips configs whose CSV already passes the completion check) and writes a portable per-run
`run_metadata.json` pinned to the container **digest**. The raw `runs/` tree is **not** committed
(`.gitignore`d) — the committed corpus + provenance land via `dataset.parquet` (below).

The sweep runs in **two phases**: you submit **one** long-lived A40 workspace, then the driver
`runai workspace exec`s each config into it (the driver does **not** submit the workspace).

### 1. Stage `wing.vertex` at the mount root

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

### 2. Submit one long-lived A40 workspace

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

The mount maps the **same** directory three ways — keep them consistent with step 3:

| View | Path |
|---|---|
| Windows host (`--output-root`/`wing.vertex` staging) | `Z:\users\eberrigan\mosquito-cfd\examples\prelim_sweep\` |
| Cluster NFS (`--host-path path=`) | `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep/` |
| Inside container (`--container-workspace`, default) | `/workspace/` |

### 3. Run the driver (loops `runai workspace exec`)

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

> **Force-CSV name (verify on the first run).** `IB_Particle_1.csv` is **assumed** from PR4's
> contract and **not yet verified against a real IAMReX run** — the repo `.gitignore` hints forces
> may instead land in `forces.csv`. If your first single-config run shows the forces under a
> different name, pass `--csv-name forces.csv` (mirrors `extract_forces.py --csv-name`) rather than
> editing source. **Smoke-test one config before the full 27.**

## Dataset (`dataset.parquet`)

PR4's extractor (`scripts/extract_forces.py`, library `mosquito_cfd.force_surrogate.dataset`)
turns each config's IB-particle force CSV into a tidy table — **one row per (config, timestep)** —
of kinematics + phase + normalized force/moment coefficients + raw forces/moments, joined to this
sweep's `reynolds` and train/holdout `split`. Forces come from the IB-particle CSV **only**
(`amr.plot_int = -1`, CC-6); no plotfiles.

| File | Status | Contents |
|---|---|---|
| `dataset.units.json` | **committed** | The column→unit contract (the schema sidecar). Pure metadata — no force values — so a consumer (PR5) has a `read_units_sidecar`-validatable contract to develop against. |
| `dataset.parquet` | **committed when PR3's corpus lands** | The data. PR4 deliberately does **not** commit a fixture-derived parquet: the only data available pre-PR3 is the synthetic test fixture, and committing it (with a required `sha256:` digest in `run_metadata.json`) would misrepresent synthetic numbers as real CFD output with false provenance. |
| `run_metadata.json` | **committed when PR3's corpus lands** | Provenance (pinned container digest, caller timestamp, any `dropped_configs`). |

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

### Regenerating (once PR3's corpus exists)

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
