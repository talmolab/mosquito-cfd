# Tasks: fix-convention-page-frames-omega

TDD throughout. Each test is written and run **red against today's text** before the text it guards is
edited. Red tests are never committed and nothing is marked xfail (design D6). The red runs go in
`openspec/changes/fix-convention-page-frames-omega/mutation-results.md` and the PR description. Every
`read_text` passes `encoding="utf-8"`.

## 1. Guards first (red)

- [x] 1.1 Fixture `tests/fixtures/convention_page/pre_181_161.md`.
  - A verbatim copy of today's `## Forces` and `## Moments` sections of `docs/coordinate-convention.md`.
  - A header line names the source commit (`246f0a0`) and says it is a frozen negative control.
- [x] 1.2 New `tests/test_convention_frames_and_omega.py`, scenario "Each reported force quantity is
  named with its frame".
  - **Text checks:** pure functions over normalized text (design D1): strip `**`/`*` emphasis, paired
    `_…_` emphasis only at word boundaries, backticks and `>` markers, then collapse whitespace. Split
    sentences on `. ` or bullets, not on the `..` in `CF_x..CF_z`.
    - `## Forces` has one sentence holding `CF_chord`/`CF_normal` and `wing body frame`, but not
      `lab-frame`.
    - One sentence holds `CF_x..CF_z` and `lab-frame components of the IB force`, but not
      `wing body frame`.
    - One sentence holds `plausibility_gate` or `fig_forces` together with `lab-frame components`.
    - `intentionally dropped` stays in `## Forces`.
    - None of `forces are reported in the wing body frame`, `Unlike the forces above` and
      `body-frame forces` appears anywhere on the page.
    - `## Moments` has one sentence holding both `lab-frame components about the hinge` and
      `CF_x..CF_z`.
  - **Fixture:** each text check except `intentionally dropped` is asserted to fail on the 1.1 fixture.
    The old page already contains that phrase.
  - **Data:**
    - `assert _parquet_on_wing(p) is True` for each `p` in `_CORPUS_PARQUETS`, and
      `assert flapping_series_on_wing() is True`. Both helpers are imported from
      `test_coordinate_convention_sign`.
    - Negative control: a `tmp_path` corpus copy with `(CF_x, CF_y)` rotated 30° about lab z must make
      `_parquet_on_wing` return False.
  - **Expected red on today's page:**
    - no lab-frame sentences in Forces;
    - no Moments sentence holding `CF_x..CF_z`;
    - all three forbidden phrases present.
- [x] 1.3 Same file, scenario "F_ref is written with ω_peak, tied to the code and to the kinematics".
  - **`F_ref` expressions:** on the flattened page, `F_ref\s*=` matches at least twice. Each match, up to
    and including the first following `S_yy`, contains `ω_peak²` and has no `ω(?!_peak)`.
  - **Required content:** the page contains `ω_peak = 2π·f_star·radians(phi_amp_deg)`, `` `ω = 2πf` ``,
    `compute_force_reference` and `computed per configuration`.
  - **Link:** a markdown link whose target, resolved from `docs/`, is
    `openspec/specs/force-surrogate/spec.md` and exists.
  - **Quoted values:** every `ω_peak\s*≈\s*([0-9.]+)` and `F_ref\s*≈\s*([0-9.]+)` match (at least one of
    each, each with at least two decimals) equals the recomputed value under `_spec_claims.format_like`.
    - Recomputed values: `2π·VALIDATED_F_STAR·radians(VALIDATED_PHI_AMP_DEG)` and
      `compute_force_reference(VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, R_GYRATION, SPAN, CHORD, RHO).f_ref`.
    - Negative control: a synthetic page quoting `F_ref ≈ 134.17` fails the value check.
  - **Known answer:** `2π·f·radians(φ_amp)` equals `max|stroke_rate(t, frequency=f, stroke_amp_rad=…)[0]|`
    over 20 001 points of one wingbeat (rel 1e-6), at (1.0, 70°) and (1.15, 55°).
  - **Kinematics table:** keeps `φ_amp·sin(ωt)` and `α_amp·cos(ωt)`.
  - **Expected red:** no `ω_peak` on the page.
