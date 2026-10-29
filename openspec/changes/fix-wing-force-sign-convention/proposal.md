# Report wing coefficients as the IB force and moment on the wing

## Why

Every committed wing coefficient is the force **on the air**, not on the wing (issue #109). The wing
path builds `CF_x..CF_mz`, the flapping-wing lab and body-frame series, and the T4 CFD series from
IAMReX's `ib_force` / `ib_moment`, which act on the fluid, without negating them. The sphere and
ellipsoid paths do negate. No test, docstring, spec or metadata field states which convention the wing
coefficients carry.

Every *graded* consumer is sign-blind (R², skill, `|CF|` gates, magnitude-graded T4), which is why
nothing broke. The repository's eventual RL-in-the-loop consumer (the "Funded / long-term" column of
`docs/field_surrogate/roadmap.md`) will take the predicted force as acting on the body. At today's sign
it would push the virtual mosquito the wrong way, and every gate would still pass.

After this change, what the coefficients and surrogates carry is the **IB force and moment on the
wing**. The solver's free-body 6-DOF balance would add an internal-fluid momentum term `ρ_f·SumU`.
That balance runs only for freely moving bodies, never for this prescribed-motion wing. For this
zero-thickness wing the term is the momentum change of fluid in a slab about one grid cell either side
of the sheet, so it depends on the grid. Whether it belongs in a physical force is the follow-up
question. The canonical documentation says this, so that consumer knows what it receives.

The convention was established with evidence before any change was proposed. The primary line was a
pre-registered blind test: the second law, as the work-from-rest inequality, holds in 57 of 57 runs.
Design "Evidence" records every line, including what was seen before pre-registration.

## What Changes

- **BREAKING — wing coefficients report the IB force and moment on the wing.**
  - Extraction applies the hinge shift to the solver's values exactly as today, then negates:
    `CF_F = −F_ib / F_ref` and `CF_M = −(M_ib + (r_origin − r_hinge) × F_ib) / M_ref`.
  - Every committed `CF_*` changes sign exactly: new = −old bitwise, because IEEE negation is exact.
  - Nothing else in the parquet changes. Raw `Fx..Mz` keep the solver's on-fluid values, the #108
    audit-trail rule, so the frozen raw-force shas hold.
- **One helper owns the sign.** `force_on_wing(...)` in `force_surrogate/normalization.py` is the only
  `−1` in the wing paths, and both paths call it. A spy test proves neither path negates by other means.
- **Physics guards pin the convention.** They recompute, from committed data:
  - the work-from-rest inequality, with a late-only form so the verdict does not rest on the impulsive
    start;
  - force/moment sign consistency on the unshifted raw columns.
  The coefficient side has the mirror inequality and a half-flip check. Algebraic guards with
  non-vacuity clauses pin `CF == −(raw, shifted)/ref`.
- **The convention travels with the data.** A `force_sign_convention` key sits in each corpus
  `run_metadata.json`, beside #108's `moment_reference`. `dataset.units.json` is unchanged, because its
  vocabulary admits only units. The rule is stated canonically in a new `## Force and moment sign`
  section of `docs/coordinate-convention.md`, and a fixed list of documents links it.
- **Both corpora are re-extracted and both surrogates retrained** (5 seeds each, pre-registered gate),
  and both evidence figures are regenerated.
- **The flapping-wing path adopts the same convention:**
  - `reconstruct_wing_forces` (6-DOF force `F_hydro = ρ_f·(SumU + ib_w)`, `ib_w = −ib_force`);
  - `reconstruct_wing_body_forces`, the T4 CFD series;
  - five force figures, and the signed RESULTS.md values, including the phase table's `CF_z (lab)`
    column.
  - The two figure scripts that compute coefficients directly (`plot_f1_forces`, V1) go through the
    same helper.
  - The false docstring "our ib_force is the TOTAL hydrodynamic force" is corrected.
- **The added-mass-subtracted diagnostic is relabelled.**
  - Today its "subtracted" series is exactly the negated 6-DOF force, and its "total" is the IB-only
    force.
  - It becomes a comparison of the 6-DOF force with `ib_w`, with keys `peak_cf_*_{6dof,ib}` and
    `drop_frac = 1 − peak_ib/peak_6dof`:

    | | 6-DOF | `ib_w` | `drop_frac` |
    |---|---|---|---|
    | chord | 0.6517 | 0.9231 | −0.4165 |
    | normal | 2.2851 | 2.6060 | −0.1404 |

    Removing the internal-fluid term raises the peaks by 42 % and 14 %. Both denominators get a
    degeneracy floor.
  - "Total" keeps its single existing meaning, `ib_w`.
  - The prose names `ρ_f·SumU` as the solver's internal-fluid term, not van Veen's added mass.
- **`verify_moment_reextraction.py`'s zero-offset control** compares coefficients against the negated
  baseline, the #109 sign.
- **`visualize.py`'s `forces` subcommand is removed.** It read plotfile marker increments and labelled
  `Fy` as lift.
- **#19 is folded in:** `IB_Particle_1.csv` is recorded as verified (spec plus three source comments),
  and the `--csv-name` escape hatch is kept.

### What does NOT change

