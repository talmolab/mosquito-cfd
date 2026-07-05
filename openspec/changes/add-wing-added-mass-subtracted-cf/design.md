# Design — added-mass-subtracted body-frame CF diagnostic (#40 cheap interim)

## Context

The T2a body-frame comparison (`reconstruct_wing_body_forces` → `body_frame_overall_match`) rotates the
**total** `ib_force` into the wing frame by the analytic `R(t)` and grades peak `|CF_chord|`/`|CF_normal|`
against van Veen's **translational-only** targets. `CF_chord` (0.92 vs ~0.3) fails → PARTIAL. van Veen
decomposes his force into translational + added-mass + Wagner; ours is the **total**. The cheapest test of
the "added mass inflates the chord" hypothesis is to subtract the one component we already log — the
added-mass term `ρ_f·SumU` (IAMReX `WriteIBForceAndMoment`; already implemented as `added_mass_force`, #36)
— and re-report the body-frame peaks. This is #40's first checkbox and is entirely cluster-free.

## Decisions

### D1 — Reported diagnostic only; no new gate (CC-V2)

The diagnostic returns **numbers**, not a verdict. The return dict carries **no** `*_match`, `pass`,
`floor`, or `in_band` field. The existing graders — `plausibility_gate` (on lab `ib_force`) and
`body_frame_overall_match` (body `ib_force` vs `VAN_VEEN_CF_TARGETS`, tol `VAN_VEEN_MATCH_TOL`, floor
`VAN_VEEN_BAND`) — are **untouched**; the subtracted value cannot re-grade van Veen. A test asserts the
diagnostic exposes no verdict key and that the existing graders' outputs on the committed run are unchanged.
*Rationale:* the interim isolates a **share** of a known defect; grading the residual against van Veen
would invent a pass/fail the roadmap explicitly reserves for T4.

### D2 — Reuse the rotation and the added-mass magnitude (CC-V4), via linearity

The rotation is **linear**, so `Rᵀ·(F_ib − ρ_f·SumU) = Rᵀ·F_ib − Rᵀ·(ρ_f·SumU)`: subtract-in-lab-then-rotate
equals rotate-then-subtract. The diagnostic therefore:
1. forms `am = added_mass_force(SumU, rho_f)` — the **existing** #36 helper (`ρ_f·SumU`), not re-derived;
2. forms `sub = ib − am` in the lab frame;
3. rotates `ib`, `am`, and `sub` into the body frame with the **existing** `body_frame_coefficients`
   (`Rᵀ·F`, explicit chord/normal/span axes) and the **existing** analytic `R(t)` from
   `wing_kinematics.rotation_matrix` ∘ `euler_angles`.

No new rotation code, no new added-mass formula. The two defect classes (magnitude reconstruction vs
orientation/motion) stay separate. A unit test on a synthetic case pins the linearity identity (a pure-chord
added-mass exactly cancels a pure-chord ib in `CF_chord`).

### D3 — RMS share = body-frame analog of `added_mass_fraction`

The body-frame added-mass **RMS share** per component is `rms(CF_added_body) / rms(CF_ib_body)` over the
steady window — the **body-frame mirror** of the existing lab-frame `added_mass_fraction`
(`rms(added)/rms(ib)`). It is **not** `rms(subtracted)/rms(ib)` and **not** a peak ratio. Reproduced:
chord 83.9 % → **84 %**, normal 12.8 % → **13 %**. A **structural** test pins the definition (a body-frame
added-mass component set to a known multiple `k` of the ib component yields share `== k`, and `≠
rms(ib−added)/rms(ib)`), so a value-only match to 84 %/13 % cannot mask a wrong formula.

**Disambiguation is mandatory in the doc (per the docs review).** The lab-frame fractions (`added_mass_fraction`,
keys `stroke`/`lift` = 37 %/29 %) and these body-frame shares (chord/normal = 84 %/13 %) sit one section
apart and are a **different frame *and* axis pairing** — stroke≠chord, lift≠normal after rotation by `R(t)`.
`RESULTS.md` MUST carry an explicit sentence that neither supersedes the other (else a reader reads 84 %/13 %
as correcting 37 %/29 %), and the reproducibility guard asserts that sentence is present — not merely that
all four percentages coexist.

### D4 — Cluster-free inputs (CC-V3)

Sole input: the committed `examples/flapping_wing/forces_t2a_newconv.csv` (29-col, with `SumU{x,y,z}`).
Because it rotates the **full 3-D** force and added-mass vectors, the diagnostic reads
`time, Fx, Fy, Fz, SumUx, SumUy, SumUz` and defines its **own** required-column set. **No single existing
tuple covers all seven:** `_REQUIRED_CSV_COLUMNS = (time, Fx, Fz, SumUx, SumUz)` lacks `Fy` **and** `SumUy`;
`_REQUIRED_BODY_CSV_COLUMNS = (time, Fx, Fy, Fz)` has `Fy` but lacks **all** `SumU*`. `SumUy` is in
**neither**. Reusing either would silently skip a needed check — so the guard test drops **each** of
`Fy/SumUx/SumUy/SumUz` individually and asserts a `ValueError`. No new simulation, no GPU, no cluster, no
run metadata.

### D5 — Honest framing (no overclaim)

Docs and the requirement state the drop **isolates the added-mass share**, it does **not** resolve the
PARTIAL. Even added-mass-subtracted, `CF_chord ≈ 0.652` is still ~2× van Veen's translational ~0.3
(0.652/0.3 ≈ 2.17); the residual (rotational drag + coarse grid + total-vs-translational) is explicitly the
**full T4**. The normal is barely affected (−12 %, share 13 %), consistent with the T2a "added-mass + Wagner
roughly cancel in the normal". This mirrors the T2b review lesson: report a share, not a resolution.

**Metric-type honesty (per the numerical-correctness review).** For the **chord**, three distinct numbers
must not be conflated: **84 %** = added-mass RMS *energy* share over the window; **−29 %** = the
peak-to-peak ratio `1 − peak_subtracted/peak_total` of two window maxima that fall at **different phases**
(the total-chord peak near a stroke reversal, the subtracted-chord peak mid-stroke — verified ~1094 rows
apart); **~47 %** = the *instantaneous* added-mass drop at the total-peak instant. The prose SHALL NOT let
"84 % of RMS" read as the *cause* of "the peak dropped 29 %" — both independently show added mass dominates
the chord, by different measures on different supports. (The normal's peaks coincide in phase, so its −12 %
is ≈ per-instant; the caveat is chord-specific but stated generally.)

### D6 — Doc numbers guarded before the edit; separate reproducibility test

The interim finding goes in a **new** subsection ("Added-mass-subtracted body-frame diagnostic (#40 cheap
interim)"). Its numbers are guarded by a **new** test that (a) recomputes total→subtracted peaks, % drops,
and RMS shares from `forces_t2a_newconv.csv`, and (b) asserts the interim literals are present in
`RESULTS.md` with the subsection's numbers **asserted-complete** via a set-equality scan of the interim
subsection (mirroring `test_headline_tables_enumeration_complete`'s mechanism, not bare `in doc` substring
checks) — run **before** the doc edit (fails until the numbers land).

It is a **separate** guard from the existing `test_headline_tables_enumeration_complete` (which scans only
the two existing tables by exact-set-equality). To keep that separation load-bearing, the interim subsection
MUST use a **distinct `### ` header** that does **not** contain the substrings `lab-frame magnitudes` or
`Body-frame per-component van Veen comparison`, and MUST **not** add/alter a numeric cell in those two
tables — a test confirms that existing guard still passes unchanged. The interim table shows the totals at
3 sig figs (`0.923`/`2.606`); the doc carries a **"same peaks"** note that these are the body-frame table's
`0.92`/`2.61` **shown to an extra significant figure** (NOT the imprecise "equal to 3 sig figs" — `0.92` is
only 2 sig figs), and a test asserts `peak_cf_*_total == body_frame_overall_match(...)["peak_cf_*"]` so the
two precisions cannot drift apart.

### D7 — Issue #40 stays open

Only the *cheap-interim* checkbox is checked, with the finding. The T4-proper decomposition and the van
Veen Fig 3–4 curve match remain unchecked; #40 is **not** closed.

## API sketch (single reporting function — the approved shape)

```python
def body_frame_added_mass_subtracted(
    csv_path: str | Path,
    *,
    f_star: float,
    phi_amp_deg: float,
    pitch_amp_deg: float,
    deviation_amp_deg: float = 0.0,
    rho_f: float = RHO,
    window_t0: float = STEADY_WINDOW_T0,
) -> dict:
    """Reported: peak |CF_chord|/|CF_normal| for total vs (ib_force - rho_f*SumU),
    their % drop, and the body-frame added-mass RMS share. No verdict field (#40 interim)."""
```

Returned keys (all reported, no verdict): `peak_cf_chord_total`, `peak_cf_normal_total`,
`peak_cf_chord_subtracted`, `peak_cf_normal_subtracted`, `chord_drop_frac`, `normal_drop_frac`,
`am_rms_share_chord`, `am_rms_share_normal`, `window_t0`. Each `peak_*` is the **independent window
argmax** of `|series|` (the subtracted peak is the max of the subtracted series, NOT the subtracted value
at the total's argmax — on this data the chord peaks migrate ~1094 rows). The drop is the **signed**
peak-to-peak fraction `chord_drop_frac = 1 − peak_cf_chord_subtracted / peak_cf_chord_total` (≈ 0.29 here;
shown in prose as −29 %; it is `1 − ratio`, so it is **negative** if subtraction raises the peak — not
unsigned in general), likewise `normal_drop_frac` (≈ 0.12). `window_t0` echoes the argument. The RMS share
is computed by a module-level seam `_body_frame_rms_share(added_body_component, ib_body_component)` so the
definition guard (task 2.2) can pin it on synthetic arrays. A test asserts the **exact key set**
(`set(out) == {…}`) so a later-added `*_match`/pass key is caught even if it is not one of the specific
verdict names the reported-not-graded test lists.

**Reuse is verified, not just asserted (per the TDD review).** Task 1.1's linearity identity
(subtract-then-rotate ≡ rotate-then-subtract) is necessary but a re-implementation with the same math would
also pass it. A separate test therefore pins `peak_cf_*_subtracted` against an **independent manual
pipeline** built from `added_mass_force(SumU)` + `body_frame_coefficients(R(t))` on the committed CSV
(`abs=1e-9`), so any divergent re-derivation fails — enforcing CC-V4 (reuse `added_mass_force` #36 and the
T2a rotation, don't re-derive). A `rho_f=0` check (subtracted peaks == total peaks, shares == 0) confirms
`rho_f` flows through to `added_mass_force`.

## Risks / mitigations

- **Reader conflates the drop with a pass** → D1 (no verdict field) + D5 (explicit "isolates, not
  resolves" framing) + a scenario asserting the honesty language.
- **Someone later loosens a gate citing the interim** → the existing not-loosened guards on
  `VAN_VEEN_BAND` / `VAN_VEEN_MATCH_TOL` / `VAN_VEEN_CF_TARGETS` stay, and a test asserts the diagnostic
  does not touch those graders' outputs.
- **Doc number drifts from data** → D6 reproducibility guard (recompute + assert-present + asserted-complete)
  runs before the edit.
