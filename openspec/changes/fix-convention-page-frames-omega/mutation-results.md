# Red runs and mutants: fix-convention-page-frames-omega

Recorded 2026-11-23 on `fix-convention-page-frames-omega` at `246f0a0`, with the change's spec deltas
present and the docs not yet edited.

## Red run of the new guards against the old text (tasks 1.2–1.5)

`uv run --frozen pytest tests/test_convention_frames_and_omega.py`: **11 failed, 21 passed.**

Failing:
- `test_page_names_the_frame_of_each_force_family`, for `body_frame_sentence`, `lab_corpus_sentence`,
  `flapping_lab_sentence`, `moments_sentence` and `no_forbidden_phrase`.
  `keeps_spanwise_drop` passes, because the old page already says "intentionally dropped".
- `test_every_f_ref_expression_uses_omega_peak`: two expressions, `F_ref = ½·ρ·ω²·S_yy` and
  `F_ref = ½·ρ_f·ω²·S_yy`.
- `test_page_defines_omega_peak_and_names_the_single_source`: no `ω_peak = 2π·f_star·radians(phi_amp_deg)`.
- `test_page_links_the_force_surrogate_spec`: the only resolved link target was `docs/force_surrogate`.
- `test_quoted_values_match_the_code`: no quoted `ω_peak ≈` or `F_ref ≈`.
- `test_documents_have_no_bare_omega_in_f_ref`: the five doc hits:
  - `docs/coordinate-convention.md:98` and `:207`;
  - `examples/flapping_wing/RESULTS.md:151` and `:163`;
  - `examples/flapping_wing/figures/README.md:21`.
- `test_results_and_figures_rows_write_omega_peak`.

Passing on the old text, as designed:
- the fixture tests, which assert that each check fails on the frozen copy;
- the data checks: both corpora and the flapping-wing lab series are `−F/F_ref` unrotated;
- the 30°-rotation, `134.17`, synthetic-exemption and unspaced-`F_ref` negative controls;
- the known-answer `ω_peak = max|φ̇|` tests at (1.0, 70°) and (1.15, 55°);
- `test_effective_specs_have_no_bare_omega_in_f_ref` and `test_exemption_is_still_needed`. These
  read the effective spec, which already includes this change's deltas.

**Spec half, against the live specs only** (`spec_bare_omega_hits(changes_dir=<empty tmp dir>)`):
5 requirement blocks, holding 6 matches.
- coordinate-convention: "Project-wide axis convention matches van Veen 2022, documented
  atomically" (2 matches).
- flapping-wing-validation, 1 match each:
  - "Van Veen-faithful force-coefficient convention, no correction factor";
  - "Added-mass decomposition reported separately (not graded by the gate)";
  - "Body-frame (chord/normal) per-component van Veen comparison";
  - "Added-mass-subtracted body-frame CF diagnostic (reported; #40 cheap interim)".

The exempt "Van Veen quasi-steady force model, pinned and guarded" holds 2 matches in both views.

`uv run --frozen pytest tests/test_review_openspec_command.py`: **2 failed, 44 passed.**
- `test_subagent6_authority_and_method`: "must not contain 'uses ω for two quantities'".
- `test_subagent6_failure_classes`: "missing anchor 'CF_chord'".

## Green

After the text fixes:
- both files: 78 passed;
- full `uv run --frozen pytest -m "not gpu"`: 3467 passed, 28 skipped, 21 deselected;
- ruff check and format on the CI scope: clean;
- `openspec validate --strict`: valid.

## One-off mutants (task 1.6)

The text checks are pure functions of a string. Each mutant was therefore applied to an in-memory
copy of the edited page, and no file was modified, so the stale-`.pyc` and concurrent-run traps do
not arise. It was run once with `PYTHONDONTWRITEBYTECODE=1` and no other test run.

| Mutant | Result | Caught by |
|---|---|---|
| put back `forces are reported in the wing body frame` | KILLED | `no_forbidden_phrase` |
| put back `Unlike the forces above` | KILLED | `no_forbidden_phrase` |
| put back `body-frame forces` | KILLED | `no_forbidden_phrase` |
| swap the frames of `CF_chord`/`CF_normal` and `CF_x..CF_z` | KILLED | `body_frame_sentence`, `lab_corpus_sentence` |
| `F_ref=½·ρ·ω²·S_yy` (no spaces) | KILLED | `f_ref_expression_failures`, `BARE_OMEGA` doc scan |
| `F_ref = ½·ρ·ω²⋅S_yy` (`⋅` operator) | KILLED | `f_ref_expression_failures`, `BARE_OMEGA` doc scan |

### Why an in-memory copy instead of a copy of the page on disk?

Task 1.6 said "on a copy of the page". The checks take the page text as an argument, so an in-memory
copy tests the same code path, and nothing needs restoring.

## After PR review round 1

The hardened checks were re-run on `git show 246f0a0:docs/coordinate-convention.md` in memory:
every frame check except `keeps_spanwise_drop` is False (including the new
`no_contradicting_frame_sentence`); `f_ref_expression_failures` reports both bare expressions and
"found 0" `ω_peak²` expressions; `quoted_value_failures` reports no quotes; the widened bare-ω scan
finds 2 hits on the old page and the same 5 live-spec blocks. On the 246f0a0 review-openspec prompt,
`check_failure_classes`, `check_authority_and_method` and `check_failure_class_frames` each fail.
The reviewers' mutants that survived round 0 are now permanent negative controls in the two test
files.
