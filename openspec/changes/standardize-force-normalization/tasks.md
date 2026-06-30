# Tasks — standardize-force-normalization

> **TDD throughout** (`uv run pytest`). Analysis-only: **no CFD re-runs, raw forces/CSVs untouched.**
> `[oracle]` marks the north-star/guard tests written first.
>
> **Commit-boundary note (BREAKING flip).** The sub-task order below is a *TDD narrative, not a commit
> boundary*. Task A's helper rewrite + field rename (`u_tip_max→u_ref`, `q_tip→q_ref`) + `f_ref`
> 624.79→200.27 + all 3 regression-locked test files + all callers MUST land in **one atomic commit**
> — any intermediate state reds the suite. Likewise Task D's caption edits and the two `"2.4"` test
> guards (D.6) must land together. See `design.md` D2 and the proposed commit plan in the review.

## A. Normalization helper + CC-3 regression lock (foundation) — **one atomic commit**

- [x] A.0 **[oracle, test-first]** `tests/test_force_surrogate_normalization.py::test_radius_of_gyration_traced_from_wing_vertex`:
      re-derive `r_gyr = sqrt(mean(r²))` (hinge-distance `r = z_local + (R_TIP − max z_local)`) from the
      committed `examples/flapping_wing/wing.vertex`; assert it equals `R_GYRATION ≈ 1.6985` (`rtol=1e-3`)
      and is `< R_TIP = 3.0`. **Note:** `R_TIP` is used *inside* the hinge-offset formula and must
      survive — a careless `s/R_TIP/R_GYRATION/` sweep would corrupt it (add a guarding comment).
- [x] A.1 **[oracle, test-first]** Update the CC-3 regression lock: validated point now yields
      `u_ref ≈ 13.04`, `q_ref ≈ 85.0`, `area ≈ 2.3562`, `f_ref ≈ 200.27` (`rtol=1e-3`),
      `f_ref == ½·rho·ω_peak²·S_yy` with `S_yy = r_gyr²·area ≈ 6.797`, and `m_ref ≈ 200.27` with the
      `length` field == `chord`. Keep the parameterization test (half stroke → smaller `f_ref`; double
      `f*` → double `u_ref`).
- [x] A.2 Add `R_GYRATION` to `src/mosquito_cfd/force_surrogate/constants.py` (value derived from
      `wing.vertex`, comment citing van Veen `S_yy`), **and rewrite the existing `R_TIP` NOTE
      (constants.py:16-19)** so it no longer claims `R_TIP` is the normalization arm (it is retired
      from normalization; `R_GYRATION` is the arm; `R_MID` stays the Reynolds arm). Also fix the now-stale
      `sweep.py:15` and `:104` docstrings that frame `R_TIP` as "the force-normalization tip arm" (it no
      longer is) — keep them as the Reynolds "do-not-conflate" illustration but cite `R_GYRATION` as the
      normalization arm.
- [x] A.3 Re-define `compute_force_reference` (`normalization.py`) to van Veen-faithful
      (`F_ref = ½ρ·u_ref²·area`, `u_ref = ω_peak·r_gyr`; positional arg `r_tip→r_gyr`); rename
      `ForceReference.u_tip_max → u_ref`, `q_tip → q_ref`; make `compute_moment_reference` reuse
      `q_ref·area`. **Update the docstrings** in `normalization.py` (lines ~4, 22-25, 40-45, 110-113,
      124, 154 — "wing-tip speed", "m_ref ≈ 624.79") to the gyration/200.27 convention.
