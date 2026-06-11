# Tasks — add-force-surrogate-dataset

TDD throughout: each implementation task writes its failing tests **first** (citing the spec
scenario), then the minimal code to pass. **Commit each tests-first + implementation pair as a
single commit — never push the intermediate "tests-only" state** (CI's test job fails on exit 1;
only exit 5 = *no tests collected* is tolerated, NOT *failing tests*). All tests are cluster-free
(CC-2): they run against the committed `tests/fixtures/synthetic_ib_particle.csv` + a manifest (the
committed `sweep_manifest.json` for corpus-shaped checks, or a **synthetic single-config manifest**
the test constructs for the validated-point/boundary checks), with no cluster/GPU/plotfiles.

## 1. Dependency + fixture groundwork

1. [x] Add `pyarrow` to `pyproject.toml [project.dependencies]`; run `uv sync` to regenerate `uv.lock`; **commit `uv.lock` in this change** and prove consistency with **`uv lock --check`** (a same-machine `uv sync --frozen` right after `uv sync` trivially passes and is false confidence). Required or `uv sync --frozen` breaks in CI's test job + `Dockerfile.python` + `Dockerfile.fp64` (D4/D11).
2. [x] Extend `tests/fixtures/synthetic_ib_particle.csv`: populate the currently-zero `Mx,My,Mz` columns with round multiples of 100 (exact-decimal coefficients under `M_ref=100`), written in the same bare-int style as the forces. **Change values only — do NOT reorder, add, remove, or retype any column** (the existing `test_synthetic_fixture_loads` asserts `list(df.columns) == REAL_SCHEMA` exactly). Update `tests/fixtures/README.md` ("all zero except forces **and moments**"; keep the "synthetic, not a real simulation run" disclaimer).
3. [x] Verify the **existing** `tests/test_force_surrogate_fixtures.py` still passes unchanged (it reads only `Fx/Fy/Fz`), confirming the fixture extension is non-breaking.

## 2. Single-source moment normalization (`normalization.py`)

4. [x] **Tests first** (`tests/test_force_surrogate_normalization.py` additions), citing spec *Single-source moment normalization*:
   - `m_ref ≈ 624.79` at the validated point, `rtol=1e-3`; `length` field equals supplied chord (scenario *Moment reference at the validated point*).
   - `m_ref` scales as **chord²** (chord enters via both `area` and `L`, so `chord=2 → 4×`); **and at a non-unit chord (2.0), `m_ref == compute_force_reference(same args).f_ref * chord` exactly** — proves the moment helper reuses the force `q_tip`/`area`, not a divergent copy (the equality is trivial at chord=1.0) (scenario *Moment reference scales with the chord length scale and reuses the force reference*).
   - `cf_m* = M*/m_ref` element-wise, shape-preserving incl. scalar; `m_ref<=0` raises; mismatched `mx/my/mz` shapes raise; empty→empty; NaN propagates.
   - `compute_moment_coefficient(fixture Mx/My/Mz, 100.0)` returns the exact known decimals.
5. [x] Implement `MomentReference`, `MomentCoefficients`, `compute_moment_reference`, `compute_moment_coefficient` in `normalization.py`, reusing the `compute_force_reference` formulas for `q_tip`/`area` (no second copy; CC-3). **Re-export the four new symbols from `force_surrogate/__init__.py` in this same commit**; assert importable. Run green.

## 3. Dataset extraction (`dataset.py`)

