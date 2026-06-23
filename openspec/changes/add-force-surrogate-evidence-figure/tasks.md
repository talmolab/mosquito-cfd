# Tasks — Force-surrogate evidence figure (PR6)

TDD throughout: each task writes the test(s) **first** (red), then the minimal implementation
(green), then refactor. All tests are cluster-free (CC-2) — no RunAI, no GPU, no plotfiles, no
`train` group. Tracks GitHub issue #24; closes roadmap row 6.

> **Deviation (post-implementation, PI review): Sane–Dickinson reference, not overlay.** Tasks 3 and 5
> below describe *overlaying* the quasi-steady baseline on the CF_z panel (the original CC-4 plan). On
> review the overlay proved misleading at the coarse grid — the uncalibrated QS model overshoots the
> CFD lift ~2.3×, a gap **dominated by the ~2.4× diffused-IB underestimate**, so an overlay mostly
> re-displays the IB bias rather than surrogate skill, and the analytic loops dominated the panel. The
> baseline is now **computed as a reference** (overshoot factor + RMSE in the sidecar, one honest
> caption sentence) and **not drawn** on the scatter; the figure gained a config→color legend. See
> proposal "Why a quasi-steady *reference* instead of the CC-4 baseline *overlay*?" + design D2. The
> baseline *formula* + CC-3 tasks (3.1–3.3) are unchanged; the overlay-specific assertions in 5.1–5.3
> were replaced by "no baseline series + config legend" tests.

## 1. Fixtures (CC-2)

- [x] 1.1 Add a tiny synthetic **predictions** fixture (2 holdout configs `s35_f085_p45` +
  `s55_f115_p45`, a handful of timesteps each; columns
  `config_name, time, phase, wingbeat, CF_{x,y,z,mx,my,mz}_{true,pred}` — **no `split` column**, matching
  the committed parquet) and a tiny **metrics dict** fixture (`per_target.<c>.rmse`, `aggregate`,
  `config_resolved.<c>.config_mean_r2` — includes a **`null`-sentinel** and a **negative**
  `config_mean_r2`, and an `inference` block). **Why in-code, not a committed `tests/fixtures/`
  parquet:** built in-code as `_toy_predictions()` / `_toy_metrics()` in the test module, matching the
  established `_toy_dataset()` convention in `test_force_surrogate_train.py` — same cluster-free
  tiny-synthetic intent (CC-2), no committed binary fixture to churn. A test writes the toy parquet to
  `tmp_path` when a file path is needed.
- [x] 1.2 Test (red→green): the fixtures load and match the schema of the **already-committed PR5
  inputs** `examples/prelim_sweep/surrogate/{holdout_predictions.parquet, metrics.json}` (column set;
  the nested `config_resolved.<c>.config_mean_r2` / `per_target.<c>.rmse` / `inference.latency_ms`
  key paths; and that **neither** carries a `split` column) — pinned against the PR5 artifacts that
  exist today, NOT against the task-9 figure outputs, so this test is green from commit 1.

## 2. Module skeleton + config_name → kinematics parsing

- [x] 2.0 Implement the `evidence_figure.py` module header: force the **Agg backend**
  (`import matplotlib; matplotlib.use("Agg")` **before** `import matplotlib.pyplot`, matching
  `examples/*/generate_*.py`); google-style module + function docstrings (ruff `D` is enforced on
  `src/`).
- [x] 2.1 Test first (parametrized): `parse_config_name("s45_f115_p60") == (phi=45.0, f_star=1.15,
  pitch=60.0)`; pin the decimal convention explicitly (`f115 → 1.15`, `f085 → 0.85`); negative cases
  each raise `ValueError` — missing field (`s45_f115`), wrong prefix (`x45_f115_p60`), non-numeric
  field (`sXX_f115_p60`), extra fields.
- [x] 2.2 Implement `parse_config_name` in `evidence_figure.py` (minimal).

## 3. Sane–Dickinson baseline (spec: baseline formula + CC-3 single-source)

- [x] 3.1 Test first: `C_L(α)` Dickinson-1999 fit returns known values at α∈{0, α_amp};
  `sane_dickinson_cf_z(phase, f_star, phi_amp, pitch_amp)` equals
  `(cos(2π·phase))²·C_L(α_amp·|cos(2π·phase)|)` on a known `phase` array (floating tolerance).
- [x] 3.2 Test first: the baseline obtains `F_ref`/`U_tip` **only** from
  `compute_force_reference` (CC-3) — spy/patch the helper and assert it is called with the parsed
  `(f_star, phi_amp, r_tip, span, chord)`, and that monkeypatching the helper to return a **sentinel
  `F_ref`** changes the baseline output proportionally (proves no inline re-derivation bypasses the
  helper — the algebraic-cancellation risk in design D2). Mirrors the existing
  `test_generate_all_figures_uses_shared_reference` pattern.
- [x] 3.3 Implement `C_L` fit + `sane_dickinson_cf_z` (computes `F_trans` via the helper's `q_tip·S`,
  divides by `F_ref`).

