## Why

The Track B force-surrogate program ([docs/force_surrogate/roadmap.md](../../../docs/force_surrogate/roadmap.md), row #4; GitHub issue [#6](https://github.com/talmolab/mosquito-cfd/issues/6)) needs the **kinematics(+phase) → force-coefficient dataset** that PR5 trains on and PR6 plots. PR1 (`add-force-surrogate-foundation`, #2) published the single-source force normalization + cluster-free fixtures; PR2 (`add-force-surrogate-sweep-config`, #5) published the 27-config corpus + `sweep_manifest.json` (kinematics, `reynolds`, train/holdout `split`). What is still missing is the **extractor** that turns each config's IB-particle force CSV into normalized coefficients joined to its kinematics, emitted as one tidy `examples/prelim_sweep/dataset.parquet` (+ units sidecar). Without it there is no training target and no evidence figure.

This is the **force-only** dataset (design §9, CC-6): forces come from the IB-particle CSV only — **no plotfile / velocity-field reading**, which sidesteps the velocity-in-plotfiles bug entirely (`amr.plot_int = -1` throughout). It is **local and cluster-free** (CC-2): PR4 is built and fully tested against the committed fixtures **before** PR3's real corpus exists, so the cluster (PR3) and local (PR4) tracks proceed in parallel once PR1+PR2 land.

## What Changes

### Extends capability: `force-surrogate`

- **New single-source moment normalization in `src/mosquito_cfd/force_surrogate/normalization.py`** (CC-3, sibling to the published force helpers — never re-derived inline):
  - `compute_moment_reference(f_star, phi_amp_deg, r_tip, span, chord, rho=1.0) -> MomentReference` — `m_ref = q_tip · area · chord`, with `q_tip` and `area` from the **same formulas** as `compute_force_reference` (`u_tip_max = 2π·f*·radians(φ)·r_tip`, `q_tip = ½ρu_tip²`, `area = π/4·span·chord`). The moment length scale is **`L = chord`** (decision D1). Regression-locked: `m_ref ≈ 624.79` at the validated point (`f*=1.0, φ=70°, r_tip=3, span=3, chord=1, rho=1`) at `rtol=1e-3` — numerically equal to `F_ref` because `L=1.0`, but a **conceptually distinct, parameterized** helper so a future non-unit chord stays correct.
  - `compute_moment_coefficient(mx, my, mz, m_ref) -> MomentCoefficients(cf_mx, cf_my, cf_mz)` — element-wise `M*/m_ref`, mirroring `compute_force_coefficients`' guards: raises `ValueError` on `m_ref <= 0` or mismatched `mx/my/mz` shapes; empty → empty; NaN propagates.
- **New module `src/mosquito_cfd/force_surrogate/dataset.py`** (pure, no cluster/GPU/plotfiles):
  - `build_dataset(manifest_path, csv_paths, *, allow_missing=False) -> tuple[pandas.DataFrame, list[str]]` — for each config in `sweep_manifest.json`, reads its IB-particle CSV **name-based** (the 29-col schema), joins the manifest's kinematics + `reynolds` + `split`, computes the **per-config** `F_ref`/`M_ref` (via the PR1 helper, with `f_star=frequency_fstar`, `phi_amp_deg=stroke_amp_deg`, and the `R_TIP/SPAN/CHORD/RHO` constants) → `CF_x/CF_y/CF_z` and `CF_mx/CF_my/CF_mz`, and tags each timestep with `phase = (time·f*) mod 1 ∈ [0,1)` and integer `wingbeat = floor(time·f*)`. One row per **(config × timestep)**. Returns the frame **and** the list of any configs dropped under `allow_missing` (the frame alone has no channel to surface dropped names — see design D6).
  - `write_dataset(df, parquet_path, units_path) -> None` — writes the parquet and the `dataset.units.json` sidecar via PR1's `write_units_sidecar`.
- **Thin driver `scripts/extract_forces.py`** — resolves each config's CSV from a configurable `--input-dir` + filename template (default: per-config subdir named by the manifest `name`, file `IB_Particle_1.csv` — IAMReX's actual output name), calls the library, and emits the committed artifacts. All logic lives in the tested module.
- **`__init__.py`** re-exports the new public API (`compute_moment_reference`, `MomentReference`, `compute_moment_coefficient`, `MomentCoefficients`, `build_dataset`, `write_dataset`, `build_run_metadata`).

### Resolved decisions (the CC-7-equivalents for PR4 — see `design.md`)

