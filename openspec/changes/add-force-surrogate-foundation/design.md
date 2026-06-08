# Design — add-force-surrogate-foundation

**Roadmap:** `docs/force_surrogate/roadmap.md` row #1 (PR1). **Branch/change-id:** `add-force-surrogate-foundation`.

## API surface

```python
# src/mosquito_cfd/force_surrogate/normalization.py
def compute_force_reference(
    f_star: float, phi_amp_deg: float, r_tip: float,
    span: float, chord: float, rho: float = 1.0,
) -> ForceReference:  # dataclass: u_tip_max, q_tip, area, f_ref
    """U_tip_max = 2π·f*·radians(phi_amp_deg)·r_tip; q_tip = ½ρU²; S = π/4·span·chord; F_ref = q_tip·S."""

def compute_force_coefficients(
    fx: ArrayLike, fy: ArrayLike, fz: ArrayLike, f_ref: float,
) -> ForceCoefficients:  # dataclass: cf_x, cf_y, cf_z (each F/F_ref)
    ...

# src/mosquito_cfd/force_surrogate/sidecar.py
def write_units_sidecar(path: Path, units: dict[str, str]) -> None: ...   # validates against UNITS_VOCABULARY
def read_units_sidecar(path: Path) -> dict[str, str]: ...
def capture_surrogate_run_metadata(*, docker_image_digest: str, **kw) -> dict: ...  # wraps benchmarks.metadata.capture_run_metadata
```

`ForceReference` / `ForceCoefficients` are small frozen dataclasses (named fields beat positional dicts for downstream clarity and test assertions).

## Key decisions

### D1. Single source of normalization (CC-3) — refactor in this PR
`F_ref` math currently lives inline in `examples/flapping_wing/generate_all_figures.py:236–241` (function `plot_f1_forces`). To actually deliver CC-3 ("never re-derived inline"), **PR1 refactors that block to call `compute_force_reference`** rather than deferring it — otherwise the new module and the example would carry two copies that can silently diverge (the regression test only pins the new module). The refactor is ~6 lines and the script already uses module-level constants matching `constants.py`; we verify the figure still reports `f_ref ≈ 624.79` by running it to a temp dir (CSV figures only). PR4/PR6 also import the helper.

The regression target values (`u_tip_max≈23.029, q_tip≈265.17, area≈2.356, f_ref≈624.79`) are **recomputed from the formula**; `RESULTS.md:100–103` documents the rounded forms (23.0/265.2/2.356/624.8), so the test uses `rtol=1e-3`.

### D2. Reuse provenance, don't fork it (with two wrapper-enforced guarantees)
`benchmarks/metadata.py:capture_run_metadata(inputs_file, output_dir, docker_image, timing, extra)` already captures git/hardware/docker/inputs/timing. We import it **unchanged** (no `benchmarks/` churn) and wrap it as `capture_surrogate_run_metadata(*, docker_image_digest, inputs_file=None, timestamp=None, ...)`. The wrapper adds what the base does not guarantee:
- **Digest required:** the base stores the image as a flat `docker_image` string and silently omits it when falsy. The wrapper passes `docker_image=docker_image_digest` and **raises `ValueError` on a blank/missing digest** (a required, non-empty kwarg) so no surrogate run is recorded against a mutable tag. (Test asserts `meta["docker_image"] == digest`.)
- **Caller-supplied timestamp (CC-1):** the base hardcodes `timestamp = datetime.now(UTC)`. CC-1 requires reproducible artifacts not stamped with runtime wall-clock, so the wrapper **overrides `meta["timestamp"]` with the caller-supplied value** when provided.
- `inputs.hash` is only populated by the base when `inputs_file` is passed and exists — callers/tests must pass a real file to get it (the digest-only path records git + digest + timestamp).

Note: producing the digest is the operator's job at run time (PR3); `docker.yml` publishes by tag and does not currently surface a `sha256:` digest — a recommended follow-up is to emit `build.outputs.digest` to the CI job summary (tracked in the roadmap, not PR1).

### D3. Dimensionless units
`project.md` does **not** state a units convention (no SI mandate is written there), and the validated flapping-wing run is fully **dimensionless** and unscaled. Inventing an SI mapping now would impose a physical scale the data does not have. The `units.json` vocabulary is therefore dimensionless (`"dimensionless"`, `"deg"`, `"dimensionless (f*)"`). When a physical scale is later fixed (a downstream concern, like calibration in other repos), an SI conversion utility can be added without changing the pipeline. Both `write_units_sidecar` and `read_units_sidecar` reject any column whose unit is not in `UNITS_VOCABULARY` (symmetric validation, so a hand-edited sidecar cannot smuggle in an illegal unit).

### D4. Cluster-free fixtures (CC-2)
Committed under `tests/fixtures/`: `synthetic_ib_particle.csv` and `micro_sweep.json` (2 configs over φ/f\*/pitch). These let PR2/PR4/PR6 tests run with zero infrastructure.

**The CSV mirrors the real IB-particle schema's full 29-column header in exact order** (`iStep,time,X,Y,Z,Vx,Vy,Vz,Rx,Ry,Rz,Fx,Fy,Fz,Mx,My,Mz,Fcp{x,y,z},Tcp{x,y,z},SumU{x,y,z},SumT{x,y,z}`) — `Fx,Fy,Fz` are columns 12–14, *not* the first columns. All columns are zero except `Fx,Fy,Fz`, which are exact multiples of a round `F_ref=100.0` so coefficients are exact decimals. This faithfulness matters: PR4's extractor reads *real* 29-column CSVs, so the fixture must be a true stand-in and the loader must be **name-based, never positional**. No comment line (real CSVs have the header on row 1); provenance lives in `tests/fixtures/README.md`. (Earlier drafts wrongly listed a trimmed force-front 11-column header — corrected here.)

### Why benchmarks/metadata.py changed (deviation from "no benchmarks change")

D2 originally said the wrapper would reuse `capture_run_metadata` with **no** change to
`benchmarks/`. During implementation the reuse surfaced a pre-existing cross-platform bug:
`get_git_info` runs `git diff HEAD` with `text=True`, which on **Windows** decodes git's UTF-8
stdout as cp1252. Once the working tree contained non-ASCII docs (φ/≈/→ in this change's files),
the decode raised `UnicodeDecodeError`, leaving `diff.stdout = None` and crashing at
`len(diff.stdout)`. Fixed minimally by adding `encoding="utf-8", errors="replace"` to the
`subprocess.run` calls in `get_git_info`/`get_hardware_info`. git emits UTF-8, so this is strictly
more correct on every platform — a bugfix, not a workaround (no follow-up debt). The wrapper still
treats `capture_run_metadata` as the single provenance source.

## Out of scope
Cluster/RunAI runs, plotfile/velocity-field reading, the forces→parquet extractor (PR4), training (PR5), figure (PR6), RL. Force-only.
