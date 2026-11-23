# Design — surrogate comparison bench (F3a)

## Context

The decision to build a bench rather than pick a winner, and the split into F3a (this change), F3b
(field models) and F3c (DoMINO), is recorded in `docs/field_surrogate/roadmap.md`,
"Revision (2026-11-18)", added by PR #171, which merges before this change. The exploration branch
`explore-surrogate-experiments` (`b99c7b2`, local, unreviewed) is the **reference for expected
magnitudes, not code to copy**. This table is the one place in this change the exploration's numbers are stated:

| Exploration result | Value | Status here |
|---|---|---|
| MLP, shipped inputs, holdout skill (median of 5 seeds) | 0.9870 (0.9861–0.9914) | `mlp_h1` / `interpolation` must reproduce the shipped `metrics.json` exactly (D7) |
| MLP, 3 harmonics | 0.9950 (0.9929–0.9958) | Expected magnitude for `mlp_h3`; holdout-informed, so optimistic where holdouts are tested (D6) |
| Ridge, H 16, d 3, α 1e-6 | 0.99914 | Re-run as `ridge_fixed` on every split (D3) |
| Ridge, E4 18-config subset seed 0 | 0.4059 | Re-tested by `control:e4_seed0` (D2) |
| E1 worst-seed body-frame normal peak error | 3.18 % at `s45_f100_p60` vs GCI 3.7 % | Expected magnitude for the gate |

The exploration code had defects this design removes (from a read-only audit of the branch):

- a basis with columns the grid cannot identify;
- a normal-equations solve;
- a penalised intercept;
- row-weighted fitting (configurations with higher f* have more rows);
- a CV grid widened after holdout scores were seen: E4 scored `H ∈ {2,4,8}` on the holdout in
  `fd33c0e` before `eaa567c` widened the grid;
- a beat yardstick computed over a different phase window from the error it was compared with;
- a margin taken from the median seed while the verdict used the worst.

## Decisions

### D0 — Two PRs, one OpenSpec change

- **PR 1 (code)**, branch `add-surrogate-comparison-bench`, contains:
  - the proposal;
  - the `force-surrogate` seams;
  - the bench package and the driver;
  - the CPU and GPU-tier tests;
  - the spec reconciliation.

  It writes no artifact into the repository.
  - The branch is rebased on `origin/main` before any code is written, while only the proposal
    exists. It is rebased again once PR #171 has merged, which must happen before PR 1 opens; the
    full suite and the shipped-artifact check are then re-run.
  - `proposal.md` and `tasks.md` carry a banner: "PR 1 of 2 — archive only after PR 2 merges".
  After it merges, `/cleanup-merged` deletes the branch
  but **does not archive the change**. The PR 1 description and the session handoff memory both say
  so.
- **PR 2 (results)**, branch `add-surrogate-comparison-bench-results`:
  - `git fetch`, then create the branch from `origin/main` after PR 1 merges. Record that commit,
    `M`, in the PR body.
  - Run the bench and the two h3 trainings **before any commit on that branch**, from the clean tree
    at `M`, into scratch directories outside the repository. The recorded commit is therefore on
    `main` and stays reachable after PR 2 is squash-merged. The branch name is not `main`, as the
    existing clean-commit test requires.
  - Between the runs: no fetch, pull or rebase. The twice-run gate asserts that both runs record `M`.
  - Copy the outputs in, then add the committed-artifact tests, the README section, the roadmap rows
    and the changelog.
  - Before merging,
    `git diff M origin/main -- src/ scripts/ pyproject.toml uv.lock examples/prelim_sweep_fine/dataset.parquet`
    must be empty; if it is not, the user decides between a re-run and acceptance, and the decision
    is recorded.
  - A code fix found during PR 2 goes to `main` through its own PR. PR 2's artifacts are then
    discarded, the branch is recreated from the new `main`, and the runs are repeated. Fixes to tests
    or docs only need no re-run.
- PR 2 touches only the task boxes of its own groups and adds its own reconciliation addendum. The
  change is archived after PR 2 merges, in a separate `chore(openspec): archive` commit.

### D1 — Reuse the trainer through small public seams, change nothing at the default

The bench must train exactly the shipped recipe, so it does not re-implement training.

- `build_features(df, phase_harmonics=1)`: the `h = 1` columns keep the literal expression
  `np.sin(2.0 * np.pi * phase)`; higher harmonics are `np.sin(2.0 * np.pi * h * phase)` appended
  after them. A frozen copy of today's construction is kept in the tests and compared bitwise.
