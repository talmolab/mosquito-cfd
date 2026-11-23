# Design: fix-convention-page-frames-omega

## D1. Name the quantity, not "forces"

The page does not choose a single force frame, because the wing coefficients come in two frames:

| Coefficients | Producer | Frame |
|---|---|---|
| `CF_chord`, `CF_normal` (and `cf_span`) | `flapping_wing.reconstruct_wing_body_forces` / `body_frame_coefficients` (rotates by `R(t)ᵀ`) | wing body frame, spanwise dropped in the van Veen comparison |
| body-frame diagnostics: added-mass-subtracted `cf_added`/`cf_6dof`, the T4 decomposition | `body_frame_added_mass_subtracted`, `decompose_wing_force` (same rotation) | wing body frame, not all the IB force |
| corpus and surrogate `CF_x..CF_z` | `force_surrogate.dataset.build_dataset`, `−F/F_ref` | lab, IB force on the wing |
| flapping-wing lab series `cf_x_ib`/`cf_z_ib` | `flapping_wing.reconstruct_wing_forces`, `−F/F_ref` | lab, IB force on the wing |
| `cf_*_added` (`ρ_f·SumU`), `cf_*_hydro` (6-DOF) | `reconstruct_wing_forces` | lab, not the IB force |
| `CF_mx..CF_mz` | `build_dataset` after `shift_moment_reference` | lab, about the hinge |

The sphere and heaving-ellipsoid coefficients are not wing coefficients and are not affected.

Every sentence about frames, on the page and in the review prompt, names the family it describes.
The page names the lab-frame IB series explicitly (corpus/surrogate `CF_x..CF_z`, `cf_x_ib`/`cf_z_ib`).
It does not claim that "every other" coefficient is lab-frame, because the table above shows that is
false.
The lab-frame wording shares the prefix "lab-frame components of the IB force" with
`comparison_figure.LAB_FRAME_PHRASE`. That module is out of scope, so the page writes the phrase out
and the guard does not import the constant.

**The guard checks the claim against the data as well as the wording.**
- `_parquet_on_wing` (imported from `test_coordinate_convention_sign`, along with `_CORPUS_PARQUETS`)
  requires each of `CF_x`, `CF_y` and `CF_z` to equal `−F/F_ref` of the same raw column, using the
  per-configuration `F_ref`. A rotated coefficient mixes components and fails.
- `flapping_series_on_wing()` does the same for the flapping-wing lab series.
- A permanent negative control writes a corpus copy whose coefficients are rotated about lab z by a
  fixed angle, and asserts the check fails. The guard is then shown to separate "rotated" from
  "unrotated" every CI run, not only in a one-off mutant.

**Text checks are pure functions of a string.**

Normalization:
- They strip `**`/`*` emphasis, `_…_` emphasis only where the underscores are paired at word
  boundaries (so `CF_chord`, `F_ref` and `ω_peak` survive), backticks and `>` markers, then collapse
  whitespace.
- Sentences split on `. ` or a bullet start, not on the `..` inside `CF_x..CF_z`.

What a check asks for:
- **Co-occurrence alone does not stop a frame swap.** One sentence can hold both families. Each check
  therefore asks for the family with its frame and without the other frame's phrase:
  - the `CF_chord`/`CF_normal` sentence must not contain `lab-frame`;
  - the `CF_x..CF_z` sentence must not contain `wing body frame`.
- **Flapping-wing lab series.** Its sentence must name `plausibility_gate` or `fig_forces` with
  `lab-frame components`. The series' own name contains "lab-frame", so the name alone would satisfy a
  looser check.
- **Moments.** The sentence must hold both `lab-frame components about the hinge` and `CF_x..CF_z`.
  Today's page already has the first phrase, so that phrase alone would not fail on the old text.

The fixture:
- The functions run on the live page and on a committed frozen copy of the pre-change sections,
  `tests/fixtures/convention_page/pre_181_161.md`.
- The test asserts that each check fails on the fixture, except `intentionally dropped`, which the old
  page already has. So "the guard fails on the old wording" holds on every CI run without git history.
  CI checks out at depth 1.

## D2. ω_peak is defined in one place; the page restates it once and is tied to the code

The force-surrogate spec's "Single-source force normalization" defines
`ω_peak = 2π·f_star·radians(phi_amp_deg)`. The coordinate-convention delta names the symbol and
refers to that requirement. It does not give the formula again. The page is narrative, so it gives
the formula once, for the reader.

**The page quotes `ω_peak ≈ 7.676`.** This is the one new number, and it is what separates the peak
rate from `2π`.

