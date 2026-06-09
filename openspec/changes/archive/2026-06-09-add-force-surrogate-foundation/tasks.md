# Tasks — add-force-surrogate-foundation

TDD-ordered: fixtures (test assets) first, then tests (red), then implementation (green), then
validation. **The suite is RED between §2 and §3. Do NOT push a tests-only commit** — the §2
tests import `mosquito_cfd.force_surrogate`, so a tests-only push is a pytest *collection error*
(exit 1, NOT the tolerated exit-5) and CI goes red. Do red/green locally; land tests +
implementation together (one logical unit). Commit plan in §5.

## 1. Fixtures (committed test assets — CC-2)

- [x] 1.1 Create `tests/fixtures/synthetic_ib_particle.csv` mirroring the **real IB-particle schema exactly** — header (verbatim order): `iStep,time,X,Y,Z,Vx,Vy,Vz,Rx,Ry,Rz,Fx,Fy,Fz,Mx,My,Mz,Fcpx,Fcpy,Fcpz,Tcpx,Tcpy,Tcpz,SumUx,SumUy,SumUz,SumTx,SumTy,SumTz` (29 cols). 5 rows, `time` 0/0.25/0.5/0.75/1.0, body center `X,Y,Z=4,2,4`, all columns 0 EXCEPT `Fx,Fy,Fz` set to exact multiples of a **round reference `F_ref=100.0`** (e.g. `Fx=50→CF_x=0.5`). **No comment line** (real CSVs have the header on row 1); record provenance in `tests/fixtures/README.md` ("synthetic — not a real run"). `.gitattributes` already enforces `eol=lf`. The loader MUST be name-based (`pandas.read_csv`), never positional.
- [x] 1.2 Create `tests/fixtures/micro_sweep.json` — 2-config descriptor over (stroke_amp_deg, frequency_fstar, pitch_amp_deg): `{35,1.0,45}` and `{55,1.0,45}`.

## 2. Tests (write before implementation — TDD red phase)