- **No CFD re-run; no change to raw columns, the hinge shift or `shift_moment_reference`.**
- **Every magnitude-graded verdict:** `plausibility_gate`, `body_frame_overall_match`, T4
  `normal_mag_pass`/`closure_pass`, peak phases, corpus guards, grid convergence.
- **The trainer and the evidence-figure code:** no functional change is planned. The figures change
  because their inputs change. `overshoot_factor` (an RMS ratio) stays exactly equal.
  `baseline_rmse_cf_z` drops to ≈0.5175 / ≈0.4782 because the quasi-steady lift and the CFD lift now
  share a sign.

## Impact

- **Affected specs:**
  - `force-surrogate`:
    - MODIFIED: dataset extraction; runner CSV-name wording (#19); hinge reference; scale-invariance;
      dataset build provenance; surrogate-to-dataset reconciliation; fine reproducibility gate.
    - ADDED: on-wing coefficients; re-extraction and retrain gates.
  - `flapping-wing-validation`:
    - MODIFIED: 6-DOF decomposition; RESULTS.md reproducibility; added-mass-subtracted diagnostic.
    - ADDED: on-wing coefficients.
  - `coordinate-convention`: ADDED the canonical sign section.
- **Affected code:**
  - `force_surrogate/normalization.py`, `force_surrogate/dataset.py`, `benchmarks/wing_kinematics.py`
    (`angular_velocity`), `benchmarks/flapping_wing.py`;
  - `scripts/extract_forces.py` (provenance key), `scripts/verify_moment_reextraction.py`
    (zero-offset control), the new `scripts/verify_force_sign_reextraction.py`;
  - `examples/flapping_wing/{visualize.py, generate_all_figures.py, generate_validation_figures.py,
    make_force_decomposition_figure.py, make_force_timeseries_3grid_figure.py}` (labels and sign);
  - #19 comments in `force_surrogate/runner.py`, `force_surrogate/run_one_config.py` and
    `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`;
  - `force_surrogate/evidence_figure.py` (PR3: the "span-normal" panel title only; the figure is
    regenerated there anyway).
- **Affected artifacts:**
  - both `dataset.parquet` and corpus `run_metadata.json`;
  - the coarse `sweep_provenance.json` (`downstream_artifacts_regenerated_from`);
  - both `surrogate/` directories, plus the coarse `seed_variation.json`;
  - both evidence-figure sets;
  - `examples/flapping_wing/figures/{fig_forces, fig_force_decomposition, fig_force_timeseries_3grid}.{png,pdf}`,
    `V1_three_convention_CF.png` and `V4_added_mass.png`: exactly these 8 files.
  - About 30 MB of blobs in total, each under GitHub's 50 MB warning.
- **Affected docs:**
  - `docs/coordinate-convention.md`;
  - `examples/flapping_wing/RESULTS.md` and `examples/flapping_wing/figures/README.md`;
  - both corpus READMEs;
  - `docs/force_surrogate/roadmap.md`, `docs/field_surrogate/roadmap.md`,
    `docs/aerodynamics_validation/roadmap.md`;
  - `docs/CHANGELOG.md` (one entry per PR).
- **Affected tests:** enumerated per PR in tasks.md task 0, derived by running the suite on simulated
  post-change trees, not by reading. Any test outside that list that needs an edit halts the change.
- **Unblocks:** #111 (extending the quasi-steady model to moments needs a settled sign).

### Deliberately out of scope

- **#133** (filed in scoping): the T4 *model's* normal force alternates sign each half-stroke, while the
  CFD's is one-signed. This change flips only the CFD series, so T4's reported signed
  `normal_curve_rmse` moves (T2a 1.759 → 1.984). No RESULTS.md literal quotes it.
- **Which CFD force van Veen should be compared with,** `ib_w` or the 6-DOF force: a follow-up issue,
  filed in PR2a.
- **Stale T4 literals already in the live flapping-wing spec** (≈2.48/2.61, ~0.058 cycle, against
  RESULTS.md's fine-grid 2.23 / 0.055): pre-existing drift, to be added to #115.
- **Whether the surrogate's `docker_image` should name the training environment** rather than the CFD
  image: pre-existing precedent, enforced by a test. It is noted in design Risks and not changed here.
- **#124** (V3 already stale), **#114**, **#130**, **#131**, **#79**, **#102**, **#129**.

### Delivery

Four PRs in the fixed order PR1 → PR2a → PR2b → PR3. Each is opened off `main` after the previous one
merges, sequential as #108 was, not stacked. The canonical section carries one data-tied pending
phrase per path, so it stays true at every pushed head:

1. **PR1 — evidence and groundwork, no binaries.**
   - `angular_velocity`, `force_on_wing`, the physics guards (the coefficient side is a strict xfail),
     the canonical section with its data-tied pending phrase;
   - #19, and the docstring fixes.
2. **PR2a — flapping-wing path.** On-wing series, the 6-DOF relabel, RESULTS.md, the 8 figure files, and
   `visualize.py`. It needs no `Z:` drive and no corpus data.
3. **PR2b — corpus flip.**
   - Extraction calls the helper, and both parquets are re-extracted and verified.
   - The coefficient-side guards turn green, and the provenance key lands.
   - The staleness banners pin "stale by exactly a sign flip".
4. **PR3 — retrain and regenerate.** Pre-registered gate, 5-seed retrains, evidence figures, numbers
   re-quoted, banners removed. "Closes #109."