6. [x] **Tests first** (`tests/test_force_surrogate_dataset.py`), citing spec *Tidy force-coefficient dataset extraction*. Construct test inputs cluster-free in `tmp_path`:
   - **Corpus-shaped checks** (reuse committed `sweep_manifest.json`, point configs at the fixture CSV): `N×T` rows one per (config×timestep); columns exactly the documented 22-col schema; `split` carried through verbatim; a complete build returns `dropped == []` (scenarios *One row per…*, *Columns are…*, *Held-out split…*, *Complete build reports no drops*).
   - **Validated-point check** (build a **synthetic single-config manifest** `{stroke_amp_deg=70.0, frequency_fstar=1.0, pitch_amp_deg=45.0}` — no committed config is at φ=70): assert `CF_x == Fx / compute_force_reference(f_star=1.0, phi_amp_deg=70.0, r_tip=R_TIP, span=SPAN, chord=CHORD, rho=RHO).f_ref` and `CF_mx == Mx / compute_moment_reference(...).m_ref` (+ y/z) — **ratio** form, not round literals — with a numeric anchor `f_ref == pytest.approx(624.79, rel=1e-3)` (scenario *Coefficients use the single-source per-config normalization*).
   - **Phase/wingbeat** (same f*=1.0 synthetic config on the fixture, `time = 0,.25,.5,.75,1.0`): exact `phase = [0,.25,.5,.75,0.0]`, `wingbeat = [0,0,0,0,1]`, pinning the `time·f*=1.0 → phase=0.0, wingbeat=1` boundary; no rows dropped (scenario *Phase and wingbeat tag every timestep*).
   - **Name-based parse** (write a **column-reordered** copy of the fixture into `tmp_path`): identical coefficients (scenario *Name-based parse…*).
   - **Empty vs missing** (write a **header-only** CSV `(tmp_path/'empty.csv').write_text(','.join(REAL_SCHEMA)+'\n')`): the empty-but-present config contributes **zero rows, no error**; a config whose path **does not exist** raises `ValueError` naming it (default `allow_missing=False`) — distinguished by **path existence**, not row count (scenarios *Empty force CSV…*, *Missing configuration CSV rejected*).
   - **allow_missing**: `build_dataset(..., allow_missing=True)` with one path absent emits the present configs and returns `(df, dropped)` with the skipped name in `dropped` (scenario *Opt-in allow_missing…*).
7. [x] Implement `build_dataset(manifest_path, csv_paths, *, allow_missing=False) -> tuple[DataFrame, list[str]]` in `dataset.py`: name-based CSV read against the 29-col schema, manifest join, per-config `F_ref`/`M_ref`, `phase`/`wingbeat`, hard-fail/`allow_missing`. **Re-export `build_dataset` from `__init__.py` in this same commit.** Run green.
8. [x] **Tests first** for `write_dataset` + units sidecar + parquet round-trip (into `tmp_path`, never committed — D10), citing spec *Dataset units sidecar*:
   - `dataset.units.json` round-trips via `read_units_sidecar`, maps each measured column correctly, includes **all 18 measured columns** (inverse check) **and** omits the non-measured `config_name/split/index/wingbeat` (scenarios *Units sidecar validates…*, *Non-measured columns omitted*).
   - `write_dataset` then `pandas.read_parquet` returns an **equal frame**: assert **float64** on coefficient/raw columns, **int64** on `wingbeat`, compare string columns (`config_name/split`) with `check_dtype=False` (pandas-3.0 `object`↔`string[pyarrow]`), `reset_index(drop=True)` both frames. **No byte-equality** assertion.
9. [x] Implement `write_dataset(df, parquet_path, units_path)` (parquet + `write_units_sidecar` from a static `_DATASET_UNITS` constant). **Re-export `write_dataset` from `__init__.py` in this same commit.** Run green.

## 4. Provenance (CC-1) — library level

10. [x] **Tests first** citing spec *Dataset build provenance*: feeding `build_dataset(..., allow_missing=True)`'s returned `dropped` into `capture_surrogate_run_metadata(..., extra={"dropped_configs": dropped})` records the names at **top-level** `metadata["dropped_configs"]` (NOT `metadata["extra"]`, because `capture_run_metadata` does `dict.update(extra)` — verified `metadata.py:211-212`); digest + caller timestamp recorded; mutable tag/missing digest raises (inherited). Implement any small `dataset.py` helper needed; run green.

## 5. Force-only guard (CC-6)

11. [x] **Test** citing spec *Force-only dataset scope guard*: `build_dataset` consumes only CSV + manifest (no plotfile path param), runs with no plotfile present.

