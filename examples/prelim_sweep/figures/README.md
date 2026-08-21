# Force-surrogate sweep figures

Figures for the `prelim_sweep` 27-config coarse corpus (Track B force-only surrogate). Two
families, from two scripts.

## Evidence figure — `scripts/make_evidence_figure.py`

PR6's *Evidence-of-Readiness* figure: predicted-vs-CFD scatter for **CF_x / CF_z / CF_my** on
the six held-out configurations (points colored by config with a shared legend), plus an
honest, data-driven caption and batched-throughput speedup annotation. See the parent
[`../README.md`](../README.md#figure-figures)'s "Figure" section for the full discussion,
including why the pointwise aggregate R² overstates skill and how to read the per-axis
config-resolved numbers.

| File | Shows |
|------|-------|
| `evidence_figure.png` | Predicted-vs-CFD scatter, `CF_x`/`CF_z`/`CF_my`, held-out configs. |
| `evidence_figure_metrics.json` | Every number on the figure (RMSE, config-resolved R², speedup decomposition). |
| `run_metadata.json` | Provenance: pinned `:fp64` digest, timestamp, git SHA/host, input hashes. |

## Wing-phase geometry diagnostic — `scripts/make_wing_phase_diagnostic.py`

Cluster-free sanity check (Phase 3 of `fix-force-surrogate-sweep-hinge`) that the wing hinge sits
at the **span root**, not a midspan pivot — the defect this change fixes. Plots the wing marker
cloud at four phases of one wingbeat (t = 0, T/4, T/2, 3T/4) with the hinge marked as a black
triangle; its metrics dict is produced by the same `assert_hinge_at_span_root` guard
(`src/mosquito_cfd/force_surrogate/geometry_guard.py`) used in `tests/test_sweep_hinge_geometry.py`,
so a passing render and a passing test agree by construction. No CFD output needed — it reads
kinematics + the wing vertex file only.

Rendered against the **default sample** (documented in the CLI's own `--help`): the validated
calibration baseline (`examples/flapping_wing/inputs.3d.validation`'s 70°/45° kinematics) plus the
sweep grid's two extreme corners, `s35_f085_p30` and `s55_f115_p60`. All three configs share the
same hinge — `(x, y, z) = (4.0, 0.5, 4.0)`, span arm `1.5` about the span axis `y` — since the
hinge location doesn't depend on kinematics, only on the wing geometry and mount point.

| File | Shows |
|------|-------|
| `validated_wing_phases.png` / `_metrics.json` / `_run_metadata.json` | The known-correct calibration baseline (70° stroke, 45° pitch). |
| `s35_f085_p30_wing_phases.png` / `_metrics.json` / `_run_metadata.json` | Sweep grid corner: smallest stroke/frequency/pitch (35°, f\*=0.85, 30°). |
| `s55_f115_p60_wing_phases.png` / `_metrics.json` / `_run_metadata.json` | Sweep grid corner: largest stroke/frequency/pitch (55°, f\*=1.15, 60°). |

## Regenerate

```bash
# Evidence figure (cluster-free; reads the committed surrogate/ artifacts):
uv run python scripts/make_evidence_figure.py \
    --predictions examples/prelim_sweep/surrogate/holdout_predictions.parquet \
    --metrics examples/prelim_sweep/surrogate/metrics.json \
    --out-dir examples/prelim_sweep/figures \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp <iso-8601>

# Wing-phase geometry diagnostic, default sample (cluster-free; reads decks + wing.vertex only):
uv run python scripts/make_wing_phase_diagnostic.py \
    --corpus-dir examples/prelim_sweep \
    --out-dir examples/prelim_sweep/figures \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp <iso-8601>

# ...or a single config, or --config all for every config in the corpus:
uv run python scripts/make_wing_phase_diagnostic.py --config s45_f100_p45 \
    --corpus-dir examples/prelim_sweep --out-dir examples/prelim_sweep/figures \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> --timestamp <iso-8601>
```
