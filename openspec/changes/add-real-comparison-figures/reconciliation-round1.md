# Reconciliation of review round 1

Each entry quotes the reviewer's finding (the operative sentence, verbatim), says how the
revision addresses it, and says where the reviewer's mechanism now appears.

Abbreviations:

- **viz** = `specs/visualization-tooling/spec.md`
- **fs** = `specs/force-surrogate/spec.md`
- **Req** = requirement
- **Sc** = scenario

## BLOCKING

**T-B1.** "With task 2.1's real-helper fixture, `runs[0].per_target.c.skill == phase_baseline_skill.per_target.c.skill` by construction … The test cannot be written as stated."

- **Addressed:** the scenario is reworded exactly as the reviewer proposed. A guard is added, with a
  test: `runs[0].skill` must equal `phase_baseline_skill`.
- **Where:**
  - viz, MODIFIED Req "…reproduce their source data exactly…": first bullet ("SHALL require
    `runs[0].per_target.<c>.skill` to equal `phase_baseline_skill.per_target.<c>.skill` exactly");
  - viz, Sc "the skill-range values are the seed sweep, verbatim" ("none equals any `r2`, `rmse`,
    `config_mean_r2`, `phase_baseline_r2` or `phase_baseline_rmse` value; and the primary seed's
    value equals `phase_baseline_skill…`");
  - viz, Sc "a primary seed that disagrees with the phase-baseline block is refused";
  - design D2 Guards; tasks 4.1.

**T-B2.** "Restructure on the `_readme_guards` pattern: a pure `check_committed_figure(root: Path, figure: str) -> None` that raises `AssertionError` with specific messages. Test it on a synthetic repo layout in `tmp_path` … Specify the edit: 'replace the last digit of the first `skill` value'."

- **Addressed:** adopted as specified, including the digit edit and the injected git metadata.
- **Where:**
  - viz, ADDED Req "Committed comparison figures stay current with their inputs and renderer":
    "A pure test helper `check_committed_figure(root, figure)` SHALL raise `AssertionError`…";
  - its Sc "the check fails for each kind of staleness" ("the last digit of the first `skill` value
    in the fine `metrics.json` changed");
  - design D7; tasks 9.1.

**T-B3.** "Require repo-relative paths: no drive letter, no leading `/`, no `..`. The committed test must resolve each `input_files[role].path` against the repo root and hash that file … Factor a pure `_portable_path` helper and test it with `PureWindowsPath(...)` on every OS."

- **Addressed:** adopted.
- **Where:**
  - viz, ADDED Req "Committed comparison figures stay current…": "Every recorded path SHALL be
    repository-relative, written with forward slashes, with no drive letter, no leading `/` and no
    `..`. A pure `_portable_path(path, root)` SHALL produce it…" and "every `input_files` path to
    resolve under `root` to a file whose sha256 equals the recorded one";
  - Sc "recorded paths are portable on every OS" (`PureWindowsPath` / `PurePosixPath`);
  - design D5 Paths; tasks 3.2.

**T-B4.** "Add a guard and a test: a non-primary `config_mean_r2 = 1.5` (also `1 + 1 ulp`) is refused, naming corpus, target, seed and `config_mean_r2`."

- **Addressed:** adopted.
- **Where:**
  - viz, ADDED Req "The cycle-mean R² diagnostic…": "The builder SHALL refuse any
    `config_mean_r2 > 1`";
  - Sc "boundary values of R²": "`1.5` and `nextafter(1, 2)` are each refused, naming the corpus,
    target, seed and `config_mean_r2`";
  - design D4 Checks; tasks 6.1.

**G-B1.** "No task commits the untracked `openspec/changes/add-real-comparison-figures/`, so porcelain shows `??`. Ticking boxes in `tasks.md` leaves a modified tracked file … Fix: add a commit 0 that commits the proposal, and commit task ticks before rendering. Check with `git status --porcelain --untracked-files=all`."

- **Addressed:** adopted.
- **Where:**
  - tasks 0.3 (proposal commit);
  - tasks 8.3 (commit the task ticks);
  - tasks 8.4 and 9.3 (`git status --porcelain --untracked-files=all`);
  - design D7 (the `git.dirty` weakness is documented).

**D-B1 / S-I1.** "The bullet has `~**1.3×**`, which `_QS_RATIO` … does not match … It also has 'down from ~2.3× …', a third match … the guard must be scoped to this one bullet … Rewrite the sentence with plain `~1.3×` and `~1.4×`, and drop or reword the '~2.3×' historical ratio."

- **Addressed:** adopted. The bullet slice, the two plain tokens, and the historical ratio written
  without the `~x×` form.
- **Where:**
  - fs, ADDED Req "The coarse README's quasi-steady paragraph…": "The bullet is the text … from
    `The Sane–Dickinson` to the next top-level `- **` bullet … exactly two tokens of the form
    `~<x.x>×`, with no markup between `~` and the number … Any other multiplier in that bullet SHALL
    NOT use the `~<number>×` form";
  - Sc "The guard rejects each defect" (`~**1.3×**`, a third `~2.3×`);
  - design D9 Coarse README; tasks 10.1–10.2.

**D-B2.** "Fix: add a new sibling section `### Comparison figures` (no 'Coarse vs fine' in its title) with the links, one-line reading guide and recipe. Inside 'Coarse vs fine' add one neutral sentence linking to it."

- **Addressed:** adopted.
- **Where:** design D9 Fine README ("A new sibling section, `### Comparison figures` … Its heading
  does not contain 'Coarse vs fine' … one neutral sentence linking to that section
  (`_BANNED`-clean, no 'resolution')"); tasks 10.3.

**D-B3.** "Fix: add one sentence to the new 'Comparison figures' section: '`docker_image` in these sidecars is the fine corpus's CFD digest (the figure runs natively); `corpus_docker_images` holds both.' Leave the Speedup paragraph alone."

- **Addressed:** adopted.
- **Where:** design D9 Fine README ("that `docker_image` is the fine corpus's CFD digest, with both
  digests under `corpus_docker_images`"; "The Speedup section's `docker_image` paragraph is left
  untouched"); tasks 10.3.

## IMPORTANT

**S-I2.** "Add one scenario per refusal, or one parameterised scenario."

- **Addressed:** one parameterised scenario covers every refusal, plus a separate digest-first
  scenario.
- **Where:** viz, ADDED Req "Comparison figures validate their inputs before writing anything", Sc
  "each defect is refused before any output" and Sc "the digest is checked before any file"; tasks
  3.1.

**S-I3 / M-S5.** "Define the beat count `N` as the number of distinct `wingbeat` values in the dataset, and require contiguity from 0 or refuse. Define the holdout label as 'wingbeats 1..N-1 of N-beat runs', with the N=2 case rendering exactly 'second wingbeat of 2-beat runs'." Also: "Build the label from the predictions' wingbeat set as well as the dataset's."

- **Addressed:** adopted. The label counts beats from 1 (`wingbeats 2–N`), because `wingbeat` is
  0-based.
- **Where:**
  - viz, Req "…validate their inputs…", Beat structure: "The dataset `wingbeat` values SHALL be
    exactly `0..N−1`, and the prediction rows' values exactly `1..N−1`, or the builder refuses";
  - viz, Req "…captions and labels…", fourth bullet;
  - Sc "the beat label follows the data" (`wingbeats 2–4 of 4-beat runs`);
  - design D5 Beat structure.

**S-I4.** "List them in the requirement: `{coarse,fine}_{dataset,predictions,metrics,run_metadata}`."

- **Addressed:** listed. The role is named `surrogate_run_metadata` so it cannot be confused with
  the corpus-level `run_metadata.json`.
- **Where:** viz, MODIFIED Req "Every generated video or figure…", Sc "a builder with more than one
  input file…" (all eight roles listed); viz, Req "Committed comparison figures…" ("for the eight
  roles"); design D5 Inputs.

**S-I5.** "Pick one. Either say it is a shared load-time guard in design D5 and the spec, or restrict the scenario to `skill_ranges`."

- **Addressed:** it is a shared load-time guard, for every statistic.
- **Where:** viz, Req "…validate their inputs…" ("a `seed_sweep.range.<c>.<stat>` differs from the
  NaN-aware min/max of its runs"); design D2 ("shared loader guard, D5") and design D5; tasks 3.1.

**S-I6.** "Replace 'Every number' with 'Every quantity that `metrics.json` also records (...)' … ('recomputed, not read, and required to equal the recorded value')."

- **Addressed:** adopted verbatim.
- **Where:** viz, MODIFIED Req "…reproduce their source data exactly…", first sentence and third
  bullet ("it is recomputed, not read, and required to equal the recorded value").

**S-I7 / M-S7 / T-I10.** "Restrict the full recomputation to `*_metrics.json`. For `*_run_metadata.json`, enumerate the checked fields … State explicitly that `library_versions` is not compared with the live environment."

- **Addressed:** adopted, with the fields enumerated.
- **Where:** viz, Req "Committed comparison figures…" ("the committed `<figure>_metrics.json` to
  equal…"; then the enumerated `run_metadata` checks, including "(not compared with the running
  environment)"); design D7.

**S-I8.** "The spec never requires the '5 seeds / not a confidence interval' statement or the 'not … grid resolution' statement … Name the guard objects."

- **Addressed:** all caption phrases are now normative, and the guard objects are named.
- **Where:** viz, ADDED Req "Comparison-figure captions and labels state the scope and never compare
  the grids" (every phrase listed; `_readme_guards._COMPARATIVE` / `_FINE_COMPARATIVE` named; and
  `_BANNED` in the skill-ranges Req).

**S-I9.** "Keep a 2-sentence Why. For example: 'Both force surrogates are committed, but no figure compares them, and the two builders meant to … have never run on real data …'"

- **Addressed:** the Why is now a short paragraph that takes up the reviewer's two-sentence
  suggestion, followed by a short statement of what the change does. The detail moved under
  "### Background".
- **Where:** proposal.md `## Why`.

**T-I1.** "The fixture should assemble metrics exactly as `run_training` does … (a) Schema parity … (b) Hand-computed known answer … (c) Byte difference … The helper must create a null R² by construction."

- **Addressed:** adopted, all three parts.
- **Where:** tasks 2.1 (the `run_training` sequence with `build_metrics`; byte-distinct corpora;
  null by construction) and tasks 2.2 (a), (b), (c); viz, Sc "a null config-mean R² passes through
  as null" ("six true cycle means are equal").

**T-I2.** "Require the builder to return and record `notes: {target: text}` in the metrics sidecar, and assert on that. Also record each caption string in the sidecar."

- **Addressed:** adopted.
- **Where:**
  - viz, Req "skill-range figure…": "plus the notes (`{target: text}`) and the caption string";
  - viz, Req "error-histogram…": "and the caption string";
  - design D2 Sidecar; tasks 4.1.

**T-I3.** The list of missing tests: schema; all 8 missing files; ±inf; JSON NaN; zero rows; one config; R²=1; R²=−1e6; partial null; non-primary null; seed count and primary seed; bin-edge convention; waveform RMS; σ ddof; seeds-panel values; primary ε; swapped predictions; beat label from predictions.

- **Addressed:** every item has a spec scenario and/or a task.
- **Where:**
  - viz, Sc "each defect is refused before any output" (schema, missing files, ±inf/NaN, JSON NaN,
    zero rows, one configuration);
  - Sc "boundary values of R²" (1, −1e6);
  - Sc "a partial null is refused";
  - Sc "partially and fully null seeds";
  - Sc "required and forbidden wording" (seed 42, 3 seeds);
  - Sc "the counts follow the bin convention";
  - Sc "the scales are the stated statistics" (waveform RMS);
  - Sc "the diagnostic's R² is recomputed…" (σ = `sqrt(35/12)` fails if `ddof=1`);
  - Sc "every seed is plotted…" (primary ε);
  - Sc "predictions swapped between corpora are refused";
  - Sc "the beat label follows the data";
  - tasks 3.1, 4.1, 5.1, 6.1.

**T-I4.** "Call each builder with a mutable digest and non-existent corpus directories, and assert the raised `ValueError` is the digest error … parametrize over all three builders … perturb `max` and `min` separately, in each corpus."

- **Addressed:** adopted.
- **Where:** viz, Sc "the digest is checked before any file"; viz, Sc "each defect is refused…"
  ("a `range` off by one ulp at `min` and at `max`"; "each of the three builders"); tasks 3.1.

**T-I5 / M-I1.** "Compare the complements (`1−R²` against `ε²/σ²` …)" and "compare `ε²` with `σ²·(1−R²)` using `abs = 1e-12·σ²`, or compare `1 − ε²/σ²` with R² at `abs=1e-12`."

- **Addressed:** complement forms with `|a − b| ≤ 1e-12·max(1, |b|)`, which is absolute below 1
  and relative above. Skill is checked as `1 − skill` (the SSE ratio). Positive magnitudes keep
  `rel, abs=0`. Task 6.1 adds the reviewer's test, "a primary R² of `1 − 1e-6` is accepted".
- **Where:** viz, MODIFIED Req "…reproduce their source data exactly…", third bullet; viz, Req
  "The cycle-mean R² diagnostic…" ("within `1e-12·max(1, |1 − R²_primary|)`"); viz, Req
  "error-histogram" identity Sc; design D3 and D4.

**T-I6.** "Add: `phase_baseline_rmse` × (1 + 1e-8) refused; × (1 + 1e-11) accepted; `config_resolved.config_mean_r2` × (1 + 1e-10) refused. Replace 'etc.' with a full mutant list."

- **Addressed:** adopted.
- **Where:** viz, Sc "a baseline that does not reproduce metrics.json is refused" (1e-8 refused,
  1e-11 accepted); tasks 5.1, 6.1; tasks 7.4 (the full mutant list, no "etc.").

**T-I7.** "3.2 lists its tests after 'Implement' … 3.9 comes after … 3.11 … will likely never be red."

- **Addressed:** each section now writes its tests first. Caption tests sit inside each figure's
  test-first task. Leak and partial-write tests come before the implementation, in task 3.2.
- **Where:** tasks 3.1–3.3, 4.1, 5.1, 6.1.

**T-I8 / G (planned red).** "Write the real-repo parametrized test and see it fail locally on absence … Render and commit the figures … Pop the stash and commit the test as a green commit."

- **Addressed:** adopted, except that the test file is parked in the session scratchpad, not in
  `git stash`. The stash is shared with other sessions' worktrees.
- **Where:** tasks 9.2 ("move the file to the session scratchpad, not to the stash") and 9.7.

**T-I9 / G-I2.** "Record `renderer_sources: {comparison_figure.py, make_coarse_vs_fine_figures.py: sha256}` … Hash with newline normalisation … Any edit to the renderer then forces a re-render." Also: "Rule: any code change after a render re-renders all three figures."

- **Addressed:** adopted.
- **Where:** viz, Req "Committed comparison figures stay current with their inputs and renderer"
  ("`renderer_sources`: the sha256 of the LF-normalised bytes…"; "`renderer_sources` to equal the
  current files"); design D7 Re-render rule; tasks 11.3.

**T-I11.** "It needs a pure compute function, e.g. `compute_<figure>_metrics(coarse_dir, fine_dir) -> dict` … For an independent anchor … recompute the histogram counts in the test with `np.histogram` …"

- **Addressed:** adopted.
- **Where:** viz, Req "Committed comparison figures…" ("…equal the library's
  `compute_<figure>_metrics`…"; "independent anchors computed in the test itself (histogram counts
  via `numpy.histogram` …)"); design D7; tasks 4.2, 5.2, 6.2, 9.2.

**T-I12.** "Add: each of the 9 files passes `git ls-files --error-unmatch`; `tests/fixtures/comparison_figure/` does not exist; each PNG starts with `\x89PNG\r\n\x1a\n`."

- **Addressed:** adopted.
- **Where:** viz, MODIFIED Req "Generated video files…", Sc "each coarse-vs-fine figure has one
  committed real-data reference output"; tasks 9.2.

**M-I2.** "Specify: (a) if the recomputed R² is NaN, require the JSON `config_resolved` value and all five `runs` values to be `null`, else refuse; (b) skip the ε cross-check in that case; (c) refuse a partial null; (d) draw σ ≈ 0 or ε_s = 0 as 'n/a' or a marker."

- **Addressed:** adopted, all four parts.
- **Where:** viz, Req "The cycle-mean R² diagnostic…" ("A null R² SHALL be all-or-none per
  target … a partial null SHALL be refused"; "An `ε_s` of exactly 0 SHALL be drawn as a marker at
  the axis floor labelled `0`"); viz, MODIFIED Sc "a null config-mean R² passes through as null";
  design D4 Null.

**M-I3.** "Add: 'a target whose recorded skill is null is drawn n/a and not normalised (or the builder refuses, naming the target)', with a test."

- **Addressed:** the refusal option.
- **Where:** viz, Req "error-histogram…": "A target whose recorded skill is null SHALL be refused,
  naming the target"; tasks 5.1.

**M-I4.** "Require each panel to print 'seed 1234 skill X (5-seed range a–b)'. Add to 3.5: 'each panel's annotation includes the `seed_sweep.range.<c>.skill` min–max, and the sidecar records it verbatim.'"

- **Addressed:** adopted.
- **Where:** viz, Req "error-histogram…": "Each panel SHALL be annotated `seed <primary> skill <x>
  (5 seeds: <lo> to <hi>)`, read verbatim" and "the skill and its five-seed range"; tasks 5.1.

**M-I5.** "Replace it with the evidence that does support retiring the claim: 'on both corpora the five-seed `config_mean_r2` ranges overlap for every target (CF_x: coarse −6.70 to 0.65, fine −2.86 to 0.77) …'"

- **Addressed:** adopted, and the "0.005–0.03" range is corrected to the true means 0.007–0.029.
- **Where:** proposal.md, Background, third bullet ("Where the 'collapse' claim came from").

**M-I6.** "Add: 'a seed with R² = −73/35 … gives ε_s > σ …'; 'a fixture whose most negative seed has R² < −4 … renders without clipping …' Task 6.1's visual inspection should name coarse CF_x and fine CF_mz explicitly."

- **Addressed:** adopted.
- **Where:** viz, Sc "every seed is plotted…" (`−73/35`); Sc "boundary values of R²" (`−1e6`);
  tasks 6.1; tasks 9.4 ("coarse `CF_x` (−6.70) and fine `CF_mz` (−4.70) are inside the seeds-panel
  limits").

**M-I7.** "Specify `density = counts / (n_rows · bin_width)` with `n_rows` including out-of-range values, and print the out-of-range counts inside the axes."

- **Addressed:** adopted.
- **Where:** viz, Req "error-histogram…" (that formula, and "their counts printed in the axes when
  non-zero"); tasks 5.1; tasks 7.4 (`density=True` mutant).

**M (frames and labels).** "Add a task requiring: the labels or caption to say 'lab-frame components on the wing; moments about the hinge' … CF_x is never labelled 'chord' or 'drag', nor CF_z 'wing-normal'."

- **Addressed:** adopted. There is a fixed label table and a forbidden-word list.
- **Where:** viz, Req "Comparison-figure captions and labels…" (the labels; "No caption, note or
  label SHALL contain `chord`, `drag`, `normal`, `span`, `pitch` or `roll`"); design D1 Target
  labels.

**G-I1.** "One commit would hold everything from sections 2-4 … Split it per the plan below, keeping the old builders until the new ones exist so every commit is green." Also the 7.9 and 6.1 splits.

- **Addressed:** adopted, following the reviewer's commit plan.
- **Where:** tasks 0.3, 1.4, 2.3, 3.4, 4.3, 5.3, 6.3, 7.5, 9.1, 9.6, 9.7, 10.2, 10.4 and 10.7. The
  renders: all three are inspected and shown to the user before any is committed (tasks 9.4–9.6).

**G-I4.** "PR #171 (corpus regeneration) is a hard ordering dependency."

- **Addressed with a correction.** PR #171 is the roadmap docs PR (`docs-surrogate-comparison-plan`).
  It changes no input of these figures. The regeneration is a future change. The ordering concern
  holds for that future change, and is recorded where it will be seen.
- **Where:** design D7, Corpus regeneration ("That future change must retrain, then re-render these
  three figures. This is written in the fine README's 'Comparison figures' section"); design D9.

**G (lab meeting).** "If the branch is never pushed, the sidecar names a commit that exists only locally … Push the branch or open a draft PR before the meeting." And: "A `/review-pr` renderer fix after the slides are built makes the slide PNGs differ."

- **Addressed:** the push or draft-PR question goes to the user at the approval checkpoint, and the
  user is told which slides a re-render affects.
- **Where:** design D10, Lab meeting; tasks 11.3, 11.6.

**G (F3a).** "'Small and textual' is a hope, not a plan … F3a merges main into its branch, never rebases … Share this hunk list with the F3a session via the user."

- **Addressed:** adopted.
- **Where:** design D10 F3a, with the hunk list in D9; proposal Impact, Coordination.

**D-I4.** "One 3-line note in the new fine README 'Comparison figures' section … Also explain that `git.commit` is the parent of the figure's own commit."

- **Addressed:** adopted. Corrected wording: `git.commit` is the commit the figures were rendered
  from. That is the parent of the data commit, unless the test commit of tasks 9.6–9.7 intervenes.
- **Where:** design D9, Fine README.

**D-I5.** "The driver docstring holds the argument contract. The fine README holds ONE worked command … `project.md` keeps … 'see `examples/prelim_sweep_fine/README.md#comparison-figures`'. Do not append as step 4 of the fine README's existing `### Regenerating` block."

- **Addressed:** adopted.
- **Where:** design D9 (the fine README holds "the one regeneration recipe, a loop over the three
  names"; project.md gets a pointer); tasks 7.2.

**D-I6.** "Line ~404 says 'Four thin argparse CLI drivers…' … Make the sentence count-free … Lines 399-401 parenthetical … must change … Delete the items cleanly … replacing the two old blocks in place."

- **Addressed:** adopted.
- **Where:** design D9 `openspec/project.md`; tasks 10.4.

**D-I7.** "Lines 33-35 … That is history; leave it … Put the removal in 'Changed' with a one-line pointer, and the new figures/driver in 'Added' … keep this entry a single bullet."

- **Addressed:** adopted.
- **Where:** design D9 `docs/CHANGELOG.md`; design D10; tasks 10.7.

**D-I8.** "Reword that row to mention the subfolder."

- **Addressed:** adopted.
- **Where:** design D9 ("The `figures/` file-table row mentions `figures/coarse_vs_fine/`"); tasks
  10.3.

**D-I9.** "Say it once (coarse README …) and make the fine README a one-line 'same as the coarse corpus' pointer."

- **Addressed:** adopted.
- **Where:** design D8 (last sentence); tasks 10.2 and 10.3.

**D-I10.** "Task 0.2's `rg` scope omits `.claude/`, `README.md`, `openspec/specs/`."

- **Addressed:** the scope is widened and the expected historical hits are listed.
- **Where:** tasks 0.2.

**S-S4.** "Impact omits docs files."

- **Addressed:** a Docs line is added to Impact.
- **Where:** proposal.md, Impact.

**S (force-surrogate MODIFIED).** "Reword: 'The metadata SHALL record the seeds (top level) and, under `library_versions`, …' Also say what happens when a package is not installed."

- **Addressed:** adopted.
- **Where:** fs, MODIFIED Req "Training reproducibility and provenance" ("the seeds (at top level)
  and, under `library_versions` …"; "SHALL be `null` when the package is not installed"); its CI-tier
  Sc ("and `seeds` remains a top-level key").

## SUGGESTIONS

- **Adopted:**
  - S-S1 (±3 edge convention): viz, Sc "the counts follow the bin convention".
  - S-S2 (R² > 1, σ = 0): see T-B4 and M-I2.
  - S-S3 (null skill range drawn): viz, Sc "partially and fully null seeds".
  - S-S5 (split requirements): the sidecar requirement is split into inputs/guards,
    captions/labels, and committed in-sync.
  - S-S7 (commit points, no "etc."): see G-I1 and T-I6.
  - S-S8 (grammar): fixed in the MODIFIED Sc.
  - T-S1 (CI lint paths): tasks header.
  - T-S2 (warnings as errors): design D5, tasks 3.3.
  - T-S3 (exit code 2, every flag): viz driver Sc; tasks 7.1.
  - T-S4 (partial write): design D5 Writing; tasks 3.2.
  - T-S5 / M-S6 (`_BANNED` scope): design D6, viz caption and skill-range Reqs.
  - T-S6 (IB-free regex, the "above 1" phrase): fs ADDED Req.
  - T-S7 (rg hit list): tasks 0.2.
  - T-S8 (numpy cycle means): design D4; viz diagnostic Req.
  - M-S1 (finer bins): edges `linspace(-3, 3, 601)`. The closest real `z` to an edge was measured at
    7.5e-9, so exact counts stay sound.
  - M-S2 (rows not independent): caption phrase in the viz caption Req.
  - M-S4 (cross-corpus `val_configs`): viz skill-range Req and tasks 3.1.
  - M-S8 (QS attribution to the omitted terms): design D9.
  - D-12 (shared rule literal): viz caption Req ("module constants … SHALL appear verbatim in the
    fine README's 'Coarse vs fine' section"); tasks 10.3.
  - D-13 (`CF_c ≈ v` guard): tasks 10.3 keeps `R2_NEAR_TARGET` green.
- **Declined:**
  - S-S6 (rename the change id): the current id is valid and is already the branch name.
  - T-S9 (render-compare from a second clone): the render-twice `cmp` plus repo-relative paths
    already catch dependence on the output path.
  - M-S3 (per-seed pointwise RMSE in the scales panel): it adds a fourth scale with no new
    conclusion, and the evidence figures already report RMSE.
  - D-11 / D-F (the proposal, design and spec repeat each other): the proposal is trimmed. The
    design and spec keep their overlap, because the spec is the normative record at archive.