- **D1 — Moment length scale `L = chord = 1.0`.** Standard pitch-moment convention; matches the chord factor in `S`. New single-source helper, regression-locked.
- **D2 — Carry all three moment coefficients `CF_mx/CF_my/CF_mz`; defer the single headline `CF_m` pick to PR6.** IAMReX writes `Mx/My/Mz` as **`r × F` about the body center in the LAB frame** ([`DiffusedIB.cpp:798–801`](https://github.com/talmolab/IAMReX)), not a body-frame pitch moment; the repo's own axis labels are internally inconsistent (issue [#1](https://github.com/talmolab/mosquito-cfd/issues/1) tracks a kinematics-axis refactor). Carrying all three loses zero information; PR6 designates the headline axis with the figure in hand.
- **D3 — Keep all timesteps; tag `phase` + integer `wingbeat`.** No silent startup-transient masking (the exact trap behind issue [#4](https://github.com/talmolab/mosquito-cfd/issues/4), where the figure script prints "(t>0.1)" but masks `t≥0.05`). PR5/PR6 filter to the converged last beat **explicitly**.
- **D4 — Add `pyarrow` dependency.** `dataset.parquet` needs a parquet engine; pandas 3.0 pulls none (confirmed: `pyarrow`/`fastparquet` both absent). Add `pyarrow` to `[project.dependencies]` and `uv sync` so `uv.lock` stays frozen for CI's `uv sync --frozen`.
- **CSV contract** — library takes explicit per-config CSV paths (testable against the fixture); the driver resolves the real layout (PR3 aligns its output to the driver's convention).
- **Missing corpus** — **hard-fail** (`ValueError` naming the missing config) by default; opt-in `allow_missing=True` skips-with-logged-warning **and records the dropped configs** in the run metadata (no silent caps).
- **Raw moments** — carry raw `Mx/My/Mz` alongside the coefficients (traceability), parallel to raw `Fx/Fy/Fz`.

### Output schema (22 columns, one row per config × timestep)

`config_name, index, time, phase, wingbeat, stroke_amp_deg, frequency_fstar, pitch_amp_deg, reynolds, split, Fx, Fy, Fz, Mx, My, Mz, CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`

The **normative** copy of this list is the spec scenario *"Columns are the documented schema"*; design.md and the `prelim_sweep` README reference it (the README leans on the `dataset.units.json` contract) rather than re-listing, so the schema has one source of truth.

`dataset.units.json` (via `write_units_sidecar`): coefficients / `phase` / `time` / raw forces+moments / `reynolds` → `dimensionless`; `stroke_amp_deg`/`pitch_amp_deg` → `deg`; `frequency_fstar` → `dimensionless (f*)`. **No new `UNITS_VOCABULARY` entry** (CC-5 — `phase`, `time`, coefficients are all dimensionless). String/bookkeeping columns (`config_name`, `split`, `index`, `wingbeat`) are omitted from the sidecar, mirroring PR2's manifest-units convention.

### Provenance (CC-1)

The dataset build emits a `run_metadata.json` via PR1's `capture_surrogate_run_metadata` (requires a pinned `sha256:` container digest — the dataset is downstream of the PR3 container run — and a **caller-supplied** timestamp). Under `allow_missing=True`, the names returned by `build_dataset` are passed as `extra={"dropped_configs": [...]}`; because `capture_run_metadata` merges `extra` via `dict.update`, they land at the **top level** of the metadata under `dropped_configs` (not nested under `extra`), so a short corpus is never silent.

### Why no committed dataset artifact (scientific honesty — decision D10)

PR3's real corpus does not exist yet, so the only data PR4 could extract is the **synthetic** test fixture (round forces, not physics). Committing a `dataset.parquet` + `run_metadata.json` built from it into `examples/prelim_sweep/` would plant an artifact that **looks** like real CFD output, and `capture_surrogate_run_metadata` *requires* a real `sha256:` digest a fixture build never legitimately has (manufacturing false provenance). **So PR4 commits the schema contract but not the data:**
- **Commit `examples/prelim_sweep/dataset.units.json`** — the pure column→unit map (from a static `_DATASET_UNITS` constant, like PR2's `_MANIFEST_UNITS`). It carries **no fabricated physics** (no `reynolds`/`CF_*` values, no digest), so it can't masquerade as CFD output, yet gives PR5 a committed, `read_units_sidecar`-validatable contract to develop against.
- **Do NOT commit** `dataset.parquet`/`run_metadata.json` — the data + provenance only become honest once PR3's corpus is run through the committed driver (with the genuine `:fp64` digest).

The full schema lives in the spec (normative) + a `prelim_sweep/README.md` dataset section (columns via the units sidecar + spec pointer, the `phase`/`wingbeat` semantics and the "filter to the converged last beat yourself" caveat, and the one-line regenerate command). Tests generate the parquet into `tmp_path` and validate round-trip — never committed. *(This is a deliberate deviation from the literal roadmap/issue wording "OUTPUT: dataset.parquet" — the roadmap row #4 + Output bullet are updated to "data committed when PR3's corpus lands; PR4 commits the extractor + units contract." User-confirmed at approval.)*

### Fixture extension (CC-2)

`tests/fixtures/synthetic_ib_particle.csv` currently has **zero** `Mx/My/Mz`, so it cannot regression-lock a nonzero moment coefficient. Populate its `Mx/My/Mz` columns with **round multiples of 100** (exact-decimal coefficients under a round `M_ref=100`), and update `tests/fixtures/README.md`. PR1's existing fixture test reads only `Fx/Fy/Fz`, so it stays green.

## Impact

- **Spec:** `force-surrogate` capability gains 5 requirements (moment normalization helper; tidy dataset extraction; dataset units sidecar; dataset-build provenance; force-only dataset guard).
- **New code:** `src/mosquito_cfd/force_surrogate/dataset.py`, `normalization.py` additions, `scripts/extract_forces.py`, `tests/test_force_surrogate_dataset.py`, additions to `tests/test_force_surrogate_normalization.py`; `__init__.py` re-exports.
- **Dependencies:** add `pyarrow` to `pyproject.toml [project.dependencies]`; `uv sync` regenerates `uv.lock`, which **must be committed in this change** (prove with `uv lock --check`) or `uv sync --frozen` breaks in **all three** places that run it: CI's test job, `docker/Dockerfile.python`, **and** `docker/Dockerfile.fp64` (the `--frozen` mismatch fails even the FP64 image, which never imports pyarrow). pyarrow consequently ships into the `:python` post-processing image (intended — that image can read the parquet; `:fp64`/`:fp32` runtime is unaffected, only their builds gate on the lock). See design D11.
- **Fixture:** `tests/fixtures/synthetic_ib_particle.csv` gains nonzero `Mx/My/Mz` (values only — column order/count/dtype unchanged, so the existing exact-`REAL_SCHEMA` fixture test stays green); `tests/fixtures/README.md` updated.
- **Committed artifacts:** `examples/prelim_sweep/dataset.units.json` **only** (the pure schema/units contract — no fabricated physics) — see *Why no committed dataset artifact* (D10). The data + provenance (`dataset.parquet`/`run_metadata.json`) are **not** committed; tests generate the parquet into `tmp_path` only. The real data lands when PR3's corpus is run through the driver.
- **`.gitattributes`:** add `*.parquet binary` (currently absent) so a *future* committed parquet (PR3+) is never EOL-normalized by the `* text=auto` heuristic.
- **CI (`.github/workflows/ci.yml`):** widen **both** ruff `run` lines (`check` and `format --check`) from `src/ tests/ examples/prelim_sweep/` to also include **`scripts/`**. This change must land **with or after** the committed `scripts/extract_forces.py` — git does not track empty dirs, so an absent `scripts/` on CI checkout fails with `E902` (design D9). Extend the load-bearing-path comment to name `scripts/`.
- **Docs:** refresh `openspec/project.md`'s `src/` tree (add `force_surrogate/` — missing since PR1 — and `scripts/`) and examples list (add **both** `flapping_wing/` and `prelim_sweep/` — both missing today), stopping the 2-PR drift; add a `scripts/` line to the root `README.md` Directory Structure; and update `docs/force_surrogate/roadmap.md` row #4 + the Inputs/Outputs `dataset.parquet` bullet to record "data + provenance committed when PR3's corpus lands; PR4 commits the extractor + units contract" (traceability for the D10 deviation).
- **Reuses (no change):** `compute_force_reference`/`compute_force_coefficients`, `write_units_sidecar`/`read_units_sidecar`, `capture_surrogate_run_metadata`, `constants.py` (`R_TIP`/`SPAN`/`CHORD`/`RHO`), `sweep_manifest.json` schema, and the committed `tests/fixtures/` (CC-2).
- **Roadmap:** row #4 status checkbox flips on merge via `/cleanup-merged` (not in this PR).
- **No** CFD-solver or Dockerfile changes (pyarrow enters images only via the lockfile). Force-only; **out of scope** (CC-6): cluster/RunAI runs (PR3), plotfile/velocity-field reading, training (PR5), the evidence figure / single-`CF_m` designation (PR6), RL.