- [x] A.4 Switch the callers passing the old field/arg: `dataset.py:167-168` (`R_TIP→R_GYRATION`,
      field access), `evidence_figure.py:181` (`R_TIP→R_GYRATION`), and `generate_all_figures.py`
      **:236** (comment "tip dynamic pressure" → gyration), **:237-239** (`R_TIP→R_GYRATION`,
      `ref.u_tip_max→ref.u_ref`, `ref.q_tip→ref.q_ref`, the `U_tip_max=…` print), **:291** (the on-figure
      caption `"Forces normalized by q_tip x S … V_tip = …"` → van Veen wording). **Keep
      `evidence_figure.py` caption strings untouched here — those are Task D** (so the `"2.4"` guard
      tests don't fire early).
- [x] A.5 Fix **all four** regression-locked test files (none gpu-marked, all run in CI):
      `tests/test_force_surrogate_dataset.py` (validated-point `f_ref`/`m_ref` ≈ 200.27,
      `CF_x = 50/200.27 ≈ 0.250`, comment at :56); the `evidence_figure` spy tests incl. the
      `ForceReference(u_tip_max=…, q_tip=…)` keyword constructor at
      `test_force_surrogate_evidence_figure.py:193` (→ `u_ref=`, `q_ref=`); **and
      `tests/test_force_surrogate_figures.py:40`** (`expected = real(gaf.F_STAR, …, gaf.R_TIP, …)` →
      `gaf.R_GYRATION`, else the spy captures an `R_GYRATION` ref vs an `R_TIP` expected → RED). Assert
      ratios/relationships, not stale literals. **All of A.2–A.5 + the callers land in ONE atomic commit.**
- [x] A.6 Run the normalization + dataset + evidence-figure test modules green;
      `uv run ruff check` + `uv run ruff format --check`.

## B. Track-B propagation + scale-invariance guard

- [x] B.0 **[oracle, test-first]** `tests/test_force_surrogate_scale_invariance.py`: load the committed
      `holdout_predictions.parquet`; assert scaling `CF_*_true`/`CF_*_pred` by `k = f_ref_old/f_ref_new
      = 3.119` leaves per-target `R²` unchanged within `1e-9` for `CF_x`, `CF_z` (and the unscaled `R²`
      matches `metrics.json`). Add a degenerate case: `f_ref_new = 0` or a missing `CF_*` column raises
      (no inf/NaN R²).
- [x] B.1 Re-derive the corpus **derived** coefficients: regenerate the `CF_*` columns of
      `dataset.parquet` (raw `Fx/Fy/Fz/Mx/My/Mz` **values unchanged**) and the held-out
      predictions by the convention rescale (no retrain — scale-invariant).
- [x] B.2 **[test]** Value-level equality (not file-byte): `pandas.testing.assert_frame_equal` on
      `Fx,Fy,Fz,Mx,My,Mz` (`check_exact=True`) between committed and regenerated `dataset.parquet`;
      assert each `CF_*_new == CF_*_old / k`; assert committed `metrics.json` per-target `R²` reused
      unchanged (within `1e-9`). Document that `R²` is invariant and `RMSE/MAE` rescale by `k`.
- [x] B.3 Regenerate `evidence_figure.png` + `evidence_figure_metrics.json` under the new convention
      (axis numbers relabel; scatter and `R²` identical). **Update the `note` string in
      `evidence_figure_metrics.json` (the committed sidecar carries the false "~2.4× diffused-IB" note).**

## C. Roadmap invariants (CC-3, CC-V6)

- [x] C.1 Rewrite **CC-3** in `docs/force_surrogate/roadmap.md` to `F_ref ≈ 200.27` and the van Veen
      `½ρ·ω²·S_yy` definition. **Update L84, L88** (the `F_ref = q_tip·S` math / "F_ref ≈ 624.79") and
      the **summary-table row L150** (`F_ref = 624.8 (q_tip 265.2 × S 2.356; U_tip 23.0)` → new values).
- [x] C.2 Rewrite **CC-V6** in `docs/aerodynamics_validation/roadmap.md` (L128-133): re-deriving CF ≠
      regenerating CFD; the "2.4×" was a **normalization convention** (3.119×), **not** a diffused-IB
      underestimate and **not** the sphere's 2.64× extraction bug; and reverse the now-false
      *"F_ref ≈ 624.8 is pure-kinematics and unaffected"* claim (F_ref **does** move to 200.27). Update
      the reconciliation-log line L187-188. Keep the raw corpus frozen/digest-pinned.

## D. Caption/claim cleanup (absorbs the CC-V6 half of #29)

- [x] D.1 `examples/flapping_wing/RESULTS.md`: remove the false "~2.4× lower"/"corrected" claim and any
      ×2.4/×2.64 factor, **and** move every stale-convention number to van Veen — the reference table
      (L100-103: `U_tip_max 23.0`/`q 265.2`/`F_ref 624.8` → `u_ref 13.04`/`q_ref 85.0`/`F_ref 200.27`),
      the CF-range table (L109-114), the "corrected coefficient" tables (L121-124, L195-201), and the
      validation-status rows (L187). (E.5 regenerates the figures these tables summarize.)
- [x] D.2 Remove the "~2.4× diffused-IB underestimate" framing from the five false-claim
      `evidence_figure.py` sites: module docstring (:9), `caveats` (:314), `reference` (:321),
      `_baseline_reference` docstring (:347), and the `note` written to the JSON sidecar (:372-373).
      **Do NOT touch line :58 (`~2.4 min/wingbeat` — a legitimate CFD-cost figure, not the false claim).**
- [x] D.3 Reconcile `examples/prelim_sweep/README.md` (~L303, L323) and the `docs/force_surrogate/
      roadmap.md` "2.4× still applies" line (L95) and sphere-row (L152) to the normalization-convention
      explanation.
- [x] D.4 Update `docs/aerodynamics_validation/t1a-findings.md` §8 follow-up note (L304-312): mark the
      CC-V6 (wing/Track-B) files as done **here** (no longer "deferred"), and correct the now-false
      "`F_ref ≈ 624.8` (pure kinematics) is unaffected" (scope it to CC-V5/sphere only).
- [x] D.5 **[test]** Add a guard test asserting no `2.4x`/`2.64x`/`×2.4`/"diffused-IB … low"/
      "underestimate" claim or numeric correction factor remains, naming the exact files:
      `flapping_wing/RESULTS.md`, `evidence_figure.py`, `prelim_sweep/README.md`, both roadmaps,
      `evidence_figure_metrics.json`. Match the **multiplier/claim** patterns specifically so the
      legitimate `~2.4 min/wingbeat` cost reference (`evidence_figure.py:58`) is NOT a false positive.
- [x] D.6 **[test]** Update the two existing tests that currently *require* the `"2.4"` string —
      `test_force_surrogate_evidence_figure.py:305` (`"2.4" in cap`) and `:708` (`"2.4" in readme`) —
      plus the related overshoot-caption asserts (:303-312), so they match the corrected captions and
      do not contradict D.5. (Lands in the **same commit** as D.2/D.3.)
- [x] D.7 In `proposal.md`/PR body, reconcile with **#29**: tick CC-V6's five doc items as done here,
      note that this change **supersedes** CC-V6's "F_ref unaffected" bullet; CC-V5 (sphere "~60% low":
      apex proposal/tasks/spec, `heaving_ellipsoid/RESULTS.md`, APEX-PDF immutability) **stays in #29**.
      No edits to sphere figures/numbers (`flow_past_sphere/*`, `force-extraction` spec).