## 4. Metric read-through + speedup derivation (spec: caption/annotation; speedup)

- [x] 4.1 Test first: `panel_annotation(metrics, "CF_z")` returns the config-resolved R²
  (`config_resolved.CF_z.config_mean_r2`) and RMSE (`per_target.CF_z.rmse`) read from the metrics
  dict (mutate the fixture → output changes; no literals). A missing key raises a clear error naming
  it. A `null`-sentinel R² renders as "n/a"; a negative R² renders verbatim.
- [x] 4.2 Test first (known-answer with **literal** inputs — NOT the tiny fixture's row counts, so
  the targets stay round/non-circular) — **two distinct speedups** (design D4):
  - **Headline throughput speedup** `= inference.throughput_rows_per_s / cfd_rows_per_s`, where
    `cfd_rows_per_s = rows_per_wingbeat(cfg) / CFD_SECONDS_PER_WINGBEAT`; known-answer e.g.
    `5.17e7 / (2000/144) ≈ 3.7e6×`; assert the exact factor AND `> 1000×`; assert the annotation/
    sidecar disclose denominator "coarse-grid A40 CFD", **batch size N=12,535**, that the CFD rate is
    **sequential**, and the **parallelism factor** (≈12,009× = throughput_speedup ÷ latency_speedup).
  - **Secondary latency speedup** `= (CFD_SECONDS_PER_WINGBEAT/rows_per_wingbeat) / (latency_ms/1000)`;
    known-answer `144/2000 / 0.000232 ≈ 310×`; assert it is **NOT** `>1000×` and is never the
    per-wingbeat-÷-per-row mix-up.
  - `rows_per_wingbeat` is **per-config** (`= 1/(f*·dt)` with `dt = constants.DT`; from the parquet's
    per-config `groupby(config_name).size()` — 2353/2000/1738; f* from `parse_config_name`), NOT a
    single constant; assert it varies across configs.
- [x] 4.3 Test first: `build_caption(metrics)` is the **compact** caption — a positive headline
  (per-axis config-resolved R²/RMSE for CF_x/CF_z/CF_my, **built from the fixture values** so mutate →
  caption changes; CF_x/CF_my dominant, CF_y subordinate), a terse "Caveats:" line (aggregate
  waveform-inflated / CF_y R²<0; coarse-grid 64×32×64 / ~2.4× IB / not validated; M_y component +
  issue #1; CF_mx/CF_mz omitted as waveform-only), a terse "Baseline:" line (zero-parameter
  translational Sane–Dickinson, bounds-not-competes), and a `README` pointer — assert each compact
  element is present and that CF_x/CF_my read as dominant over the CF_y tell. (The **full** prose
  disclosures are asserted on the README in task 10.2, not here.)
- [x] 4.4 Implement `panel_annotation`, `compute_speedup` (headline throughput + secondary latency;
  `CFD_SECONDS_PER_WINGBEAT` module constant; per-config `rows_per_wingbeat` from the parquet),
  `build_caption` (all read from artifacts).

## 5. Figure assembly (spec: three panels; CF_my headline; baseline only on CF_z)

- [x] 5.1 Test first (Matplotlib object model, no pixels): `build_figure(predictions, metrics)`
  returns a figure with exactly three scatter axes for CF_x/CF_z/CF_my; each has a 1:1 line; the
  CF_z axis carries **two** labeled series (surrogate + Sane–Dickinson baseline); the moment panel
  label contains "M_y"+"moment" but **not** "pitch moment"; the caption text references issue #1; the
  speedup annotation text contains "coarse-grid" (or "coarse A40") on the denominator and the
  headline factor is the throughput (>1000×) one.
- [x] 5.2 Test first (negative assertions): the Sane–Dickinson baseline label appears on **exactly
  one** axis and that axis is **CF_z** — the CF_my axis carries **no** baseline series; the headline
  moment coefficient is `CF_my` and **no** axis plots a `CF_mx_*` or `CF_mz_*` column; every plotted
  point is a holdout-config point (count == fixture row count per coefficient).
- [x] 5.3 Implement `build_figure(...) -> matplotlib.figure.Figure` (panels, 1:1 lines, baseline
  overlay on CF_z only, per-panel annotations, compact caption, config-distinguished points). Add a
  per-axis **legend** on CF_z so the two series are discoverable via `ax.get_legend_handles_labels()`
  (the object-model accessor the 5.1/5.2 tests key off).

## 6. Artifacts + provenance (spec: committed artifacts; CC-1 digest/timestamp)

- [x] 6.1 Test first: `generate_evidence_figure(..., out_dir, image_digest, timestamp)` writes
  `evidence_figure.png` (≥200 dpi — assert the `savefig` **`dpi` kwarg** via spy, not by re-reading
  the PNG), `evidence_figure_metrics.json` (per-axis surrogate RMSE, CF_z baseline RMSE, annotated
  config_mean_r2, speedup inputs+units; written **LF-newline UTF-8** like `write_units_sidecar`), and
  `run_metadata.json` (git, supplied digest, verbatim timestamp, hash of consumed parquet+metrics).
