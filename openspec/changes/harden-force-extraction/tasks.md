# Tasks — harden-force-extraction

TDD: failing test first, then implementation. Cluster-free throughout
(`uv run pytest -m "not gpu and not requires_plotfile"`).

## 1. Cluster-free wiring coverage (#7) — no behavior change

- [ ] 1.1 **(test)** Add a `_synthetic_box(...)` helper (the dict shape `extract_eulerian_box` returns:
      `u,v,w,gradpx,gradpy,gradpz` 3-D + `x,y,z` coords + `dx`) with a uniform inlet plane `U`, a
      uniformly slowed outlet plane `cU`, and constant `gradpx=G`.
      `test_sphere_cv_drag_wiring_known_answer` — monkeypatch `stress_integral.extract_eulerian_box` to
      return it, call `sphere_cv_drag_cd`, assert `cd == cd_from_drag(closed_form_drag)` and that the
      returned `x_inlet`/`x_outlet` are the selected cell centers. (Verifies "Known synthetic box yields
      the closed-form Cd".)

## 2. dt guard + untested guards (#6)

- [ ] 2.1 **(test)** `test_unsteady_dt_nonpositive_raises` (dt=0 and dt<0 → ValueError);
      `test_unsteady_shape_mismatch_raises`; `test_unsteady_nonfinite_raises`. (Verifies "Non-positive
      time step raises" + the existing shape/non-finite guards.)
- [ ] 2.2 Implement: `unsteady_momentum_force` raises `ValueError` on `dt <= 0`. Run 2.1 green.

## 3. CV mode tolerates field-only plotfiles (#8)

- [ ] 3.1 **(test)** `test_cv_method_without_particles` — monkeypatch `extract_particle_forces` to raise
      and `extract_eulerian_box` to return a synthetic box; assert `extract_sphere_cd(method="cv")`
      returns the CV `cd` with `cd_marker_lastpass is None`. And `test_marker_method_requires_particles`
      — `method="marker"` with particle extraction failing still raises. (Verifies "CV mode tolerates a
      field-only plotfile".)
- [ ] 3.2 Implement: in `extract_sphere_cd`, compute the marker sum best-effort when `method="cv"`
      (`cd_marker_lastpass=None` if particles unavailable); keep `method="marker"` strict; update the
      docstring (the key may be `None` in CV mode).

## 4. Doc-consistency reconciliation (review #1–5)

- [ ] 4.1 `t1a-findings.md` §8: standardize the medium Cd on **1.184** (was 1.183 in three spots);
      keep the Richardson 1.131 (which derives from 1.184); soften the isolated-equivalent to the honest
      bracket the §8 error budget supports (≈1.00–1.11), removing any sub-2% "≈1.10 within 1–2%" claim.
- [ ] 4.2 `examples/flow_past_sphere/RESULTS.md`: medium 1.184; replace "≈1.10 (within ~1–2%)" with the
      bracket; keep citing `t1a-findings §8`.
- [ ] 4.3 `roadmap.md` T1b row: fix the dead change link → `openspec/changes/archive/2026-06-24-add-sphere-stress-cd/`; align the isolated-equiv wording.
- [ ] 4.4 `openspec/changes/archive/2026-06-24-add-sphere-stress-cd/proposal.md`: `method="surface_stress"` → `method="cv"`.
- [ ] 4.5 `tests/conftest.py` + `pyproject.toml`: correct the `requires_plotfile` wording (auto-skipped
      when the plotfile root is absent; CI does not pass `-m "not requires_plotfile"`).

## 5. Close-out

- [ ] 5.1 `uv run ruff check src/ tests/` + `ruff format --check` + `uv run pytest -m "not gpu and not
      requires_plotfile"` green; `openspec validate harden-force-extraction --strict`.
- [ ] 5.2 Commit; PR → `docs/aerodynamics-validation-roadmap`; after merge `/openspec:archive`.