- [x] 2.1 `test_compute_force_reference_matches_validated` — at f\*=1.0, φ_amp=70°, r_tip=3.0, span=3.0, chord=1.0, ρ=1.0, assert `u_tip_max≈23.029`, `q_tip≈265.17`, `area≈2.3562`, `f_ref≈624.79` with `rtol=1e-3` (values recomputed from the formula; RESULTS.md:100–103 shows the rounded 23.0/265.2/2.356/624.8). (Scenario: "Reference normalization at the validated point".)
- [x] 2.2 `test_compute_force_reference_parameterized` — φ_amp 70°→35° strictly decreases `u_tip_max` and `f_ref`; doubling `f_star` doubles `u_tip_max` (`pytest.approx(2*base, rel=1e-12)`). (Scenario: "Parameterization, not hardcoded".)
- [x] 2.3 `test_compute_force_coefficients` — array Fx/Fy/Fz and F_ref → `cf_* == F*/F_ref` element-wise (`np.testing.assert_allclose`) AND `cf_x.shape == fx.shape`; plus a scalar-input case. Assert per-field; never compare whole `ForceCoefficients` instances with `==`. (Scenario: "Force coefficients".)
- [x] 2.4 `test_compute_force_coefficients_zero_reference_raises` — `F_ref=0.0` raises `ValueError`. (Scenario: "Zero reference rejected".)
- [x] 2.5 `test_compute_force_coefficients_empty_and_nan` — empty array in → `result.cf_x.shape == (0,)` / `.size == 0` (no crash); a NaN force → `np.isnan(result.cf_z)` true at that index (use `np.isnan`/`equal_nan`, never `==` on NaN). Unpack dataclass fields for assertions. (Scenario: "Empty and NaN forces".)
- [x] 2.6 `test_units_sidecar_roundtrip` — `write_units_sidecar`→`read_units_sidecar` via `tmp_path` returns an identical mapping; UTF-8, indent=2. (Scenario: "Units sidecar round-trip".)
- [x] 2.7 `test_write_units_sidecar_rejects_unknown_unit` — unit not in `UNITS_VOCABULARY` raises `ValueError` naming column + unit. (Scenario: "Unknown unit rejected on write".)
- [x] 2.8 `test_read_units_sidecar_rejects_invalid` — (a) non-JSON / non-object file raises `ValueError`; (b) on-disk `units.json` with an out-of-vocabulary unit raises `ValueError`. (Scenario: "Invalid sidecar rejected on read".)
- [x] 2.9 `test_capture_surrogate_run_metadata` — write a `tmp_path` inputs file; call `capture_surrogate_run_metadata(docker_image_digest=<digest>, inputs_file=<tmp>, timestamp="2020-01-01T00:00:00+00:00")`; assert `meta["git"]["commit"]` present (NOT branch — checkout may be detached; tolerate the `{"error":...}` branch defensively), `meta["docker_image"]==<digest>`, `meta["inputs"]["hash"]==hash_file(tmp)`, `meta["timestamp"]=="2020-01-01T00:00:00+00:00"` (caller-supplied ISO string, CC-1). **Also** a digest-only call (`inputs_file=None`) → `meta` has no `inputs` key. (Scenarios: "Run provenance includes container digest", "Caller-supplied timestamp recorded".)
- [x] 2.10 `test_capture_surrogate_run_metadata_requires_digest` — `docker_image_digest=""`/`None` raises `ValueError`. (Scenario: "Missing digest rejected".)
- [x] 2.11 `test_synthetic_fixture_loads` — committed `synthetic_ib_particle.csv` parses name-based (no cluster/GPU), exposes the 29 documented columns in order, and its `Fx,Fy,Fz` normalized by `F_ref=100.0` give the exact known coefficients. (Scenario: "Synthetic fixture is usable cluster-free".)
- [x] 2.12 `test_micro_sweep_fixture_parses` — `micro_sweep.json` parses to 2 configs each with keys `stroke_amp_deg, frequency_fstar, pitch_amp_deg`. (Guards the otherwise-unconsumed-until-PR2 fixture.)
- [x] 2.13 `test_generate_all_figures_uses_shared_reference` — importlib-load `examples/flapping_wing/generate_all_figures.py`; monkeypatch its `compute_force_reference` with a spy; call `plot_f1_forces(tmp_path, <committed forces.csv or fixture>)`; assert the spy was invoked AND the `F_ref` it returned equals `compute_force_reference(F_STAR, PHI_AMP_DEG, R_TIP, SPAN, CHORD, rho=1.0).f_ref`. Cluster-free (yt/pandas lazy-imported; matplotlib Agg). This is the automated guard for CC-3 (a manual run cannot detect a reintroduced inline formula). (Scenario: "Inline normalization is replaced by the shared helper".)
- [x] 2.14 Run `uv run pytest tests/test_force_surrogate_*` — expect FAIL (ImportError). Confirm RED **locally**.

## 3. Implementation (TDD green phase)

