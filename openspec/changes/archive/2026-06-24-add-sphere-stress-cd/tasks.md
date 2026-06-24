# Tasks — add-sphere-stress-cd

## Status (delivered) — method deviated; see design "Why two-plane periodic-duct…"

- ✅ **0** marker registered (`pyproject.toml`, `conftest.py`).
- ✅ **1** core implemented as the **periodic-duct CV balance** (not the single-plane wake survey — invalid
  under periodic y/z): `periodic_duct_drag`, `cd_from_drag`, `extract_eulerian_box`, `sphere_cv_drag_cd`
  in `stress_integral.py`, with cluster-free KATs (momentum uniform+varying, constant-gradpx pressure,
  null, NaN-raises, Cd definition; `ρ≠1`). `recover_pressure_in_plane`/`wake_survey_drag` removed.
- ✅ **2** yt adapter (full level-0 covering grid + in-memory slice, `('boxlib',·)` tuples + presence
  assert, `YTArray→float64`, halo, cell-center coords); marked tests pass on real data.
- ✅ **3** `extract_sphere_cd(method="cv")` (back-compat; `cd_marker_lastpass` diagnostic); exported.
- ✅ **4** ran on committed `plt10000` → **H1/H1′** (coarse 1.342, medium 1.184, Richardson 1.131;
  field/marker 2.64×; H2 excluded). Recorded in `t1a-findings.md §8`, `flow_past_sphere/RESULTS.md`.
- ⏭️ **5 (Stage-2 full 6-face box)** — **not needed**; the two-plane balance already plateaus.
- 🟡 **6 (CC-V5/V6)** — done for `RESULTS.md` + `METHODS.md` Known-Limitation #1; the broader sweep
  (apex change files, frozen Track-B corpus captions, `force_surrogate` roadmap, `heaving_ellipsoid`
  RESULTS) is a **tracked follow-up issue** (keeps this PR focused; avoids entangling frozen/submitted
  artifacts and another in-flight change).
- 🟡 **7** close-out (this step).

Original (pre-deviation) task list below, retained for traceability.



TDD throughout: each implementation task is preceded by its failing test, and tests+impl for a group are
committed together (never a red-test-only commit). CI stays cluster-free; the literature validation is a
marked local step. Cluster-free command: `uv run pytest -m "not gpu and not requires_plotfile"`.

**Two stages (minimal-first).** Stage 1 (the single-plane wake survey) makes the H1/H2 verdict with
minimal code. Stage 2 (the full 6-face CV box + `<1%` KATs) is built only if Stage 1 is band-edge
ambiguous or the published-rigor artifact is wanted — it does **not** gate the verdict.

## 0. Test infrastructure (must precede any `requires_plotfile` use)

- [ ] 0.1 Register a `requires_plotfile` marker in `pyproject.toml`
      `[tool.pytest.ini_options].markers` + an auto-skip in `tests/conftest.py` (mirror the `gpu` skip):
      skip when the plotfile root is absent. Path source = env var `MOSQUITO_CFD_PLOTFILE_ROOT`
      (documented default = the Z: benchmarks dir); never hard-code a Windows path into collection. Add
      `-m "not gpu and not requires_plotfile"` as the documented cluster-free invocation.

## 1. Stage-1 core: wake survey + the KATs that gate the verdict (cluster-free)

- [ ] 1.1 **(test)** `test_stress_integral.py::test_momentum_term_divergence_free_closed_form` — a
      **pointwise divergence-free** wake field (uniform freestream + transverse-compact x-uniform deficit;
      `v,w` close continuity; **assert `‖div u‖≈0`**; **survey faces in the freestream, `u=U∞`**), `p=0`;
      assert the wake-survey drag `ρ∬u_x(U∞−u_x)dA` (= `ρπσ²A(2U∞−A)` for a Gaussian) within 1% (box ≥5σ
      or compare to the truncated integral). (Verifies "Momentum-flux term…" + "Single-plane wake survey".)
- [ ] 1.2 **(test)** `::test_pressure_term_linear_pressure` — uniform `u`, `∇p=(G,0,0)`; assert pressure
      drag `−G·L_x·A_x` within 1% and that `recover_pressure_from_grad` reproduces `p0+G·x` up to a
      constant. (Verifies "Pressure term…".)