- [x] 1.4 Same file, scenario "No bare ω in F_ref in the documents that restate the normalization".
  - **Pattern:** `ω(?:²|\^2|\*\*2)\s*[·⋅]?\s*S_yy`.
  - **Search set:**
    - the page, `RESULTS.md` and `figures/README.md`;
    - each block of `_spec_claims.effective_spec` for coordinate-convention and
      flapping-wing-validation, skipping "Van Veen quasi-steady force model, pinned and guarded" by name.
  - **Exemption:** the guard fails with that name if the block is missing or no longer matches.
    Negative control: a synthetic block without a match fails that check.
  - **Positive checks:**
    - the RESULTS.md normalization paragraph, the `Force reference F_ref` row and the
      `figures/README.md` `fig_forces` row contain `ω_peak²`;
    - the `Reference speed u_ref` row contains `radians(phi_amp)`.
  - **Expected red:**
    - five doc hits: page :98 and :207, RESULTS :151 and :163, figures :21, plus the failing positive
      checks;
    - the spec half, recorded by one run with `changes_dir` set to an empty `tmp_path`, which gives 6
      hits on the live specs.
- [x] 1.5 `tests/test_review_openspec_command.py`.
  - Add `CF_chord`, `CF_x..CF_z`, `flapping-wing lab-frame series` and `lab-frame components` to
    `FAILURE_CLASSES`.
  - Add `narrative only` to `AUTHORITY_AND_METHOD`.
  - The failure-class block must contain none of `forces are in the wing frame`,
    `forces in the wing frame` and `By design, forces`.
  - The whole Subagent 6 template must not contain `uses ω for two quantities`.
  - **Expected red** on today's skill file.
- [x] 1.6 One-off mutants, only for what the permanent negative controls in 1.2–1.4 do not cover. Run
  with `PYTHONDONTWRITEBYTECODE=1`, alone (no other test run), restoring from saved bytes, on a copy of
  the page:
  - put back each forbidden phrase alone;
  - swap the frames of `CF_chord` and `CF_x..CF_z`;
  - write one `F_ref` expression as `F_ref=½·ρ·ω²·S_yy` (no spaces);
  - use `⋅` in a bare form.

  Each mutant must turn the guard red. Record the results in `mutation-results.md`.

## 2. Text fixes (green)

- [x] 2.1 `docs/coordinate-convention.md`:
  - "Forces": the frame of each family, `ω_peak` defined with its attribution, `` `ω = 2πf` ``, the
    speed `ω_peak·r_gyr` at the radius of gyration, values, per configuration, and links.
  - "Moments": the "Frame: lab, not wing." sentence (keep `R(t)ᵀ`) and the rest-pose note.
  - Sign section: `F_ref` only.
  - Keep the sign bullets, pending phrases, "van Veen (2022, eq 1.1) normalization", the kinematics
    table, and both `##` headings and their anchors.
- [x] 2.2 `.claude/commands/review-openspec.md`: failure class 1 and the authority note.
- [x] 2.3 `examples/flapping_wing/RESULTS.md` lines 151, 160, 163 and 181–182, and
  `examples/flapping_wing/figures/README.md` line 21. Keep `200.27`, `−Fz / F_ref`, `body-frame` and
  `lab-frame`.
- [x] 2.4 `docs/CHANGELOG.md`: an Unreleased `### Fixed` entry. It covers:
  - the frame statements;
  - `ω_peak` in `F_ref`;
  - the new guard;
  - the review-prompt wording;
  - "no coefficient values change";
  - follow-ups #202 and #203.

  It must not mention #141.
- [x] 2.5 Run 1.2–1.5 green. Then run the full `uv run --frozen pytest -m "not gpu"` from Git Bash.
  This covers the guards listed under Impact, plus `test_force_surrogate_normalization.py` and
  `test_force_surrogate_driver.py`. It also re-confirms D4 (`test_live_spec_claims.py` with the deltas
  active).
- [x] 2.6 Lint and validate:
  - `uv run --frozen ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`;
  - `ruff format --check` on the same scope;
  - `openspec validate fix-convention-page-frames-omega --strict`.

## 3. Reconcile and ship

- [x] 3.1 Re-read the proposal, design, tasks and deltas against the diff. Any deviation goes into a
  `### Why N instead of M?` note.
- [x] 3.2 Commit per design D6. Commits say "advances #181" / "advances #161", never a closing or
  negated closing keyword.
- [x] 3.3 Review and pre-merge:
  - Run `/review-pr`, then `/pre-merge-check`, with no Copilot review.
  - Before every push: merge main in (no rebase), then `git merge-base --is-ancestor origin/main HEAD`.
  - Get the user's approval before the first push and before writing "Closes #181 / Closes #161" in
    the PR body.