**It also quotes `F_ref ≈ 200.27`,** because a reader of the convention page needs the reference
value next to the formula. The guard recomputes both values at the precision printed:
- `ω_peak` from the `constants` values;
- `F_ref` from `compute_force_reference`.

Every `ω_peak ≈`/`F_ref ≈` quote is checked, with at least one of each and at least two decimals,
using `_spec_claims.format_like`. A change to the constants then fails the guard instead of leaving
the page stale.

**That recomputation is internal consistency only:** the page, the guard and the code share one
formula. A known-answer check ties the name "peak stroke rate" to the kinematics.
`2π·f·radians(φ_amp)` must equal `max|wing_kinematics.stroke_rate|` over a dense grid on one
wingbeat, at the validated point and at a corpus corner (f* = 1.15, 55°). A shared radians or `2π`
slip would fail it.

**The page states that `F_ref` is computed per configuration.** Corpus `F_ref` spans 36.17–163.51, so
200.27 must not read as the corpus value.

**Attribution.** Van Veen's simulations hold the stroke rate constant after acceleration, so "the
stroke rate" in eq 1.1 needs no qualifier there. Taking the sinusoid's peak is this project's
constant evaluation of it, and the page says so. The paper's exact wording of eq 1.1 was not
re-checked in this change. The page keeps the citation the project already uses.

## D3. The bare-ω guard has one exemption, which must still be needed

**Pattern.** `ω(?:²|\^2|\*\*2)\s*[·⋅]?\s*S_yy`. It does not match `ω_peak²`.

**Search set:**
- the convention page, `RESULTS.md`, `figures/README.md`;
- each requirement block of the effective specification of coordinate-convention and
  flapping-wing-validation (`_spec_claims.effective_spec`, the live spec with every active change's
  delta applied). Iterating blocks lets the guard skip one block by name.

**The exemption.** In flapping-wing-validation's "Van Veen quasi-steady force model, pinned and
guarded", `ω` is the model's instantaneous stroke speed: `model_inputs` passes `|φ̇|`, so `½ρω²S_yy` is
correct there. The guard skips that block. It fails with the requirement's name if the block is
missing or no longer matches. A synthetic test confirms that check.

**Positive checks.** The specific rows are also checked, so a fix that drops the expression cannot pass:
- RESULTS.md :151 and :163 and the `fig_forces` row must contain `ω_peak²`;
- the `u_ref` row must contain `radians(phi_amp)`.

**Spec half of the red run.** `effective_text` already applies this change's deltas, so the spec half
of the guard cannot be seen red on this branch. The red run records:
- the five doc hits: page :98 and :207, RESULTS :151 and :163, figures/README :21;
- the spec half against the live specs only (`changes_dir` set to an empty temporary directory),
  which gives 6 hits: coordinate-convention 2 and flapping-wing-validation 4.

`src/` is outside the search set, because `src/mosquito_cfd/force_surrogate/` is out of scope (#202).
The guard's module docstring names #202 so the set can grow later.

## D4. Live-spec claim guard

`test_live_spec_claims.py` guards two flapping-wing-validation requirements:
- "Stroke motion reproduces van Veen's translational sweep";
- "Retired kinematics and T4 claims stay out of this specification".

This change modifies neither. The modified requirements add no numbers. Task 2.5 runs the guard with
the delta active; it ran green during review (`test_live_spec_claims.py`: 155 passed).

## D5. Deltas are copies plus substitutions

Each MODIFIED block was generated from the live requirement by asserted single-occurrence string
substitutions, and the review diffed each block against the live text.

The intended differences:
- **flapping-wing-validation:** `ω` → `ω_peak` in four places, plus one link clause.
- **coordinate-convention:**
  - the force sentence becomes a frame list and a normalization paragraph;
  - the existing first scenario's Then is reworded;
  - three scenarios are added.
- **review-openspec-skill:**
  - the frame wording, and a clause on the authority note;
  - `narrative only` added to the first scenario, with one AND line;
  - four anchors and one AND line added to the second scenario.

## D6. Commits

Red tests are never committed, and nothing is marked xfail. The red runs are recorded in
`mutation-results.md` and the PR description. Each commit lands a guard together with the text it
guards:

1. `docs(openspec): propose fix-convention-page-frames-omega (advances #181, advances #161)`
   - the change dir.
   - CI green: only deltas, which validate and keep `test_live_spec_claims` green.
2. `fix(docs): name the frame of each force and write ω_peak in F_ref (advances #181, advances #161)`
   - the page, RESULTS.md, figures/README.md, the new test, the fixture, `mutation-results.md`.
3. `fix(review-openspec): state the frame of each force family (advances #181)`
   - the skill file and its test.
4. `docs(changelog): ...`
   - CHANGELOG.

Merge main in; never rebase.
