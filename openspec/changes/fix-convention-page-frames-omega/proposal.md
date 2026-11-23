# Change: Say which frame each force is in, and write ω_peak in F_ref

Advances #181 and #161. Places left out are tracked as follow-ups: #202 (bare ω elsewhere) and
#203 (lab-frame `CF_x`/`CF_y` labelled chord/span elsewhere).

## Why

The convention page says every reported force is wing-body-frame, but most of them are lab-frame
(#181). It also uses `ω` for two quantities, so read literally its `F_ref` is 1.49× too small (#161).
The live coordinate-convention requirement repeats both errors.

**#181: frames.** `docs/coordinate-convention.md` "Forces" says forces are "reported in the **wing
body frame**". "Moments" then says "Unlike the forces above — which are reported in the wing body
frame", and the rest-pose note says the page "carries body-frame *forces* and lab-frame *moments* by
design".

The project's wing force coefficients come in two frames (the full list is in design D1):

| Coefficients | How they are formed | Frame |
|---|---|---|
| Force-surrogate corpus and surrogate `CF_x..CF_z` | `build_dataset`: `−F/F_ref` on the solver's `Fx..Fz` (`dataset.py:406-424`) | lab |
| Flapping-wing lab series `cf_x_ib`/`cf_z_ib` (the `plausibility_gate` input) | `reconstruct_wing_forces`: `−F/F_ref` (`flapping_wing.py:246, 273-274`) | lab |
| `fig_forces` `CF_x..CF_z` | formed inline with `force_on_wing(...)/F_ref` (`generate_all_figures.py:261-284`) | lab |
| Flapping-wing benchmark `CF_chord`/`CF_normal`, and the body-frame diagnostics built on them (`cf_span`, the added-mass-subtracted diagnostic, the T4 decomposition) | `reconstruct_wing_body_forces` rotates by `R(t)ᵀ` (`flapping_wing.py:433`) | wing body |

On both committed corpora, `max|CF + F/F_ref|` is 0.0 exactly for x, y and z, using the
per-configuration `F_ref`. The `/review-openspec` math reviewer's failure-class list makes the same
claim ("By design, forces are in the wing frame"), and the review-openspec-skill spec pins it.

**#161: ω.** In the page's kinematics table `ω = 2πf`. In `F_ref = ½·ρ·ω²·S_yy` it is the peak stroke
rate, which the page never defines. The normative definition is in the force-surrogate spec
("Single-source force normalization") and `compute_force_reference`:
`ω_peak = 2π·f_star·radians(phi_amp_deg)`. This is exactly `max|φ̇|` for the sinusoidal stroke.

Recomputed from the code at the validated point (`f* = 1`, `φ_amp = 70°`, `R_GYRATION = 1.69849`,
span 3, chord 1, ρ = 1):

| Quantity | Value |
|---|---|
| `S_yy = R_GYRATION²·area` | 6.79732 |
| `ω_peak = 2π·radians(70)` | 7.67636 |
| `F_ref` (code) = `½·ρ·ω_peak²·S_yy` | 200.271 |
| `F_ref` with `ω` read as `2π` | 134.174 |
| ratio = `radians(70)²` | 1.49263 |

The issue gives 200.26; the code gives 200.271, so that is a rounding slip. Corpus configurations
have their own `F_ref` (36.17–163.51). 200.27 is the validated point only.

The coordinate-convention spec, the flapping-wing-validation spec (four requirements),
`examples/flapping_wing/RESULTS.md` and `figures/README.md` also write `F_ref` with a bare `ω`.

## What Changes

**`docs/coordinate-convention.md`**

- "Forces" names each coefficient family with its frame, one family per sentence.
  `CF_chord`/`CF_normal` and the diagnostics built on them are in the wing body frame, with `F_y`
  intentionally dropped, following van Veen. The corpus and surrogate `CF_x..CF_z`, the
  flapping-wing lab series `cf_x_ib`/`cf_z_ib` and the `fig_forces` `CF_x..CF_z` are "lab-frame
  components of the IB force on the wing". The lab-frame `cf_*_added`/`cf_*_hydro` are named as not
  the IB force alone, and the sign section names the frame of each 6-DOF series. That phrase shares
  its prefix with `comparison_figure.LAB_FRAME_PHRASE` ("lab-frame components of the IB force and
  moment on the wing; moments about the hinge"), so the page and the figures use the same words.
- The normalization block:
  - writes `F_ref = ½·ρ·ω_peak²·S_yy` and keeps the "van Veen (2022, eq 1.1) normalization" citation;
  - gives `ω_peak = 2π·f_star·radians(phi_amp_deg)` as this project's constant normalization scale.
    Van Veen's simulations include accelerating strokes, and the repository's implementation of his
    model uses the instantaneous stroke speed, so `F_ref` is a fixed reference force, not van Veen's
    instantaneous scaling;
  - says it is not the `` `ω = 2πf` `` of the table;
  - places the speed `ω_peak·r_gyr` at the radius of gyration (today it says the stroke *rate* is "at"
    the radius);
  - quotes `ω_peak ≈ 7.676` and `F_ref ≈ 200.27` at the validated point, with `F_ref` computed per
    configuration;
  - links `openspec/specs/force-surrogate/spec.md` and `compute_force_reference` as the single source.
- "Moments":
  - "Frame: lab, not wing." now says, in one sentence, that moments are lab-frame components about the
    hinge, like the corpus `CF_x..CF_z`. A second sentence contrasts them with `CF_chord`/`CF_normal`.
    It keeps `R(t)ᵀ`.
  - The rest-pose note says the page carries wing-frame `CF_chord`/`CF_normal` beside lab-frame
    `CF_x..CF_z` and moments.
- The sign section's `F_ref = ½·ρ_f·ω²·S_yy` becomes `ω_peak²`. Its pinned bullets and pending phrases
  are unchanged.

**`.claude/commands/review-openspec.md`** (Subagent 6 prompt)

- Failure class 1 states the frame of each family:
  - the flapping-wing body-frame family (`CF_chord`/`CF_normal` and the diagnostics built on them) is
    wing-frame;
  - the corpus and surrogate `CF_x..CF_z`, the flapping-wing lab-frame series and the moments are
    lab-frame components;
  - derived `CF_m*` are about the deck's hinge, and raw `Mx..Mz` are about the particle origin.
- The authority note becomes "`docs/coordinate-convention.md` is narrative only and has been wrong
  before (#108, #181)".

**`examples/flapping_wing/RESULTS.md`**

- The normalization paragraph (line 151) and the `F_ref` row (line 163) write `ω_peak`. The paragraph
  also places the speed, not the rate, at the radius of gyration. It says `ω_peak` is the peak stroke
  rate, not `2πf`, and links the convention page's `#forces` section instead of restating the formula.
- The `u_ref` row (line 160) writes `radians(phi_amp)`. Its value 13.04 holds only in radians.
- The lab-frame table row label "CF_x range (chord / streamwise)" (line 181) becomes "lab x,
  streamwise", and the z row becomes "lab z, vertical / lift". This is the #181 mix-up in a file this
  change already edits.

**`examples/flapping_wing/figures/README.md`**

- The `fig_forces` row (line 21) writes `ω_peak`.

**Spec deltas** (all MODIFIED; see `specs/`)

- **coordinate-convention**, "Project-wide axis convention matches van Veen 2022, documented
  atomically":
  - The body states the frame of each family.
  - It writes `F_ref = ½·ρ·ω_peak²·S_yy` computed per configuration. It refers to the force-surrogate
    spec for `ω_peak` and does not define it again.
  - The existing scenario "Convention page states the van-Veen-faithful axes and normalization" names
    the body-frame pair and writes `ω_peak`.
  - Three scenarios are added; the guard tests implement them.
- **flapping-wing-validation**: `ω²` → `ω_peak²` in four requirements, and nothing else changes:
  - "Van Veen-faithful force-coefficient convention, no correction factor";
  - "Added-mass decomposition reported separately (not graded by the gate)";
  - "Body-frame (chord/normal) per-component van Veen comparison";
  - "Added-mass-subtracted body-frame CF diagnostic (reported; #40 cheap interim)".

  "Van Veen quasi-steady force model, pinned and guarded" keeps its `ω`, the model's instantaneous
  stroke speed.
- **review-openspec-skill**, "Math and Physics Review Checklist":
  - the failure-class wording and its scenario anchors;
  - `narrative only` becomes an authority anchor, and `uses ω for two quantities` is forbidden.

**Tests, written first**

- New `tests/test_convention_frames_and_omega.py`.
- New fixture `tests/fixtures/convention_page/pre_181_161.md`.
- `tests/test_review_openspec_command.py` gains anchors and forbidden phrases.

**`docs/CHANGELOG.md`**: one Unreleased `### Fixed` entry.

## Out of scope

- `src/mosquito_cfd/force_surrogate/` (another session owns it). Its docstrings, the other `src`
  comments, `generate_all_figures.py:273`, `docs/force_surrogate/roadmap.md:92,94`, and the
  `ω_ref` naming at flapping-wing-validation spec line 710 are in #202. That `ω_ref` is defined as
  `ω_peak`, so it is not wrong.
- The `fig_forces` legends (`generate_all_figures.py:311,313`, pinned by
  `test_flapping_wing_sign_use_sites.py`) and the `CF_x`↔`CF_chord` sentence at
  `docs/force_surrogate/roadmap.md:226` are in #203.
- `add-surrogate-comparison-bench`, #192 corpus regeneration, PR #198.
- No code, data or behaviour change, and no coefficient value changes.

## Impact

- **Affected specs:** coordinate-convention (1 requirement), flapping-wing-validation (4 requirements),
  review-openspec-skill (1 requirement).
- **Affected files:**
  - `docs/coordinate-convention.md`
  - `.claude/commands/review-openspec.md`
  - `examples/flapping_wing/RESULTS.md`
  - `examples/flapping_wing/figures/README.md`
  - `docs/CHANGELOG.md`
  - new `tests/test_convention_frames_and_omega.py`
  - new `tests/fixtures/convention_page/pre_181_161.md`
  - `tests/test_review_openspec_command.py`
  - `openspec/changes/fix-convention-page-frames-omega/mutation-results.md`
- **Existing guards that constrain the wording and must stay green:**
  - `test_coordinate_convention_sign.py`: the sign bullets, pending phrases and evidence location;
  - `test_kinematics_attribution.py`: "van Veen (2022, eq 1.1) normalization", the table cells,
    "Sourced verbatim from van Veen 2022 §2.4", "van Veen §2.4" and #142;
  - `test_new_convention_deck_and_docs.py`: `## moments`, "declared pivot", `R(t)`,
    `kernel.location`;
  - `test_t4_stale_claims.py`: the new CHANGELOG entry must not mention #141;
  - `test_flapping_wing_validation.py` and `test_results_reproducibility.py`: `200.27`,
    `−Fz / F_ref` and the frame words in RESULTS.md;
  - `test_no_false_diffused_ib_claim`: no `×` multiplier wording near 2.4;
  - `test_live_spec_claims.py`;
  - the `#moments` and `#force-and-moment-sign` anchors.
- **Active changes:** none has a delta on these three capabilities. `add-surrogate-comparison-bench`
  touches force-surrogate only. The new guard reads the effective specification, so any later delta
  that writes a bare `ω²·S_yy` will turn it red, as intended.
