# Design: refresh-v3-validation-figure

## Context

Recomputed from committed data at `e600581` with `mosquito_cfd.force_surrogate.train._r2`, the R²
the generator and the trainer both use (reproduced independently by the proposal review).

| parquet at | CF_x R² | CF_z R² |
|---|---|---|
| `5833ea7` (#23), `c74d69b` (#36) | 0.9931809360713737 | 0.9854005163288705 |
| `e77643c` (#71) | 0.9992649005145562 | 0.9982067504494778 |
| `de081f3` (#126) | 0.9994493298493718 | 0.9983285995529343 |
| `e1ee11d` (#147) = HEAD | 0.9994622131359757 | 0.9980780306252153 |

- The committed summary's `v3` block equals the `c74d69b` row; `metrics.json` `per_target` R² equals
  the HEAD row exactly.
- `c74d69b` multiplied every `CF_*_true` / `CF_*_pred` column by exactly k (bitwise, all 12,535
  rows; CF_x max |·| 1.362 → 4.249). The summary and V3 PNG were committed only in `c74d69b`.
- A full `main()` run into a scratch directory at `e600581` (Windows, the project `uv` environment)
  re-renders V1, V2, V4, V5 byte-identically and reproduces the `v1`, `v2`, `v4`, `v5` blocks
  exactly. `main()` takes about 1 s.

## D1. Panels: van Veen as stored, and the same coefficients on the peak-tip reference

The parquet holds van Veen coefficients: `dataset.py:400` normalizes per configuration with
`compute_force_reference(f_star, stroke, R_GYRATION, ...)`, and `dataset.py:410` applies
`force_on_wing`. `F_ref ∝ (f_star · φ · r)²`, so `F_ref(R_TIP) / F_ref(R_GYRATION) = (R_TIP /
R_GYRATION)²` for every configuration, and one scalar k is exact (over the corpus's 9 distinct (f*, φ) pairs,
|r − k|/k ≤ 4.3e-16). k is computed as today, from `compute_force_reference` at (1, 70).

- Van Veen panel: `(y, yhat)` as stored. Title `"{coef} van Veen (committed): R2={r2:.6f}"`.
- Peak-tip panel: `(y / k, yhat / k)`, computed with `/ k` exactly (`y * (1/k)` differs in the last
  ulp). Title `"{coef} peak-tip reference (stored / k): R2={r2:.6f}"`. These are today's
  coefficients (on-wing sign, hinge moments, current model) expressed on F_ref(R_TIP), not a
  reproduction of the pre-#36 data; the title says so by naming the operation, not "legacy".
- Axis labels: x = `"CFD {coef} (lab frame, on wing)"`, y = `"surrogate {coef}"`. The coarse
  corpus `CF_x..CF_z` are lab-frame and on the wing (coordinate-convention spec, "Force and moment
  sign"); `CF_chord`/`CF_normal` are the wing-frame ones. "Stroke" is not used: lab x is the stroke
  direction only at φ = 0.
- Suptitle: `"V3  Moving F_ref from r_gyr to r_tip divides both axes by k = F_ref(r_tip)/F_ref(r_gyr);
  R^2 unchanged"` (states the direction; see #170).

Rejected: dropping the peak-tip panel (the figure would no longer show the invariance it exists
for); keeping parquet × k and renaming it (a scale no convention uses).

## D2. Whole-summary comparison

`_summary_mismatches(committed, fresh) -> list[str]` (private helper in the test module) walks both
dicts and returns one message per mismatch, each starting with the dotted key path, in one of the
formats `"{path}: missing in fresh"`, `"{path}: missing in committed"`, `"{path}: type {a} != {b}"`,
`"{path}: committed {c!r} != fresh {f!r}"` (so a test can tell a stale value from a missing key):

- keys must be equal at every level (missing and extra keys are both mismatches); a dict on one side
  and a non-dict on the other is a mismatch;
- numbers (int/float, not bool): non-finite on either side is a mismatch; if `|committed| < 1e-12`
  the values must agree within `1e-12` absolute, otherwise within `1e-12 · |committed|` (no absolute
  floor);
- anything else (bool, str): `==`, with type equality.

The near-zero rule keys on the committed magnitude, not on exact `0.0`, so a `delta` of `1.1e-16`
committed from one platform and `0.0` regenerated on another both pass. A relative tolerance on a
value that small would be equality.

Why `1e-12`: the user's choice, checked against both directions. Catching: the smallest relative R²
change across the three retrains is `1.29e-5` (CF_x, #126 → #147). Not flaking: R² ≈ 0.999 has
spacing 1.1e-16, so `1e-12` is about 9,000 ulps; `R² = 1 − SS_res/SS_tot` damps summation error by
`1 − R²`, and five summation orders (fsum, cumsum, reversed, blocked, `np.sum`) give a bitwise-equal
R². `v1`, `v2`, `v4`, `v5` involve no cancellation. For the mean/RMS fields the worst conditioning is
CF_x `true_mean` (Σ|y|/|Σy| ≈ 68): numpy's pairwise summation bounds its error by about 2e-13
relative, and eight summation orders differ by at most 9.3e-15. A future field with Σ|a|/|Σa| above
about 300 would need a looser tolerance. On Linux (PR #172's CI, ubuntu-latest, at `fa3fb2b`) the
guard against the Windows-written summary passed at `1e-12`. That run gives pass/fail only; the
largest Linux-vs-Windows difference was not measured, because WSL was unavailable locally (task 3.5).

A test asserts the helper returns `[]`, and fails listing every message otherwise.

## D3. Inspecting V3 without changing the API

The V3 tests replace the module's `plt.close` with a collector (the `_render_with_sentinels`
pattern in the same file), assert exactly one figure was collected, and close it with the saved real
`plt.close` in `finally`. Panels are located by title (coef + convention string), with exactly one
match each and four axes in total; each panel has exactly one `PathCollection`. The V3 tests call
`fig_v3_scale_invariance(tmp_path)` themselves and take R² from its return value; they do not request
the module-scoped `main()` fixture, which would otherwise run under the collector and collect five
figures.

## D4. Summary key rename

`r2_before` / `r2_after` → `r2_van_veen` / `r2_peak_tip`. "Before/after" carried the wrong direction.
Repo-wide search at `e600581`: nothing reads either key. The generator writes them and the committed
JSON holds them; `tests/test_flapping_wing_validation_figures.py` reads only `delta`.
(`tests/test_force_surrogate_scale_invariance.py` has local variables of the same names; #170.)

## D5. Regeneration, diff, and the PNG

`main()` runs once in the worktree after the generator change. Every written file is compared with
`HEAD`: V1, V2, V4, V5 byte-identical and the `v1`, `v2`, `v4`, `v5` blocks unchanged, or the change
stops. The JSON is written with `Path.write_text(..., newline="\n")`; `.gitattributes` already stores
`*.json` as LF, so this affects only the Windows working tree.

The V3 PNG is not byte-reproducible across platforms (fonts, freetype), and no test compares PNG
bytes. What V3 plots is guarded by rendering it in the test (D3) and by the known-answer check (D7);
the committed PNG matches only because it is regenerated in the same commit as the summary.

## D6. Scale- and sign-sensitive fields in `v3`

R² is unchanged by a pure rescale or sign flip of the parquet, which is exactly how `c74d69b` changed
it, so an R²-only guard would stay green while the committed PNG went stale. Per coefficient, `v3`
records `true_mean`, `true_rms`, `pred_mean`, `pred_rms` of the van Veen (stored) arrays; the D2
comparison then fails on any rescale (RMS) or sign flip (mean; both CF_x and CF_z means are non-zero:
+0.021, +0.574).

## D7. Known answer for the peak-tip panel

The holdout rows merge one-to-one with `examples/prelim_sweep/dataset.parquet` on
(`config_name`, `time`), whose raw `Fx`, `Fz` are on the fluid. The peak-tip panel's x offsets must
equal `−F / compute_force_reference(frequency_fstar, stroke_amp_deg, R_TIP, SPAN, CHORD, RHO).f_ref`
per row (per-config F_ref, not the scalar k), within `rel = 1e-12, abs = 0` (measured agreement
6.7e-16; `abs=0` because pytest's default `abs=1e-12` would otherwise dominate for the smallest
values, |CF_z| ≈ 5e-5). A ×k or a dropped sign is off by O(1). Raw `Fx`, `Fz` are on the fluid per
the coordinate-convention spec ("Force and moment sign"); the data shows only CF = −F/F_ref, which
this test pins. This covers `*_true` only; `*_pred` has no raw anchor and is tied by
the exact van Veen-panel equality.