## E. Wing reconstruction + validation (depends on A) — gate on ib_force ALONE

- [x] E.0 **[prerequisite]** Resolve the `SumU*`→force relationship from IAMReX `WriteIBForceAndMoment`
      (`c:\repos\IAMReX-fork\Source\`): is the added-mass term already force-like, or a momentum sum
      requiring `d/dt`? Document the exact column algebra. (Raw data shows ~1000× ambiguity — this gates
      E.1a, never the band.)
- [x] E.1a **[oracle, test-first]** `tests/test_flapping_wing_validation.py`: assert the added-mass term
      equals the **documented `WriteIBForceAndMoment` expression** on a known row of the committed
      `IB_Particle_1.csv` (formula citation in the docstring). Locks the formula to the **source**, not
      the band.
- [x] E.1b **[oracle, test-first]** Assert the **`ib_force`-only** `max|CF_x|`, `max|CF_z|` ∈ `[0.5,1.5]`
      under the van Veen convention over the pinned steady window (no added-mass, no correction factor;
      provable from committed data today), and that the gate verdict is **unchanged** whether or not the
      added-mass term is included. Report the rotation-invariant `|CF| = sqrt(CF_x²+CF_z²)`. Band NOT
      loosened.
- [x] E.2 **[test]** Pin the steady window `t0` as a **named constant** with a documented physical
      criterion (exclude the impulsive-start transient — confined to steps 1–8, `t ≤ 0.004`, where
      `max|CF_x|` spikes to ~39; any `t ≥ 0.005` is clean). Assert the reported peak CF values are
      reproducible from committed `forces.csv`/`IB_Particle_1.csv` for that window, and report **both**
      band-edge margins on `ib_force` alone: the `CF_z` **floor** above 0.5 (~+0.11) **and** the
      `CF_x` **ceiling** below 1.5 (~−0.09 — the tighter edge near the transient cutoff).
- [x] E.3 **[test]** Decomposition: `combined = ib_only + added_mass_only` (float tol); added-mass
      fraction bounded `0 < f < 1`, actual value snapshotted (not hard-locked to 15%/33%).
- [x] E.4 **[test]** Spy/monkeypatch that `generate_all_figures.py` calls `compute_force_reference`
      (no inline `F_ref`) — mirror `test_sane_dickinson_uses_cc3_helper`.
- [x] E.5 **[test]** Assert the docs disclose the gate is a **lab-frame O(1) magnitude** check, that the
      lab `CF_x/CF_z` are NOT van Veen body-frame chord/normal axes, and defer body-frame per-component +
      time-resolved to T2a (#1) / T4 (no overclaim).
- [x] E.6 Implement the reconstruction in `generate_all_figures.py` (via `compute_force_reference`, no
      inline re-derivation); regenerate wing `RESULTS.md` + figures in the van Veen convention (no fudge).

## F. NVIDIA proposal

- [x] F.1 Update CF numbers and drop the "~2.4× underestimate" framing in the NVIDIA proposal doc
      (external vault: `c:\vaults\physics surrogate models\nvidia-proposal\` per
      `docs/aerodynamics_validation/roadmap.md:140`). **First confirm draft-vs-submitted status** — if
      the PDF is already submitted/immutable (like the APEX PDF in #29), record the intentional drift
      instead of editing. Verify no stale `624.79`/"2.4×" remains in the editable source.

## V. Figures (TDD-backed; each asserts the numeric quantity it shows)

- [x] V1 Three-convention `CF_x(t)/CF_z(t)` overlay vs `[0.5,1.5]`; test asserts the three `F_ref`
      (≈624.8 / 253.2 / 200.3) and that van Veen peaks fall in band.
- [x] V2 Planform + second-moment integrand `c(y)·y²`; test asserts `r₂ ≈ 1.6985`, `S_yy ≈ 6.797`
      (`rtol=1e-2`, pinned to the A.0/design values — single source of truth).
- [x] V3 Scale-invariance scatter (before/after); test asserts `ΔR² < 1e-9` (reuses B.0).
- [x] V4 Added-mass decomposition (ib_force vs added-mass over the cycle); test reuses E.3 (clearly
      labelled "not graded by the gate").
- [x] V5 Lab-vs-body-frame illustration at the α=45° midstroke (honesty figure); test asserts the
      orientation/forces are drawn from the documented `WingKinematics` rotation.

## Z. Close-out

- [x] Z.1 Delete the `SCRATCH_*` files (md + 3 PNGs) from the repo root before the first commit; use
      path-scoped `git add` per commit; verify `git status --short` shows no `SCRATCH_*` before committing.
- [x] Z.2 `uv run pytest` (full, cluster-free) + `uv run ruff check .` + `uv run ruff format --check .`
      green; `openspec validate standardize-force-normalization --strict`.
- [x] Z.3 Queue the #1 stroke-about-span note (post on user go-ahead); post the #29 close-out comment
      marking CC-V6 done (with the corrected 3.119× mechanism) and CC-V5 remaining.