- [x] 6.2 Test first: a mutable tag (no `sha256:`) raises `ValueError` (via
  `capture_surrogate_run_metadata`/`validate_image_digest`); the artifacts are not written.
- [x] 6.3 Test first: degenerate inputs are rejected before any artifact is written — an **empty**
  predictions parquet and a **single-config** parquet each raise a clear error; a metrics dict
  missing `config_resolved`/`inference`/a panel `per_target` raises naming the missing key.
- [x] 6.4 Implement `generate_evidence_figure` orchestration + `evidence_figure_metrics.json` writer,
  reusing `capture_surrogate_run_metadata` unchanged — pass the **predictions parquet** as its single
  `inputs_file` and record the **metrics.json** SHA256 + seeds via `extra=` (the helper hashes only
  one `inputs_file`; this folds both consumed inputs into one auditable metadata file). **Export the
  public entrypoint(s) from `force_surrogate/__init__.py` `__all__` here** (so tasks 6–8 import via the
  package surface, not a deep path).

## 7. Force-only scope guard (spec: CC-6)

- [x] 7.1 Test first: the public entrypoint signature neither accepts nor requires a
  plotfile/field path; it requires only the predictions parquet + metrics.json paths.
- [x] 7.2 Confirm (no new code) — adjust signature if the guard test fails.

## 8. CLI driver

- [x] 8.1 Test first: `scripts/make_evidence_figure.py` argument parsing (inputs, out-dir,
  `--docker-digest`, `--timestamp`) delegates to the tested library entrypoint (mock the library).
- [x] 8.2 Implement the thin CLI driver (mirrors `scripts/extract_forces.py`).

## 9. Generate + commit the real figure (operator step)

- [x] 9.1 Run the CLI against the committed `examples/prelim_sweep/surrogate/{holdout_predictions.parquet,
  metrics.json}` with the PR5 container digest + a supplied timestamp; produce
  `examples/prelim_sweep/figures/{evidence_figure.png, evidence_figure_metrics.json, run_metadata.json}`.
- [x] 9.2 Eyeball the PNG: 3 panels, CF_z baseline overlay visibly worse than surrogate, caption +
  speedup present; confirm `evidence_figure_metrics.json` numbers match the figure.
- [x] 9.3 Commit the three artifacts.
- [x] 9.4 (Optional, lands **with** 9.3 — never earlier) A committed-figure contract test pinning
  `examples/prelim_sweep/figures/evidence_figure_metrics.json` (keys + that its numbers match what
  the figure code recomputes from the committed inputs), mirroring the existing
  `test_committed_units_contract_matches_module` precedent. Must not be introduced before the
  artifact exists, or it is red on every prior commit. Do **not** pin the `run_metadata.json`
  git-hash field (it records the generation-time parent commit, not the merge commit).

## 10. Wire-up, docs

- [x] 10.1 Add a `tests/fixtures/` README note + an RTM/comment mapping each test to its spec
  scenario (project convention: tests cite their OpenSpec scenario). (Package `__all__` export was
  done in task 6.4.)
- [x] 10.2 Add a **Figure (`figures/`)** section to **`examples/prelim_sweep/README.md`** (the corpus's
  canonical narrative doc, matching its existing Dataset/Surrogate tables): (a) a table listing the
  three artifacts with a one-line description each — including the `run_metadata.json` provenance
  fields (git commit, pinned digest, caller timestamp, inputs hash), in the same one-line style the
  README uses for the dataset/surrogate `run_metadata.json`; and (b) the **full honesty discussion**
  that the compact on-figure caption only points to — the issue-#1 axis caveat, the CF_mx/CF_mz
  exclusion reason, the baseline's omitted-terms / symmetric-rotation / stroke-plane-normal-vs-lab-z /
  zero-parameter-unfitted caveats, the coarse-grid / ~2.4× / not-validated framing, and the speedup
  batch-size (N=12,535) + sequential-CFD decomposition (incl. the ~310× per-evaluation floor). Defer
  all metric *numbers* to `evidence_figure_metrics.json`/`metrics.json` (no re-tabulation — README
  drift-avoidance). Do **not** create or target a root `RESULTS.md` (it does not exist).
- [x] 10.3 Test first (cluster-free): assert `examples/prelim_sweep/README.md` contains the full
  disclosure set (so honesty stays test-enforced off the PNG — spec scenario "On-figure caption is
  compact; full disclosures live in the README").

## 11. Pre-merge

- [x] 11.1 `/pre-merge-check`: ruff lint+format clean, full cluster-free test suite green, coverage
  reported on the new module.
- [x] 11.2 Reconcile implementation vs. this proposal/design/spec (step 9 of `/new-feature`); update
  the proposal docs with a `### Why N instead of M?` note for any deviation; file a follow-up issue
  for any bug worked around.
- [x] 11.3 `openspec validate add-force-surrogate-evidence-figure --strict` passes.
