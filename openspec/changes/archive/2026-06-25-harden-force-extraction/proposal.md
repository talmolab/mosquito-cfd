# Change: harden-force-extraction

Robustness + test-coverage hardening of the `force-extraction` capability, plus doc-consistency
reconciliation, from the post-merge `/review-pr` of T1b (`add-sphere-stress-cd`).

## Why

The T1b review found no blocking defects but three robustness/coverage gaps and a set of
cross-document numeric inconsistencies in the just-landed work:

- The drag-from-plotfile **wiring** (`sphere_cv_drag_cd` → `extract_eulerian_box` →
  `periodic_duct_drag`) has **no cluster-free test** — every assertion that pins a real Cd is
  `requires_plotfile` and skipped in CI, so a wiring regression (wrong plane, wrong slice, wrong
  `dy*dz`/`dx`) would not be caught.
- `unsteady_momentum_force` divides by `dt` with **no `dt > 0` guard** (`dt=0` → silent `inf`/`nan`),
  and its shape/non-finite guards are untested.
- `extract_sphere_cd(method="cv")` **hard-depends on IB particle fields** (it always reads
  `particle_real_comp*` for the diagnostic), so a *field-only* plotfile crashes before the
  marker-independent CV path runs.
- Several docs cite the medium-grid Cd inconsistently (1.183 vs 1.184) and one states an
  isolated-equivalent "≈1.10 (within ~1–2%)" that the documented ~1–5% viscous error budget does not
  support; plus a dead roadmap link and a stale `method="surface_stress"` name in the archived proposal.

## What Changes

- **Cluster-free wiring coverage (no behavior change):** a synthetic in-memory "box" fixture (the shape
  `extract_eulerian_box` returns) lets a known-answer test drive `sphere_cv_drag_cd` end-to-end with no
  plotfile, pinning plane selection, the `gradpx` slice, `dy*dz`/`dx`, sign, and the Cd conversion.
- **`dt > 0` guard** in `unsteady_momentum_force` (raise rather than emit `inf`/`nan`); its shape and
  non-finite guards get tests.
- **CV mode tolerates field-only plotfiles:** when `method="cv"`, the IB-marker diagnostic is computed
  *best-effort* — if particle fields are absent, `cd_marker_lastpass` is `None` and the CV `cd` is still
  returned. `method="marker"` (default) still requires particles (that *is* the method).
- **Doc reconciliation:** standardize the medium Cd on **1.184**; soften the isolated-equivalent to the
  honest bracket (≈1.00–1.11); fix the roadmap T1b archive link; correct `surface_stress`→`cv` in the
  archived proposal; fix the `requires_plotfile` marker/CI wording.

## Impact

- **Affected specs:** MODIFIES `force-extraction` (adds robustness + cluster-free-verifiability
  requirements/scenarios).
- **Affected code:** `src/mosquito_cfd/benchmarks/stress_integral.py` (`unsteady_momentum_force` guard),
  `analyze_sphere.py` (`extract_sphere_cd` CV best-effort marker), `tests/test_stress_integral.py` (new
  cluster-free wiring + guard tests + a synthetic-box fixture). No new dependencies; FP64 preserved.
- **Affected docs:** `t1a-findings.md`, `RESULTS.md`, `roadmap.md`, the archived
  `add-sphere-stress-cd/proposal.md`, `conftest.py`/`pyproject.toml` marker wording.
- **Out of scope:** the broader CC-V5/CC-V6 supersession sweep (issue #29); any solver/re-run work.
