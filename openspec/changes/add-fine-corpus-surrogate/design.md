# Design

## Context

- The trainer is corpus-neutral: `scripts/train_surrogate.py` takes `--dataset`/`--out-dir`
  (required); `examples/prelim_sweep` appears in `train.py` only in docstrings. The fine dataset
  has the coarse schema, the same 27 kinematic configs, the same 21/6 split, wingbeats 0–1, and the
  same `dt`, so converged-beat (`wingbeat >= CONVERGED_MIN_WINGBEAT = 1`) holdout configs have the
  same 1738/2000/2353 rows per beat. The phase-only baseline (`train.build_phase_only_baseline`)
  handles several converged beats per config;
  here there is exactly one (archived #127 design D2).
- The evidence figure is **not** corpus-neutral. `evidence_figure.py` hard-codes the coarse grid in
  five places:
  - `CFD_SECONDS_PER_WINGBEAT = 144.0` is the speedup denominator;
  - the caption headline says "sequential coarse-grid A40 CFD";
  - the caveat reads "Coarse 64x32x64 grid: pipeline readiness, not validated aerodynamics.";
  - the quasi-steady line and the sidecar `note` say "the coarse-grid CFD lift" (and "at this
    resolution");
  - `_README_POINTER = "examples/prelim_sweep/README.md"`.
- **Where 144 s comes from.** It is 2.4 min × 60: the roadmap's Hardware row rounds the wall time
  of one A40 run of the 70° validation deck `inputs.3d.validation`. `examples/flapping_wing/RESULTS.md`
  "Performance" records that run (its "second run (February 27)") as 146 s for one wingbeat (2000
  steps). That deck writes plotfiles every 100 steps (`amr.plot_int = 100`). It is not a sweep
  configuration, and it is a single sample.
- **What the fine CFD wall time is.** Each of the 27 `run_metadata_<config>.json` files has
  `timing.wall_time_s`, `timing.timesteps` and `gpu_model == "NVIDIA A40"`. Per step it is
  2.097–3.302 s, median 2.1440 s. Per wingbeat it scales with 1/f* (a wingbeat is `1/(f*·dt)`
  steps): medians 4996 / 4297 / 3739 s at f* = 0.85 / 1.0 / 1.15. The median step rate
  (≈2.14 s/step) is about 7% above the force-only fine pilot's 2.010 s/step
  (`docs/force_surrogate/fine-grid-pilot-report.md`; pilot `plot_int = -1`, pre-hinge-fix geometry).
  The ~2× spread is node variation, not kinematics.
- **What "grid-checked" means.** T3c (PR #52) ran the 3-grid convergence study at the 70° validation
  stroke, outside the sweep's φ ∈ {35, 45, 55}°, at `dt = 2.5e-4` on the A5000, on peak body-frame
  `CF_normal` (GCI_fine "3.7 %") and `CF_chord` (GCI_fine "27.6 %"; the source writes a space before
  `%`, and the README quotes these strings verbatim). No moment and no lab-frame time series was
  grid-checked. T4: `CF_chord` 0.41 vs the van Veen QS model 0.43, `CF_normal` 2.23 vs 2.48 (~11%).
  The source is `examples/flapping_wing/RESULTS.md`.
- The committed coarse sidecar has no git, timestamp or path fields. A reviewer regenerated it and
  the PNG from the committed inputs on the Windows host: both were byte-identical. The figure's
  `run_metadata.json` legitimately changes between regenerations.
- The scope guard permits exactly two file inputs (predictions + metrics.json). A scalar CLI argument
  is not a file input.
- `get_git_info` sets `dirty` from `git diff HEAD` (`benchmarks/metadata.py:96`), so it ignores
  untracked files; a clean tree must be checked with `git status --porcelain` separately.
- At a fixed seed the A5000 has reproduced coarse training bitwise (#126; archived #127 D5). The live
  spec still claims bitwise reproducibility only for the CPU path (`reproducibility.bitwise ==
  "cpu_only"`); this change does not alter that claim.

## Decisions

### D1. Train with the existing trainer and the coarse run's flags

```
uv run --frozen --group train python scripts/train_surrogate.py \
  --dataset examples/prelim_sweep_fine/dataset.parquet --out-dir <scratch> \
  --docker-digest <examples/prelim_sweep_fine/run_metadata.json docker_image> \
  --timestamp <utc> --seed 1234 --sweep-seeds 1235 1236 1237 1238 \
  --epochs 2000 --n-val-configs 3 --device cuda --wandb disabled
```

There are no functional trainer changes. The digest is the image that produced the data, as for the
coarse surrogate; training runs in the WSL uv environment, not in that container (the README says
so). Whether 2000 epochs converge on the fine data is not studied (out of scope).

### D2. `GridProfile`: the coarse default is byte-identical

```python
@dataclass(frozen=True)
class GridProfile:
    name: str                 # "coarse" | "fine"
    cfd_label: str            # text after "sequential " in the headline
    lift_label: str           # "coarse-grid CFD lift" / "fine-grid CFD lift"
    qs_suffix: str            # " at this resolution" / ""
    grid_caveat: str
    readme_pointer: str
    cfd_seconds_per_wingbeat: float | None   # 144.0 (fixed) / None (derived from a per-step cost)

GRID_PROFILES = {"coarse": COARSE_PROFILE, "fine": FINE_PROFILE}
```

| field | coarse (current text, unchanged) | fine |
|---|---|---|
| `cfd_label` | `coarse-grid A40 CFD` | `fine-grid A40 CFD at its median per-step wall time` |
| `lift_label` | `coarse-grid CFD lift` | `fine-grid CFD lift` |
| `qs_suffix` | ` at this resolution` | (empty: on the fine grid the reason is the omitted terms) |
| `grid_caveat` | `Coarse 64x32x64 grid: pipeline readiness, not validated aerodynamics.` | `Fine 256x128x256 grid: agreement with CFD, not with experiment; grid convergence checked only at one wing motion outside this sweep (README).` |
| `readme_pointer` | `examples/prelim_sweep/README.md` | `examples/prelim_sweep_fine/README.md` |
| CFD cost | `144.0` s per wingbeat (`CFD_SECONDS_PER_WINGBEAT`, name kept) | a supplied cost per step |

- `build_caption`, `build_figure`, `_baseline_reference` and `generate_evidence_figure` take
  keyword-only `grid: str = "coarse"`, resolved through `GRID_PROFILES`; an unknown name raises
  `ValueError` listing the valid names. `compute_speedup` takes keyword-only
  `cfd_seconds_per_wingbeat: float = CFD_SECONDS_PER_WINGBEAT`.
- `generate_evidence_figure(..., grid=..., cfd_seconds_per_step=None)` and `build_figure` validate
  everything before writing (`resolve_grid`):
  - `fine` with `None` raises `ValueError`;
  - a non-finite or ≤0 per-step cost raises;
  - `coarse` given any per-step cost raises: its cost is fixed at 144 s per wingbeat.
- For the fine profile, `cfd_seconds_per_wingbeat(profile, s, rows)` = `s × rows` of the
  representative configuration, so the speedup's per-row CFD cost is exactly `s`.
- `build_caption` rejects a speedup whose per-wingbeat cost does not fit its profile: the coarse
  label over anything but 144 s, or the fine label over 144 s.
- The figure's `run_metadata.json` always records `grid`, `cfd_seconds_per_step` (`null` for
  coarse) and `cfd_seconds_per_wingbeat` from now on.
  The committed coarse record predates them; the spec says a record without them reads as
  `coarse` / 144 s. The coarse figure is **not** regenerated (D2 gate). The sidecar key set is
  unchanged; `speedup.cfd_seconds_per_wingbeat` already records the value.
- The ">1,000x faster than CFD" headline holds on both grids. The latency-floor clause is printed for
  both in the same form.
- CLI: `scripts/make_evidence_figure.py --grid {coarse,fine}` (default `coarse`) and
  `--cfd-seconds-per-step FLOAT`, passed through.

**Coarse no-op gate.** It is pre-registered: a CI half plus a manual PNG half.

- **CI half (permanent):** `test_committed_sidecar_regenerates_from_committed_inputs[coarse]` calls
  `generate_evidence_figure` with the default grid on the committed coarse predictions and metrics
  into `tmp_path`, and compares the sidecar with the committed one: parsed JSON, exact for copied
  values, `approx(rel=1e-12)` for the two computed quasi-steady RMS values, so a last-ulp numpy
  difference on Linux cannot fail CI.
- **Manual half (PNG bytes):** run once, on the Windows host where the committed figure was made.
  - **(a)** `main`'s code (`dada8f0`) in a temporary detached worktree in the scratchpad, run from
    that worktree's root with its own `.venv`: `uv run --frozen --group viz`.
  - **(b)** this branch's code at C2, run the same way from the branch worktree.
  - Preconditions, recorded:
    - in each run, `mosquito_cfd.force_surrogate.evidence_figure.__file__` lies inside that run's
      own worktree;
    - `hasattr(ef, "GRID_PROFILES")` is False for (a) and True for (b);
    - `uv pip freeze --exclude-editable` is identical between the two envs;
    - `matplotlib.__version__` is recorded.
  - **Hard gate:** (a) and (b) produce byte-identical PNG and sidecar, and (a) equals the committed
    coarse PNG and sidecar.
  - Any precondition or comparison failure halts for a decision with the user.

### D3. Fine CFD cost: median per-step wall time, passed as a scalar

`mosquito_cfd.force_surrogate.cfd_cost.median_cfd_seconds_per_step(paths) -> dict` (torch-free)
returns `{"seconds_per_step", "n_configs", "gpu_model", "min", "max"}`:

- per file: `timing.wall_time_s / timing.timesteps`;
- `ValueError`, naming the file (`path.name`), on:
  - no paths;
  - a missing `config` or `gpu_model`;
  - a `wall_time_s` that is missing, `None`, `bool`, a string, non-finite or ≤0;
  - a `timesteps` that is not a positive integer (`bool` and fractional values rejected);
  - a duplicate `config`;
  - more than one distinct `gpu_model`;
- `statistics.median` (for an even count, the mean of the middle two).

`scripts/cfd_seconds_per_step.py --metadata-dir <dir>` globs `run_metadata_*.json` (the
corpus-level `run_metadata.json` does not match) and prints `repr(seconds)` on stdout (summary on
stderr). `float(repr(x)) == x` for every float, so the value passes through the CLI exactly.

**Why per step.** The speedup divides by the CFD cost per row, and each dataset row is one CFD
timestep. Per-wingbeat time scales with 1/f* (a wingbeat is `1/(f*·dt)` steps), so a median over
per-wingbeat times pools three f* levels; it happened to land on an f*=1.0 config (4375 s), which
matched the representative config only by chance. The per-step rate does not depend on the
kinematics (the pilot's was near-constant), so it is the quantity to take the median of. Found by
the pre-GPU code review; the user chose per step at the pre-GPU checkpoint.

**Why the median.** The ~1.6× spread in per-step time (2.10–3.30 s) is node variation. The median
is robust to the slow-node tail; a mean or the max would inflate the speedup.

**Disclosure (README, not caption).** The two denominators are **not like-for-like**:

| | coarse | fine |
|---|---|---|
| source | one A40 run of the 70° validation deck | the sweep's own 27 A40 runs |
| statistic | single sample | median |
| includes | plotfile output, start-up | plotfile output, start-up |

The force-only pilot rate is cited as the comparison point, with no ratio printed. The README states
the source of each number. The ~30× and ~7% figures stay in this design only: they are unguarded
derived ratios and must not appear in the README.

### D4. Reproducibility gate for the fine run (replaces #127's D5)

There is no prior fine artifact to byte-match. The gate is pre-registered:

- Before each run, in WSL:
  - `git --git-dir=<…> status --porcelain` is empty;
  - HEAD is the training commit (planned as C3; in the event `5f5db6e`, after the pre-GPU review
    commits `58ee8fb` and `5f5db6e`);
  - `test ! -e .venv/bin` (no Linux venv inside the Windows worktree);
  - `UV_PROJECT_ENVIRONMENT` is set **inside every** `wsl -e bash -c` command or copied script.
- Run the full 5-seed training (D1) **twice**, into `$HOME/mosquito-cfd-110/run{1,2}/surrogate`
  (ext4), with the same timestamp.
- **(a)** `surrogate.pt` and `holdout_predictions.parquet` are byte-identical (`cmp`).
- **(b)** `metrics.json` is equal as parsed JSON after removing the wall-clock fields of
  `inference` (`latency_ms`, `throughput_rows_per_s`); `inference.basis` is compared.
  `run_metadata.json` is equal after removing `run_id`.
- **(c)** Both records have `git.commit ==` the training commit, `dirty is False`, and
  `branch == "add-fine-corpus-surrogate"`.
- Any failure **halts** for a decision with the user, and nothing is loosened. Run 1 is committed.
- The outcome goes in tasks.md, the CHANGELOG and the PR body, worded as an observed outcome, not a
  bitwise claim.

### D5. Fine README

These sections follow the existing "What's here" table, which gains the new files. There is no
separate `figures/README.md`, because that table covers the figure files.

1. **"What the figure reports: skill over the phase-only baseline."**
   - A one-line local definition ("skill = 1 − MSE/MSE₀; MSE₀ = error of the phase-only baseline"),
     linking `../prelim_sweep/README.md#honest-reading-of-the-figure-cc-4` for the derivation.
   - The skill table, with the coarse header and row shape (`_SKILL_ROW`/`_SKILL_HEADER`).
   - The n=5 caveat and the waveform-credit caveat.
   - The CF_mx/CF_mz panel exclusion, with their skill given only in the table.
2. **"Config-resolved (cycle-mean) R², 5 seeds."**
   - Header `| target | cycle-mean R², 5 seeds |`, row `` | `CF_x` | lo to hi | `` (2 dp).
   - A pointer to the coarse README for why it is off the figure.
3. **"Coarse vs fine."**
   - Header `| target | skill, 5 seeds, coarse | skill, 5 seeds, fine | ranges overlap |`, row
     `` | `CF_x` | lo to hi | lo to hi | yes | ``.
   - Overlap is computed on the raw values; touching counts as overlap; `n/a` if either range is
     `null`.
   - Prose rule (spec): an overlapping target is described only as "no shift detected"; a disjoint
     one only as "`CF_c` … higher/lower on fine across 5 seeds".
   - One sentence: each grid is scored against its own corpus's phase-only baseline, so a difference
     reflects the data as well as the surrogate. No attribution to resolution alone.
4. **"Quasi-steady reference."** A short local paragraph, not only a pointer, because the spec's
   disclosure scenario applies to each corpus's README. It covers:
   - the fine-grid RMS ratio (the sidecar's `overshoot_factor`, at the caption's precision);
   - the model's nature: uncalibrated, translational-only, omits rotational/added-mass/LEV lift,
     symmetric-rotation AoA, stroke-plane-normal lift vs the lab-z CFD component;
   - that it is not overlaid on the figure;
   - a pointer to the coarse README for the full description.

   The coarse README's own QS paragraph is left as it is (coarse README out of scope; noted in the
   follow-up issue).
5. **"Validation status of the fine CFD."** Per Context:
   - convergence was checked only at the 70° validation stroke, at `dt = 2.5e-4` on an A5000, on
     peak body-frame forces;
   - GCI_fine "3.7 %" `CF_normal`, "27.6 %" `CF_chord` (verbatim as in the source);
   - QS-model comparison per component;
   - no moment checked, no measured forces;
   - the 27 sweep configs passed only the acceptance gate's internal checks;
   - all of it cited to `examples/flapping_wing/RESULTS.md`.
6. **"Speedup."**
   - Batched throughput vs sequential fine-grid A40 CFD, the batch size and the latency floor.
   - D3's like-for-like disclosure. The fine cost is stated as "x.xx s per step" (the sidecar's
     `cfd_seconds_per_wingbeat / rows_per_wingbeat`, 2 dp, guarded), and no coarse/fine ratio is
     stated.
   - The digest names the data-producing image (D1).
7. **"Regenerating."** The D1 command, the cost script, the figure command.

Prose rules:
- Moments are lab-frame components about the hinge, never "pitch"/"roll" moment; the wing-frame
  conversion is "deferred, not currently tracked".
- n=5 wording only.
- No `CF_c ≈v`/`= v` prose.
- No species wording added (#79).

Number sources:
- **Fixed literature/validation numbers** (GCI, T4 values, the pilot rate): each quoted string is
  checked by a test to appear verbatim in its cited source file (`RESULTS.md`, the pilot report).
- **Run-derived numbers:** recomputed from the committed JSON.

### D6. Committed-artifact guards over both corpora

`CORPORA = {"coarse": REPO/"examples"/"prelim_sweep", "fine": REPO/"examples"/"prelim_sweep_fine"}`
is built from literals. ids are literals too, and nothing reads a file at collection time.

**Testable helpers.** Each README/table guard is a pure function, e.g.
`check_comparison_table(readme_text, coarse_metrics, fine_metrics)` or
`check_cycle_mean_table(readme_text, metrics)`.
- C3 tests them on synthetic inputs (coarse `metrics.json` + hand-written README text). Each must pass
  on a correct case and fail on: a flipped overlap cell, a range off by 0.001, a missing target row,
  a disallowed comparative word, and a `null` range not shown as `n/a`.
- The committed-artifact tests call the same helpers on the real files.
- So the fine guards' logic is verified in C3, before any fine artifact exists.
- Helpers signal every content failure (missing table, missing row, unparsable cell) with
  `AssertionError`, never `AttributeError`, `KeyError` or `IndexError`. That keeps them inside the
  xfail `raises=` set below, so a genuine coding error still fails.

**Strict xfail with `raises=`.**
- Fine parametrizations of committed-artifact tests are marked
  `xfail(strict=True, raises=(FileNotFoundError, AssertionError), reason="#110: fine artifacts land in C4/C5")`.
  A `NameError`, `KeyError` or `TypeError` therefore still fails.
- Negative README checks are bundled in the same test function as a positive check (e.g. "not with
  experiment"), so nothing XPASSes against today's README.
- The existing `fine-corpus` git-record param and the cross-match test pass today: never xfail them.
- Expected C4 set (surrogate only), removed in C4:
  - holdout == dataset
  - surrogate metadata names the dataset
  - seed-sweep consistency
  - phase-baseline recompute
  - the new settings test
  - clean-git-commit `[fine-surrogate]`
- Everything that reads `figures/` or the fine README stays xfailed until C5.

| test | coarse | fine |
|---|---|---|
| `test_regenerated_records_carry_a_clean_git_commit` | ✓ | + fine surrogate + fine figure records |
| `test_surrogate_holdout_targets_equal_the_committed_dataset` | ✓ | ✓ |
| `test_surrogate_metadata_names_the_committed_dataset` | ✓ | ✓ |
| new `test_surrogate_trained_with_the_coarse_settings`: seeds `[1234..1238]`, epochs 2000, 3 `val_configs`, `docker_image == <corpus>/run_metadata.json`'s, `bitwise == "cpu_only"` | ✓ | ✓ |
| `test_figure_metadata_names_the_committed_surrogate_outputs` | ✓ | ✓ + `grid == "fine"`, seconds == sidecar |
| `test_committed_seed_sweep_is_internally_consistent` | ✓ | ✓ |
| `test_committed_phase_baseline_skill_recomputes` | ✓ | ✓ |
| new `test_committed_sidecar_regenerates_from_committed_inputs` | ✓ (default grid) | ✓ (`fine`, recomputed seconds) |
| `test_readme_skill_table_is_metrics_json` | ✓ | ✓ |
| `test_readme_config_resolved_r2_matches_committed_metrics` | ✓ unchanged | replaced by `_R2_NEAR_TARGET.findall(fine_readme) == []`, inside the fine cycle-mean-table test (positive check first), so it cannot XPASS against today's README |
| `test_readme_throughput_figures_match_the_committed_sidecar` | ✓ + literal `"≈3.8×10⁶×"` kept | ✓ via the formatter |
| `test_readme_carries_full_disclosures` | ✓ unchanged | fine disclosure set (spec scenario) incl. "3.7 %", "27.6 %", `RESULTS.md`, `fine-grid-pilot-report.md`, verbatim-in-source check |
| `test_committed_figure_metrics_matches_committed_inputs` | ✓ + `batch_size == 12535` literal | ✓ `batch_size == len(holdout)`; no `latency < 1000`; QS-vs-surrogate RMSE check kept but listed under Risks |
| new fine-only: cost median == sidecar; cycle-mean table; comparison table + prose rule | — | ✓ |
| `seed_variation` tests, `_QUOTED_TARGETS`, `"2.4" not in readme`, `latency_speedup < 1000` | ✓ | — (see Why) |

**Throughput formatter.** `format_power_of_ten(x)` (in `tests/_readme_guards.py`; only tests use
it) is unit-tested on these cases, and the coarse
README test keeps its literal:

| input | output |
|---|---|
| 3.76e6 | `≈3.8×10⁶×` |
| 1.14e8 | `≈1.1×10⁸×` |
| 9.96e5 | `≈1.0×10⁶×` (not `10.0×10⁵`) |

Latency and parallelism use one explicit format per corpus (the coarse string is unchanged).

**Why some checks stay coarse-only:**
- `latency_speedup < 1000` is a coarse fact; on the fine grid the floor should exceed 1,000×.
- `"2.4" not in readme` is a substring check that a legitimate fine value (e.g. −2.43) would trip;
  the fine README uses a pattern check instead: no `2.4×`/`2.4x`, no "diffused-IB underestimate".
- `seed_variation.json` and the five canonical `CF_c ≈v` quotes exist only for coarse.

### D7. Spec delta strategy

- ADDED: the three requirements named in the proposal.
- MODIFIED (full text): the seven named in the proposal. The edits:
  - replace hard-coded `examples/prelim_sweep/...` paths with the corpus's;
  - make the grid wording per-profile;
  - generalize the speedup denominator;
  - label the coarse-only numbers as coarse;
  - restore the provenance sentence and exempt records predating `grid`.
  - The coarse-specific numbers and the #115 note are otherwise kept as they are.
- Not modified:
  - "Force-only evidence-figure scope guard" (still two file inputs);
  - "Cluster-free evidence-figure tests";
  - "Phase-only baseline skill in metrics.json";
  - "Multi-seed sweep reported by the trainer";
  - "Training reproducibility and provenance": the D4 gate is an observed outcome and the
    `cpu_only` bitwise claim stands, as the ADDED requirement states.

### D8. Git discipline

- **Frozen commits.** From task 12 (the D4 gate) on, C1–C3 are immutable: no amend, no rebase, and
  newer `main` is merged in, never rebased onto.
  - A trainer-path fix means new commits and a full redo of §5.
  - A figure-code fix before the push is a new commit C4′, with the figure regenerated at C4′. If C5
    already exists locally (unpushed), C5 is redone:
    1. Save the README edits as bytes outside the repository.
    2. `git reset --hard C4`.
    3. Commit the fix as C4′.
    4. Regenerate the figure at the clean C4′.
    5. Restore the README bytes and recommit C5.

    Only the regenerated PNG is then reachable from the branch.
- **Two provenance scopes** (task 22):
  - *Surrogate record* (commit C3): the trainer path, i.e. `src/mosquito_cfd/force_surrogate/`
    excluding `evidence_figure.py` and `cfd_cost.py`, plus `src/mosquito_cfd/benchmarks/metadata.py`,
    `scripts/train_surrogate.py` and `uv.lock`. A non-empty diff → back to §5.
  - *Figure record* (commit C4/C4′): `evidence_figure.py`, `cfd_cost.py`, `sidecar.py`, `train.py`
    (it supplies `write_json`), `benchmarks/metadata.py`, `scripts/make_evidence_figure.py`,
    `scripts/cfd_seconds_per_step.py` and `uv.lock`. A non-empty diff → regenerate the figure
    only.
- **One blob per binary in the pushed range**, checked at task 24 with
  `git rev-list --objects origin/main..HEAD`.
- **After the push:** the policy for review findings that touch figure code is decided by the user
  at approval: BLOCKING findings only, second PNG reported (see the proposal).

## Risks

- **The D4 gate fails.** Halt and diagnose with the user (in-process sweep state vs GPU
  nondeterminism, as #127 D5 did). No binary is committed before the gate passes.
- **The coarse no-op gate fails or a precondition fails.** Halt; fix the code, not the gate.
- **A fine guard legitimately fires.** Example: fine QS RMSE not above the surrogate RMSE, or a
  literal written for coarse magnitudes. Halt for a decision; never re-pin silently.
- **Fine skill could be below the phase-only baseline for some target.** The caption flags it,
  subordinate. Nothing assumes positive skill.
- **More than one blob per binary.** D8.
