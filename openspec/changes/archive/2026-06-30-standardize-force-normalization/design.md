# Design — standardize-force-normalization

## Context

`compute_force_reference()` is the CC-3 single source of force/moment normalization, reused by the
Track-B `dataset.py`, `evidence_figure.py`, the sweep, and the wing `generate_all_figures.py`, and
regression-locked to `F_ref ≈ 624.79`. The wing's coefficients looked too small versus the literature,
which was wrongly attributed to a diffused-IB force deficit (and conflated with the sphere's real
extraction bug). This change corrects the **convention**, analysis-only.

## Derivation spike (the basis for the locked numbers)

Run on the committed `wing.vertex` (908 markers) and `forces.csv`; reproduced by the V1–V3 figure
tasks.

- **van Veen eq 1.1:** `F = ½ρ·ω²·S_yy·C_F`, `S_yy = ∫c(y)y² dy` (eq 1.2). The velocity scale is the
  stroke rate `ω` at the **radius of gyration** `r₂ = sqrt(S_yy/S)`, not the wingtip.
- From the markers (binned by hinge distance `r`, uniform-area elements): `mean(r²) = 2.885`,
  `r₂ = 1.6985`, `S_yy = r₂²·S = 6.797` (`S = π/4·span·chord = 2.356`). `r_tip = max r = 3.0`.
- `ω_peak = 2π·f*·radians(70°) = 7.6764`; `u_ref = ω_peak·r₂ = 13.04`; `q_ref = ½ρ·u_ref² = 85.0`;
  `F_ref = q_ref·S = ½ρ·ω_peak²·S_yy = 200.27`.
- Factor vs current: `(r_tip/r₂)² = 3.119`. **Not** the issue's `(π/2)² = 2.47` (peak-vs-mean of a
  sinusoid) — that is unrelated physics that merely shared an order of magnitude with the old fudge.
- Re-derived CF (raw `ib_force`, `t ≥ 0.05` window): `max|CF_x| = 1.41`, `max|CF_z| = 0.68` — both in
  `[0.5, 1.5]` with **no** correction factor. (`t ≥ 0.5` window gives 1.34 / 0.61; pinning the steady
  window is a Task-A item.)
- **Scale-invariance:** on the committed `holdout_predictions.parquet`, multiplying `CF_*_true` and
  `CF_*_pred` by `k = 3.119` leaves `R²` bit-identical (`ΔR² = 0`; CF_x 0.993181, CF_z 0.985401,
  matching `metrics.json`). RMSE/MAE scale by `k`; R² and the scatter are invariant.

## Decisions

### D1 — Normalization arm is the radius of gyration (`r_gyr`), derived from geometry

`compute_force_reference` keeps the `½ρ·u² · area` structure but replaces the **tip arm** with the
**radius of gyration**: `u_ref = ω_peak · r_gyr`, so `F_ref = ½ρ·u_ref²·area = ½ρ·ω_peak²·S_yy`
(identically van Veen eq 1.1, since `S_yy = r_gyr²·area`). `r_gyr` is committed as a new constant
`R_GYRATION ≈ 1.6985` in `constants.py`, **derived once from `wing.vertex`** and guarded by a
traceability test (re-derive from the marker file, assert match) so it is not a magic number. The old
`R_TIP = 3.0` is retired from normalization (kept only for documentation/illustration); `R_MID = 1.5`
stays the Reynolds arm (untouched).

### D2 — API: rename the misnamed field [BREAKING]