## 6. Thin driver + smoke test (driver provenance wiring lives HERE, with the driver)

12. [x] **Driver smoke test first** (mirror PR2's `test_driver_smoke` via `importlib.util.spec_from_file_location`): run `main()` into `tmp_path` with `--input-dir` at a fixture-derived tree + an **obviously-synthetic sentinel** `--docker-digest sha256:0000…0000` + a fixed `--timestamp`; assert exit 0 and that `dataset.parquet`/`dataset.units.json`/`run_metadata.json` are written and re-readable. **Add a second smoke invocation with `--allow-missing` and one config's CSV absent**, asserting the written `run_metadata.json` has **top-level** `dropped_configs == [<name>]` (exercises the driver's `extra=` wiring through `main()`, not just the library). Then implement `scripts/extract_forces.py` (no logic): argparse `--manifest --input-dir --csv-name --out --units --metadata --docker-digest --timestamp [--allow-missing]`; resolve `{config_name -> input-dir/<name>/IB_Particle_1.csv}`; `df, dropped = build_dataset(...)`; `write_dataset(df, ...)`; `capture_surrogate_run_metadata(docker_image_digest=..., timestamp=..., extra={"dropped_configs": dropped})`; write metadata. Google-style docstring. (This folds the former "wire provenance into the driver" step in with the driver it depends on — the driver must exist before it can be wired.)

## 7. Committed artifact (contract only) + docs

13. [x] **Commit `examples/prelim_sweep/dataset.units.json` ONLY** (the pure `_DATASET_UNITS` contract — no fabricated physics; D10/option b). Do **NOT** commit `dataset.parquet`/`run_metadata.json`. Add `*.parquet binary` to `.gitattributes` **inside the existing "Binary files" block** (beside `*.png binary`), as forward-config for PR3's real parquet.
14. [x] Add a **dataset section to `examples/prelim_sweep/README.md`**: (a) the 22-column schema **by reference** to the spec (normative) + the committed `dataset.units.json`, not re-listed; (b) the `phase`/`wingbeat` semantics with the explicit **"filter to the converged last beat (wingbeat ≥ 1) yourself — the extractor keeps the startup transient on purpose (with the current 2-beat corpus)"** caveat; (c) the one-line regenerate command (driver against PR3's corpus). Note the committed `dataset.units.json` is the schema contract while the data lands with PR3.

## 8. Integration: CI, lint, docs

15. [x] Widen **both** `.github/workflows/ci.yml` ruff lines (`check` and `format --check`) to include `scripts/` (D9), and extend the load-bearing-path comment to name `scripts/`. **Must land with/after task 12's committed `scripts/extract_forces.py`** (empty dir → E902 on CI checkout; a local `ruff check scripts/` on the empty dir is a false green). Do **not** add any `.py` under `examples/prelim_sweep/` (keeps that lint path green).
16. [x] Refresh `openspec/project.md`: add `force_surrogate/` (one-line description) + `scripts/` to the `src/` tree, and **both `flapping_wing/` and `prelim_sweep/`** to the examples list (both currently missing — stops the drift fully). Add a `scripts/` line to the root `README.md` Directory Structure.
17. [x] Update `docs/force_surrogate/roadmap.md`: row #4 and the Inputs/Outputs `dataset.parquet` bullet to record "**data + provenance committed when PR3's corpus lands**; PR4 commits the tested extractor + driver + the `dataset.units.json` contract" (traceability for the D10 deviation). (The status checkbox flips on merge via `/cleanup-merged`, not here.)
18. [x] `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/` and `ruff format --check` clean; `uv run pytest` green; `uv run pytest --cov` reports coverage for the new modules.

## 9. Validation

19. [x] `openspec validate add-force-surrogate-dataset --strict` passes.
20. [x] Re-read `proposal.md`/`design.md`/`spec.md` vs the implementation; reconcile any drift (update docs + add a `### Why N instead of M?` note if the implementation had to deviate).