- `_fit_one_seed` gains keyword arguments `split: SplitAssignment | None = None` and
  `phase_harmonics: int = 1`.
  - With `split=None` it calls `make_config_splits` exactly as today.
  - `run_training` passes `phase_harmonics` explicitly, also at the default.
- The public wrapper `fit_seed(df, split, *, seed, phase_harmonics, ...)` validates the split, then
  calls `_fit_one_seed`.
- `_fit_one_seed` reaches torch only through `build_model`, `train_model` and `predict`. CPU tests
  replace those three with recorders and run the real carve, feature and standardiser code. That is
  how PR 1 proves the bench's interpolation fit receives the same arrays as `run_training`'s (the
  spec's seam scenario); a short GPU test then confirms identical predictions after an unrelated fit
  in the same process.
- `predict_frame(fit, frame)` builds features for arbitrary rows with the fit's own harmonic count
  (from `feature_names`) and standardisers, so the bench can evaluate a model on the 256-phase grid.
  Skill is scored on the fit's own test predictions, not `predict_frame`'s, as `run_training` does.
- `run_training(..., phase_harmonics=1)` validates the value before any I/O; `--phase-harmonics` on
  `scripts/train_surrogate.py`. `metrics.json` and `run_metadata.json` already record `features`; no
  new key is added, so the default files are unchanged.
- `build_phase_only_baseline(..., reference_configs=None)`.
- The new names are exported from `mosquito_cfd.force_surrogate`.

### D2 — Splits are derived from data, and the interpolation carve is the shipped carve

Faces come from the configurations' kinematic columns after a guard that every setting has exactly 3
distinct values. The validation carve for an arbitrary training list reuses `make_config_splits`'s
algorithm through a shared private helper, extracted in its own refactor commit.

Controls draw 18 of the 21 `pool` configurations; the six labelled holdouts are their test set, so a
control differs from `interpolation` only in having 3 fewer training configurations. A control and
a face still differ in their test sets: the six holdouts against the nine face configurations. Test
difficulty is therefore a confounder. The baseline-relative RMS only partly corrects for it. The
like-for-like view compares a face model and the controls on the same configurations: the 1–3
holdouts each face contains (none for pitch 30). The face-without-holdouts metric serves a different
purpose, removing holdout-informed optimism, and widens the test-set difference. With the capped basis the six controls are full rank, so none reproduces
E4's collapse. `control:e4_seed0` adds E4's own subset, which is rank deficient.

The construction was confirmed against `experiments/common/splits.py` and
`e4_ablations/ridge_cv.py` on the exploration branch. The ranks are pinned in the spec.

Each face split keeps 18 training configurations; after the 3-configuration validation carve the MLP
fits on 15. That is the honest cost of extrapolation at this corpus size, and the controls are carved
the same way.

### D3 — The ridge reference, defined so the grid can identify it

**Why two stages.** Every configuration is one point $z_c$ in settings space. However many phase
samples it has, it pins the settings dependence at one point only. Writing the target as

$$
C(z, \varphi) \approx \sum_{k=0}^{2H} \Big(\sum_{j} \beta_{jk}\, m_j(z)\Big)\, g_k(\varphi),
$$

with $g_0 = 1$, $g_{2h-1} = \cos 2\pi h\varphi$, $g_{2h} = \sin 2\pi h\varphi$, the bench first
computes each configuration's Fourier coefficients $a_{c,k}$ from its beat resampled onto
$N = 256$ uniform phases (exact orthogonal projection on that grid for $H \le 32 < N/2$), then fits,
for each $k$ and target, a ridge regression of $a_{c,k}$ on the monomials $m(z_c)$:

$$
\min_{\beta}\; \sum_{c} \big(a_{c,k} - m(z_c)^{\mathsf T}\beta\big)^2 + \lambda \sum_{j \ge 1} \beta_j^2,
\qquad \lambda = \alpha\, n_{\text{train configs}} .
$$

This has three effects:

- **Equal weight.** Each configuration counts once; the exploration weighted by row count.
- **Cheap cross-validation.** Leave-one-configuration-out CV costs one multi-right-hand-side solve
  per split, fold, $d$ and $\alpha$. All $H$ and targets share it, because the coefficient columns
  for a smaller $H$ are a subset. An independent prototype ran all 14 splits in about 6 s.
- **Identifiability in one place.** The question lands in an $n_{\text{configs}} \times P$ matrix,
  where it can be measured.

**Identifiability cap.** With $L_v$ distinct values of setting $v$ in training, every polynomial in
$z_v$ of degree $\ge L_v$ equals one of degree $L_v - 1$ on those values (for three values
$z^3 = e_1 z^2 - e_2 z + e_3$). The basis therefore keeps only monomials with each exponent
$\le L_v - 1$. On a face split the held-out setting has $L_v = 2$, so the model is at most linear in
it. This is a limitation the bench reports, not a defect.

**Ranks.** With the cap, the full training matrices of `interpolation`, the controls and the faces
are full rank. The deficits are in the CV folds and in E4's subset.

When a matrix is rank deficient, a coefficient direction is invisible to its training configurations
but not necessarily at a test configuration. The prediction there is set by $\lambda$, not by data.
The bench records ranks per split and $d$, with the singular-value gap, so a poor score can be traced
to it.

**Solve.** `numpy.linalg.lstsq` on the augmented system
$\begin{bmatrix} M \\ \sqrt{\lambda}\, D \end{bmatrix}\beta = \begin{bmatrix} a \\ 0 \end{bmatrix}$,
with $D$ the identity with its intercept row removed (unpenalised intercept). This avoids squaring the
condition number as the normal equations do.

**Selection: the one-standard-error rule.** The grid is fixed before any bench result exists and
extends past the exploration's chosen $H = 16$. An independent reimplementation of the CV on the
corpus's training configurations, made during design review (`review-reconciliation.md`, round 2, M2), found:

- the score falls with $H$ and then plateaus from about $H = 12$;
- a plain argmin, and also a 1 % relative band, lands on $H = 32$ (the grid edge) on all six faces,
  because the scores are about $10^{-5}$ to $5 \times 10^{-4}$;
- $H = 8$ is within about 10 % of the best everywhere.

A tolerance must therefore come from the data's own scatter. The rule takes the simplest candidate
within one standard error, across the leave-one-out folds, of the best. The rule is standard, has no
hand-picked constant, and was fixed with the user before any bench result exists.

The same reimplementation, applied to this rule (`review-reconciliation.md`, round 3), found:

- θ* is at `H = 32` on every split;
- the rule chooses `H = 8, d = 2` on `interpolation`, E4's subset and the controls;
- it chooses `H` 16–24, `d = 3` (the `d` edge) on the faces;
- the smallest `selection_margin` is 8.7e-3.

The `H`-first tie-break takes the simpler `d = 2` where it is within one standard error. A `ridge`
row below `ridge_fixed` on the pool-trained splits is that choice, not a defect.

These are design-review prototype outputs on training configurations, not bench results. The
one-standard-error rule was motivated by the CV score scale. It was adopted after design review had
also seen holdout skills of ridge variants, however, so `ridge` is marked weakly holdout-informed.

Where the choice lands, including on an edge, is recorded, not assumed. `selection_margin` records
how close any candidate came to the threshold. A split with `selection_fragile` is refit at its
committed choice rather than re-selected in the consistency test, because a different BLAS could flip
a near-tie.

**`ridge_fixed`.** A design-review reimplementation (`review-reconciliation.md`, round 2 M4, confirmed in round 3)
found two things. At the exploration's fixed point $(16, 3, 10^{-6})$ the corrected ridge still
collapses on E4's subset, with a grid-approximated holdout skill of about 0.75. Re-selection picks
$d = 2$ and scores about 0.997. Without a fixed-point entry the bench would report "no collapse" and
credit it to the corrected construction. `ridge_fixed` runs at that point on every split so the two
causes can be told apart.

The point was chosen by CV on the 21 pool configurations, but on a grid widened after holdout scores
had been seen, so it is holdout-informed (see D6). `H = 16` was the edge of that grid, which is
consistent with `θ*` landing at the `H = 32` edge here.

### D4 — Metrics and normalisation

Skill is the existing #127 definition (`compute_baseline_skill`), with the baseline built from the
split's own training configurations. For `interpolation` the explicit list is `pool`, and the
baseline curves are bitwise the shipped one's.

Skill is **not comparable across splits**. The phase-only baseline's RMS is about 0.11 of the
component peak for `interpolation` and about 0.20 on the pitch faces, so the same model error gives a
different skill. Cross-split comparisons use `rmse_frac_component_peak` with the baseline's value
beside it.

Errors are fractions, named `_frac_` so nobody multiplies them by 100. Grid errors are computed on the
256-phase grid. The models are evaluated directly at the grid phases; the CFD beat is periodically
interpolated.

The component normaliser `peak_t` is one number per target, the corpus-wide grid peak, used on both
sides of every lab-frame comparison. It includes the test configurations. It is a fixed reporting
constant shared by every split and every model, and it never feeds fitting or selection, so it is not
leakage.

`results.parquet` stores the sums needed to recompute every pooled value. Its size is 12 fits
(5 + 5 MLP seeds, `ridge`, `ridge_fixed`) × 6 targets × 102 (split, test configuration) pairs
(6 interpolation + 6 faces × 9 + 7 controls × 6) = 7,344 rows.

**Target beat** (defined in the spec). Every entry and the baseline use the last beat common to every
configuration. On the 2-beat corpus that is exactly `filter_converged_beat`'s output, so the MLP's
training frame is the shipped one.

On a longer corpus, training on several beats would put repeated phases into one configuration,
which the ridge rejects. Using only the last beat throws away beats the MLP could use, and that last
beat carries the f* = 0.85 anomaly (#173); beat `N − 2` would avoid both. Which beats a regenerated
corpus should train on is therefore a decision for that rerun, together with retraining the shipped
surrogate (the exact `mlp_h1` regression is valid only on the 2-beat corpus). The shipped trainer is
not changed here.

### D5 — The hover gate is provisional by construction

Per the roadmap, the uncertainty must be measured, not assumed; today it cannot be measured on this
corpus. So the gate reports each stand-in yardstick separately, labelled with its source, carries
`provisional: true` with reasons, emits no overall verdict, and never reports a component without a
yardstick as passing.

- **Body-frame peaks on the grid.** The last row of every f* = 0.85 configuration jumps (#173), and
  raw-row peaks pick it up. Grid peaks remove most of it: a residual of up to 0.3 % stays, because
  the wrap interpolation still touches that row.
- **The beat is not periodic.** In every configuration the first row of the converged beat and its
  last regular row differ by 2–7 % of that configuration's lab component peak (1–4 % of `peak_t`),
  and by 1–5 % of the body-frame normal peak. The defect survives slope correction (1.2–5.0 %).
  - The normal peak lies within 0.06 of phase from the splice, and at it in 4 of 27 configurations,
    because each beat starts mid-stroke.
  - A periodic model (sin/cos MLP, Fourier ridge) cannot represent the jump, so its error has a
    floor near there of the yardsticks' size.
  - The bench records the raw and slope-corrected jumps, with the wrap gap in row spacings (it is
    2.1 spacings at f* = 1.15), and lists the jump as a provisional reason.
  - Longer runs in the regenerated corpus are expected to shrink it; the bench will show whether
    they do.
- **Rotation.** `CF_x..CF_z` are rotated with the existing `euler_angles`, `rotation_matrix` and
  `body_frame_coefficients`, as on `main` after #168. `f_ref = 1` because the inputs are already
  coefficients.
  - The known answers are written by hand, so the test does not compare the code with itself.
  - The phase 0.125 cases pin the stroke angle and phase→time; at phases 0 and 0.25 the stroke
    drops out.
  - The x̂ case is even in φ, so the ŷ case and `cf_span` are what pin the stroke sign.
  - The 0.125 values were checked against the code before being written into the spec.
- **`grid_gci` reasons.** Every reason in the spec was checked against `inputs.3d.convergence_fine`
  and the corpus decks.
- **`coarse_vs_fine`** is the coarse-fine difference. Under the asymptotic Richardson model,
  $E_c = r^p E_f$, so the difference is $E_c - E_f = (r^p - 1) E_f \approx 5.8\,E_f$: a
  conservative upper bound on the fine grid's error, and about $0.85\,E_c$, an under-estimate of
  the coarse grid's. (The proposal first said it bounds the coarse grid's error; the pre-PR
  review corrected the direction.) The Richardson estimate of the fine grid's error, $1/(r^p - 1)$
  of it, is reported as `coarse_vs_fine_scaled` with its limits in its label.
- **`late_beat`** is implemented now, tested on synthetic 2-, 3- and 4-beat frames, and switches on
  when the regenerated corpus has at least 4 beats. The quadrature combination
  $\sqrt{Y_{\text{grid}}^2 + Y_{\text{late}}^2}$ assumes the grid and settling errors are
  independent; the linear sum is recorded beside it.

### D6 — Committed artifacts and the shipped model

The shipped `surrogate/` and `figures/` are not retrained. `surrogate_h3/` and `figures_h3/` are
produced by the existing scripts with `--phase-harmonics 3` and new `--out-dir` values, after the
twice-run gate. The figure generator needs no change: it already takes `--out-dir` and does not depend
on the feature count.

The holdout status of every entry (`holdout_informed` and its reason) is defined in the spec: `mlp_h3`,
`ridge_fixed` and, weakly, `ridge` are holdout-informed; `mlp_h1` is unverified. Holdout-informed
entries are optimistic wherever a split's test set contains labelled holdouts, which is
`interpolation`, the controls and 5 of the 6 faces. The summary therefore reports face metrics
without those configurations, and a like-for-like view of the face models and the controls on them.

A change-lifetime check, not a committed test, keeps the shipped artifacts unchanged. The paths are
the fine `surrogate/`, `figures/` and `dataset.parquet`, and the whole coarse `examples/prelim_sweep/`.
At the end of every task group:

- `git diff --exit-code <base> -- <paths>` is empty (working tree against `<base>`, so it holds
  before the commit);
- `git status --porcelain -- <paths>` is empty.

`<base>` is `git merge-base origin/main HEAD` for PR 1, and `M` for PR 2. A legitimate change on
`main` (#114 may touch `figures/`) therefore does not trip it, even after a rebase. Line-ending
normalisation is checked by one dry run on a clean tree before task 1a. A standing test
would break on purpose at the planned corpus regeneration and #114.

### D7 — Bench results are committed, small and recomputable

A CPU test recomputes the committed results:

- every summary number from `results.parquet`;
- the splits;
- the ridge rows from the dataset.

Two tolerances apply, for different checks:

- **Summaries recomputed from `results.parquet`:** `1e-12`. These are the same arithmetic on stored
  numbers.
- **Ridge refits from the dataset:** `rtol = 1e-8` on scores, sums, metrics and the retained singular
  value, plus `atol = 1e-9` on differences of nearly equal scores. Design-review perturbation tests
  put BLAS-level differences between 2e-11 and 6.4e-10 (`review-reconciliation.md`, rounds 2 and 3).

A dropped singular value is round-off: it moved across 1.8 decades under mere row reordering. So it
is only checked against the rank tolerance, never by value.

Before PR 2 opens, the recompute test runs twice against the scratch outputs:

- natively on Windows, where the CPU suite runs;
- under WSL2, where the outputs were produced.

The maximum relative differences go in the PR body. A value above `1e-8`, or a failure of this test
in PR 2's CI (the GitHub runner's BLAS), halts for a decision; the tolerance is not loosened. Bitwise
claims are made only within one process.

The `mlp_h1` / `interpolation` per-seed skills must equal the shipped `metrics.json` exactly, because
they come from the same `compute_baseline_skill` call on the same predictions. That holds only under
three preconditions:

- the run is on the host recorded in the shipped `surrogate/run_metadata.json` (talmo-lab-02, under
  WSL2);
- the driver, `torch` and `physicsnemo` match the shipped run;
- `mlp_h1` / `interpolation` is fitted first in the process.

The test compares the two committed `run_metadata.json` files, so a bench recorded on any other host
(for example the native-Linux gh-04 box) fails these preconditions by design; task 9.1 checks the host
before the run. The shipped
record has no numpy version or `CUBLAS_WORKSPACE_CONFIG`, so those cannot be asserted; the bench
records both for next time. MLP rows are not otherwise recomputed in CI.

## Risks

- **`mlp_h1` interpolation does not reproduce the shipped skill.** PR 1's seam tests make a seam
  change unlikely. If the check fails anyway, a precondition probably changed. Halt and diagnose; do
  not loosen the check.
- **Ridge at a grid edge.** Recorded with `at_grid_edge = true`. Widening the grid after seeing
  holdout scores is not allowed in this change (that was the exploration's mistake).
- **2-beat data.** Every number is labelled as from the 2-beat corpus and will be recomputed after
  regeneration.
- **GPU contention.** The MLP fits run on the local A5000. The GPU is checked idle before each run;
  timing fields are informational, not gated.