The `ForceReference` velocity field `u_tip_max` is no longer a tip speed; rename to `u_ref` (speed at
the radius of gyration) and `q_tip → q_ref`, updating all call sites and tests. This is the
honest minimum API churn (touches #31's "force-coefficient API" surface; coordinated, not expanded).
It is **BREAKING** (public dataclass fields + the regression-locked `f_ref`/`m_ref` values). Because
the helper, its three regression-locked test files, and every caller (`dataset.py`,
`evidence_figure.py`, `generate_all_figures.py`) reference the old names/values, the flip MUST land as
**one atomic commit** — any intermediate state reds the suite. The `r_tip` positional argument of
`compute_force_reference` becomes `r_gyr`, so the call sites passing `R_TIP` (`dataset.py:167-168`,
`evidence_figure.py:181`, `generate_all_figures.py:237`) switch to `R_GYRATION` in the same commit.

### D3 — Gate framing: O(1) magnitude, frame + tier deferred (roadmap CC-V4)

The normalization (`F_ref`) is a **scalar** and therefore frame-independent — it is correct regardless
of the axis convention. The **component split** (`CF_x` vs `CF_z`) is not: van Veen reports body-frame
chord-wise/normal components, our forces are lab-frame, and at the α=45° midstroke lab ≠ body, so the
lab `CF_x/CF_z` **mix** chord-wise and normal load and do not correspond to van Veen's axes. The
`[0.5, 1.5]` check is therefore graded as an **order-of-magnitude plausibility gate on lab-frame
magnitudes**, and the analysis additionally reports the **rotation-invariant** in-plane resultant
`|CF| = sqrt(CF_x² + CF_z²)` (max-of-resultant ≈ 1.34–1.42 over the steady windows — *not* the
resultant-of-maxes, since `CF_x` and `CF_z` peak at different instants) as the frame-honest companion
(a rotation preserves magnitude, not components). The docs must state that the per-component lab values are not van Veen body
axes; the faithful body-frame per-component comparison is deferred to **T2a (#1)** and the
time-resolved curve match to **T4** (V5 visualizes the lab-vs-body distinction). This honors CC-V4
("two distinct defects, never conflate") and prevents overclaiming. **Decided (user):** the
per-component `[0.5,1.5]` check is the graded oracle (the band is itself per-component, so a
magnitude-vs-band gate would have its own mismatch); reviewer 3's rotation-invariant magnitude is
**reported as the frame-honest companion** and the "lab ≠ van Veen body axes" caveat is mandatory.
Window robustness: the impulsive-start transient is confined to steps 1–8 (`t ≤ 0.004`); every
defensible steady window (`t ≥ 0.005`) clears both band edges (CF_z floor ~+0.11, CF_x ceiling ~−0.09).

### D4 — Re-derive (don't regenerate): the frozen-corpus distinction

CC-V6 is rewritten: the **raw** CFD outputs (IB-particle CSVs, raw `Fx/Fy/Fz`/`Mx/My/Mz` columns)
stay byte-frozen/digest-pinned; the **derived** coefficients (`CF_*` columns, evidence figure,
metrics) are re-derived under the new convention. No solver run, no surrogate retrain (scale-invariant
— predictions rescale by the same `k`). `R²` is unchanged; `RMSE/MAE` rescale by `k` and are reported
honestly.

### D5 — Added-mass term (`SumU*`) is reported separately, NOT graded by the gate

The plausibility gate is graded on `ib_force` **alone** (which already clears the band: CF_x 1.34–1.41,
CF_z 0.61–0.68). The IB added-mass term from the `SumU*` columns is reported as a **separate
decomposition**, never folded into the graded coefficient. Rationale (reviewer 3, confirmed on the
committed data): the raw `SumU*` is **~1000× ambiguous** — `SumUx` peak ≈ 4357 (comparable to `Fx`
≈ 7905) if it is already force-like, but `d(SumUx)/dt` peak ≈ 8.7×10⁶ (~1100× `Fx`) if it is a
momentum sum requiring a time derivative (the 6-DOF balance in `t1a-findings.md` §1 uses
`(ΣU_new − ΣU_old)/dt`). Letting an unverified term with that ambiguity decide the `[0.5,1.5]` gate
would invert the change's own "no fudge" principle. So: **Task E.0 resolves the exact `SumU*`→force
expression from the IAMReX `WriteIBForceAndMoment` source first**; a formula test (E.1a) locks the
expression to the **source**, not to the band; the gate (E.1b) is on `ib_force` and is unchanged
whether or not added-mass is included. The decomposition fraction is reported (bounded `0 < f < 1`,
value snapshotted), not hard-locked to the issue's "~15%/~33%".

### D7 — Implementation deviation: the QS reference under-predicts (no longer "overshoots")

Discovered during implementation (Task B). The Sane–Dickinson `CF_trans(t) = (U(t)/u_ref)²·C_L` is
**convention-independent** (the `q_ref·area` cancels against `f_ref`), but the CFD `CF_z` it is
compared against **grows by `k`** under van Veen. So the recorded `overshoot_factor =
rms(CF_trans)/rms(CFD CF_z)` falls from ~2.3 (old peak-tip) to **≈ 0.73** (van Veen) — the QS model
now **under-predicts** the CFD lift rather than overshooting it. This is itself a confirmation of the
change's thesis: the old "overshoot dominated by ~2.4× diffused-IB" was an artifact of the too-small
peak-tip normalization; with the CFD lift correctly in-band, an uncalibrated *translational-only* QS
model (omitting rotational, added-mass, and LEV lift) under-predicts it, as expected. The
`evidence_figure.py` caption/docstring/note prose, the spec's Sane–Dickinson requirement, and the
`overshoot_factor > 1` test assertions were updated to neutral RMS-ratio language (`> 0`, "is ~N× the
CFD lift"); the JSON key `overshoot_factor` is kept (it is the same computed ratio) to avoid churn.
The "reference-only, not overlaid" decision stands (the model is a poor fit: baseline RMSE ≫ surrogate
RMSE).

### D8 — Task F: NVIDIA proposal is a submitted, immutable PDF (intentional drift)

The NVIDIA proposal lives in the external vault `c:\vaults\physics surrogate models\nvidia-proposal\`
as a **submitted PDF** (`eberrigan_physics_nemo_for_rl_proposal.pdf`); the editable markdown/slide
sources do **not** carry the stale CF numbers or the "~2.4× underestimate" framing (only the PDF does,
and it cannot be edited). Per F.1, this is recorded as **intentional drift** (exactly like #29's APEX
PDF): the submitted PDF retains the original note; any future resubmission should cite the van Veen
numbers — `F_ref = 200.27`, wing `CF_x ≈ 1.41`, `CF_z ≈ 0.68` (in-band, no fudge). No repo file is
edited for Task F (the vault is outside this PR).

### D6 — #29 reconciliation

#29's CC-V6 currently says to re-caption the Track-B "2.4×" to cite the sphere's resolved **2.64×
extraction** factor. This change proves that explanation wrong for the wing/corpus (it was a
normalization convention, 3.119×). So this change **takes over and corrects** CC-V6 (re-derive, don't
"cite the sphere factor") and closes that half of #29 on merge; the sphere-side CC-V5 "~60% low"
cleanup remains in #29.

## Alternatives considered

- **Mean-wingtip convention (the issue's original plan, `F_ref ≈ 253`, ×2.47).** Rejected: it is not
  van Veen's published definition, and it leaves `CF_z = 0.49` **below** the 0.5 floor on raw
  `ib_force` (only clearing the gate via the added-mass term). van Veen-faithful clears both
  components on raw force and is the honest attribution. (Full comparison in the spike.)
- **Splitting foundation (A–D, F) from wing validation (E).** Viable — E depends only on A. Folded
  per decision; flagged in `proposal.md` if review judges it unwieldy.
- **Touching the axis convention here.** Rejected: #1/T2a requires solver + BC + geometry changes and
  **re-runs** (post-submission); out of bounds for an analysis-only change. See D3.