- [ ] 1.3 **(test)** `::test_pressure_constant_invariance` (drag invariant to an added pressure constant,
      `assert_allclose`); `::test_null_field_zero_drag` (tol `1e-12·ρU∞²D²`); `::test_cd_from_drag_known_answer`
      (`Fx/(½ρU²·πD²/4)`); `::test_sign_convention` (inlet `+ρU∞²`). (Verifies "Null field…", "Pressure-
      constant invariance", sign.)
- [ ] 1.4 Implement the Stage-1 core in `src/mosquito_cfd/benchmarks/stress_integral.py` (FP64):
      `wake_survey_drag(plane fields, *, rho, U, D)`, `recover_pressure_in_plane(...)`,
      `cd_from_drag(Fx, *, rho, U, D)`, and the full `control_volume_drag(...)` returning
      `{Fx,Fy,Fz, per_face, per_term}` (used by Stage 2). Run 1.1–1.3 green.

## 2. yt Eulerian adapter (cluster I/O, isolated)

- [ ] 2.1 **(test, marked)** `::test_adapter_single_level_exact_fp64` under
      `@pytest.mark.requires_plotfile` — assert `extract_eulerian_box` returns **bare `float64`** arrays
      (YTArray unwrapped), enforces `ds.index.max_level == 0`, confirms an fp64 build, reads via
      `('boxlib', name)` tuples, **asserts all six fields present**, and returns real cell-center coords.
      Skips cleanly when the plotfile is absent. (Verifies "Single-level covering grid is exact and FP64".)
- [ ] 2.2 **(test, marked)** `::test_adapter_pads_for_face_derivatives` — assert the read box is padded
      ≥1 cell (≥2 centered) beyond the requested integration faces. (Verifies "Read extent is padded…".)
- [ ] 2.3 Implement `extract_eulerian_box(plotfile_path, bounds, *, halo)` via `covering_grid(level=0)`:
      lattice-aligned `left_edge`/`dims` from `ds.domain_left_edge`; `('boxlib',·)` field tuples;
      `.to_ndarray()` + `.astype(np.float64)`; present-fields + single-level + fp64 asserts; return arrays
      **plus** cell-center coordinate arrays.

## 3. `extract_sphere_cd` integration (back-compatible)

- [ ] 3.1 **(test)** `::test_default_method_preserves_contract` — default (marker) path still returns
      every pre-change key incl. **`fy_sum`, `fz_sum`** (analyze_sphere.py:139–148). Synthetic fixture, no
      plotfile. (Verifies "Default method preserves the existing contract".)
- [ ] 3.2 **(test)** `::test_surface_stress_method_reports_field_cd` — `method="surface_stress"` with a
      stubbed plane/box ⇒ `cd` is the field Cd and `cd_marker_lastpass` carries the relabelled marker
      diagnostic. (Verifies "Surface-stress method reports the field-based Cd".)
- [ ] 3.3 Implement the `method=` branch; relabel the marker sum as `cd_marker_lastpass` (diagnostic
      only); extend (never break) the return dict; export new public symbols from `benchmarks/__init__.py`;
      **update the `extract_sphere_cd` docstring** (full return-key list — incl. the currently-undocumented
      `literature_cd` — and the new `method=` arg) at `analyze_sphere.py:117-124`. Add a contract note that
      `cd_from_drag`'s "drag = streamwise Fx" assumes +x freestream; **T2b reuse must pass the streamwise
      axis explicitly** (CC-V4, design Decision 9); the core returns the full `(Fx,Fy,Fz)`.

## 4. Literature validation + H1/H1′/H2 classification (marked/local; Z: is mounted here)

- [ ] 4.1 **(test, marked)** `::test_sphere_cd_classifies[coarse,medium]` under
      `@pytest.mark.requires_plotfile` — wake-survey Cd on both grids; **classify** H1 (±5% of 1.087) /
      H1′ (≈1.09–1.15, isolated-equivalent within ±5%) / H2 (≈0.45); do not hard-fail on H2. Skipped in CI.
- [ ] 4.2 Run locally: a downstream-plane sweep (x ≈ 7–8, outside the recirculation bubble) reporting
      wake-survey Cd; compute the **confinement offset** `1+kβ` (β=0.79%, k≈2–4) and the isolated-
      equivalent Cd; compute the **steadiness gate** from `plt09900`/`plt10000` (require |unsteady| < 5%
      of |drag|, else void). (Stage-2 full-box + per-term breakdown only if Stage 1 is band-edge ambiguous.)
- [ ] 4.3 Classify **H1 / H1′ / H2 / void**. Write the verdict + both grids' Cd + isolated-equivalent +
      the documented `+3–6%` setup offset to a new `## 8. Stage-1 result` addendum in
      `docs/aerodynamics_validation/t1a-findings.md`; update `examples/flow_past_sphere/RESULTS.md`
      (replace "Investigation Required" with the resolved finding) and have RESULTS.md **cite t1a-findings
      §8 as the single source** for the number.

## 5. Stage-2 full-box KATs (build only if Stage 1 is band-edge ambiguous or for published rigor)

- [ ] 5.1 **(tests, deferred)** `::test_viscous_per_face_transpose` (`u=(by,cx,0)`, `ρ≠1`, per-face
      `μ(b+c)·A`); `::test_viscous_net_poiseuille` (`u_x=U0+(g/2μ)y(H−y)`, net `−g·H·L_x·L_z`);
      `::test_convergence_order` (fitted order ∈[1,2], CV faces fixed under refinement);
      `::test_anisotropic_dx`; `::test_offcenter_cv_box`; `::test_nan_in_cv_raises`;
      `::test_cv_size_sweep_plateau` (compact-deficit field; spread <1%); `::test_pressure_curl_free_path`.
      (Verifies the two viscous scenarios, convergence, plateau, NaN.) Wire the full 6-face path through
      `control_volume_drag` (already drafted in 1.4) only when this stage is triggered.

## 6. Conditional downstream reconciliation

- [ ] 6.1 **(if H1/H1′) CC-V5 — supersede every live "~60% low / under investigation" copy** (≥5 exist):
      `add-apex-benchmarking/proposal.md:63`, `tasks.md:31` (**2.1.5**; 2.2.4 is an unrun to-do — mark
      superseded, don't "fix a claim" there), `specs/apex-benchmarks/spec.md` (on that change's archival),
      `benchmarks/METHODS.md:242` + its `extract_sphere_cd` snippet (`METHODS.md:210-216`),
      `examples/heaving_ellipsoid/RESULTS.md:91`. Record that the **submitted APEX PDF is immutable**.
- [ ] 6.2 **(if H1/H1′) CC-V6 — re-caption (never regenerate)** the frozen corpus + ~2.4× origin:
      `examples/prelim_sweep/README.md:303,323`, `force_surrogate/evidence_figure.py`,
      `examples/flapping_wing/RESULTS.md:116-118`, `docs/force_surrogate/roadmap.md:95,152`, and note
      whether `openspec/specs/force-surrogate/spec.md` needs re-captioning. `F_ref≈624.8` unaffected.
- [ ] 6.3 **(if H2)** Instead: record the H2 verdict + deferred solver-remediation plan (t1a-findings §6
      a/b/c) in the roadmap T1b row; `xfail`/relax test 4.1; do **not** edit the frozen corpus or run
      anything.

## 7. Close-out

- [ ] 7.1 `uv run ruff check src/ tests/` + `uv run ruff format --check src/ tests/` +
      `uv run pytest -m "not gpu and not requires_plotfile"` green; coverage on `stress_integral.py`;
      `openspec validate add-sphere-stress-cd --strict`.
- [ ] 7.2 Update the roadmap T1b row with the outcome (H1/H1′/H2/void); write `handoff_t2a.md`.
- [ ] 7.3 `/pre-merge-check`; PR → `/review-pr` → merge to `docs/aerodynamics-validation-roadmap`; then
      `/openspec:archive add-sphere-stress-cd`.

## Suggested commit sequence (CI-safe; PR targets the roadmap branch like T1a's #27)

1. `test(sphere-cd): register requires_plotfile marker + conftest auto-skip` (task 0)
2. `feat(sphere-cd): Stage-1 wake-survey core + gating KATs` (tasks 1)
3. `feat(sphere-cd): yt covering_grid adapter (tuples, halo, fp64, aligned)` (tasks 2)
4. `feat(sphere-cd): method="surface_stress" in extract_sphere_cd (back-compat)` (tasks 3)
5. `test(sphere-cd): literature Cd classification (requires_plotfile, local)` (task 4.1)
   — run 4.2 locally, classify —
6. `docs(T1b): record <H1|H1′|H2|void> result + confinement offset (§8 + RESULTS)` (task 4.3)
7. H1/H1′: `docs: reconcile CC-V5/CC-V6 to resolved sphere-Cd factor` (tasks 6.1–6.2)
   · H2: `docs(T1b): record H2, defer remediation, xfail 4.1` (task 6.3)
   · (only if ambiguous) `feat(sphere-cd): Stage-2 full CV box + <1% KATs` (task 5.1)
8. `docs(roadmap): tick T1b row + handoff_t2a` (task 7.2)