- [x] 3.1 `src/mosquito_cfd/force_surrogate/__init__.py` — package marker + `__all__` re-exports (only symbols defined at commit time).
- [x] 3.2 `constants.py` — `SPAN=3.0`, `CHORD=1.0`, `R_TIP=3.0`, `RHO=1.0`, validated reference point (`VALIDATED_PHI_AMP_DEG=70.0`, `VALIDATED_PITCH_AMP_DEG=45.0`, `VALIDATED_F_STAR=1.0`), each with a unit comment, plus a comment distinguishing `R_TIP=3.0` (tip, normalization) from the midspan arm `r_mid=1.5` used for viscosity/Re (RESULTS.md:79). Google-style module docstring.
- [x] 3.3 `normalization.py` — frozen dataclasses `ForceReference`/`ForceCoefficients`; `compute_force_reference(...)`; `compute_force_coefficients(fx, fy, fz, f_ref)` raising `ValueError` if `f_ref == 0`, preserving shape, propagating NaN. Pure, no I/O.
- [x] 3.4 `sidecar.py` — `UNITS_VOCABULARY` (dimensionless set, CC-5); `write_units_sidecar`/`read_units_sidecar` (BOTH validate against vocabulary; UTF-8, indent=2; read raises on malformed JSON); `capture_surrogate_run_metadata(*, docker_image_digest, inputs_file=None, timestamp=None, **kw)` wrapping `benchmarks.metadata.capture_run_metadata` — pass `docker_image=docker_image_digest`, **raise `ValueError` on blank/missing digest**, and since the base has **no** `timestamp` kwarg and hardcodes `datetime.now(UTC)`, **override `meta["timestamp"]` on the returned dict** when a caller timestamp is given (CC-1).
- [x] 3.5 Re-export the public API in `__init__.py`.
- [x] 3.6 **CC-3 single-source refactor:** replace the inline `F_ref` block in `examples/flapping_wing/generate_all_figures.py:236–241` (function `plot_f1_forces`) with a call to `compute_force_reference(F_STAR, PHI_AMP_DEG, R_TIP, SPAN, CHORD, rho=1.0)`. Verify: test 2.13 (automated) **and** a manual run `uv run python examples/flapping_wing/generate_all_figures.py --output-dir <tmp>` **from the repo root** still reports `F_ref≈624.79`.
- [x] 3.7 Run `uv run pytest tests/test_force_surrogate_*` — expect GREEN.

## 4. Validation

- [x] 4.1 `uv run ruff format --check src tests && uv run ruff check src tests` pass (repo uses `ruff format`; line-length per pyproject = 88; google docstrings). *(CI lints `src/` only; we also lint `tests/` locally.)*
- [x] 4.2 `uv run pytest --cov=mosquito_cfd.force_surrogate --cov-report=term-missing` — full suite passes; report coverage.
- [x] 4.3 `openspec validate add-force-surrogate-foundation --strict` passes.
- [ ] 4.4 On merge (NOT in PR1): tick `docs/force_surrogate/roadmap.md` row #1 and `openspec archive add-force-surrogate-foundation` (use the `cleanup-merged` command).

## 6. Implementation deviation (reconciliation)

- **`benchmarks/metadata.py` was modified after all** (proposal said "no change"). `get_git_info` ran `git diff HEAD` with `text=True`, which on Windows decodes git's UTF-8 output as cp1252 and crashed (`UnicodeDecodeError` → `diff.stdout=None` → `len(None)` TypeError) once the working tree contained non-ASCII docs (φ/≈/→). Fixed minimally by adding `encoding="utf-8", errors="replace"` to the `subprocess.run` calls in `get_git_info`/`get_hardware_info`. This is a correctness bugfix (git emits UTF-8), not a workaround — no follow-up debt. See design.md "Why benchmarks/metadata.py changed".

## 5. Commit plan (every pushed commit GREEN)

**Merge method: rebase/merge to preserve the 3 conventional commits** (matches the repo's linear history). Do red/green locally, then land:

1. `feat(force-surrogate): force-coefficient normalization, units sidecar, provenance wrapper + cluster-free fixtures + tests` — `src/mosquito_cfd/force_surrogate/*`, `tests/test_force_surrogate_*`, `tests/fixtures/*`. (tests+impl together — GREEN)
2. `refactor(flapping-wing): source F_ref from force_surrogate.normalization (CC-3)` — `examples/flapping_wing/generate_all_figures.py`. (GREEN; **depends on commit 1** — imports `compute_force_reference`; never cherry-pick/reorder/revert independently of commit 1; verified per §3.6 + test 2.13)
3. `docs(force-surrogate): spec for add-force-surrogate-foundation + roadmap row #1 alignment` — the change's `specs/` + ticked `tasks.md` + roadmap edits (row #1 mentions the refactor; digest follow-up recorded). (GREEN; no runtime refs)

Single reviewable PR for PR1. No RESULTS.md/METHODS.md edit required (PR1 additive + §3.6 closes the DRY loop). Co-Authored-By trailer per harness policy (matches repo history).
