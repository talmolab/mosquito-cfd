# Design — wing coefficients report the IB force and moment on the wing

## Context

IAMReX's diffused-IB writer (`WriteIBForceAndMoment`, `DiffusedIB.cpp`, pinned `f93dc794`) emits
`kernel.ib_force` / `kernel.ib_moment`. Each is the sum over markers of
`F_marker = (U_wing − u*)/dt · dv` (and `r × F_marker`), the quantity `ForceSpreading_cic` **adds** to
the Eulerian forcing field. That makes it a force on the fluid. `ib_w = −ib_force` is therefore the
**IB force on the wing**, and this change makes every wing coefficient `ib_w`.

The solver also has a 6-DOF balance. The source shows what it is and how far it applies:
- **The balance.** For a freely translating particle (`TL == 2`, `DiffusedIB.cpp:1082-1086`), the
  velocity update uses `ρ_f·(Δsum_u/dt − ib_force)`, i.e. `F_hydro = ρ_f·(SumU + ib_w)`, plus gravity,
  buoyancy and `Fcp`.
- **Where it applies.** The flapping wing has prescribed motion, so the solver never evaluates this
  balance for the wing. "6-DOF force" here means that formula applied to the wing's columns, not a
  quantity the solver computes.
- **What `SumU` is.** `CalculateSumU_cir` (`:223`) gives `Σ u·pvf·dx³`, the momentum of fluid weighted
  by the body volume fraction. The CSV column is its time difference (`:1267-1269`).
- **What "inside" means for the wing.** For the vertex-file wing (`geometry_type = 4`, `:190-213`) the
  level set is `phi = (distance to nearest marker − dx)/a`, so every point within one grid cell of a
  marker counts as body.
- **Consequence.** The wing has no real thickness, so `ρ_f·SumU` is the momentum change of fluid in a
  slab about two cells thick around the sheet. It depends on the grid, and is largely a discretization
  artifact. It is not a corpus quantity, and its physical status is the follow-up issue's question.

| Path | Today | After |
|---|---|---|
| `force_surrogate/dataset.py` → corpora → surrogates → evidence figures | no sign change | IB force on wing |
| `benchmarks/flapping_wing.py` (lab, body-frame, T4, added-mass diagnostic) and two figure scripts that compute CF directly | no sign change; `cf_*_hydro = added − ib` | IB force on wing |
| sphere / heaving ellipsoid (`analyze_sphere.py`, `heaving_ellipsoid/*`) | negates | unchanged |

The user decided:
- coefficients on the wing; raw columns as written;
- a 5-seed retrain, not an exact negation transform;
- the flapping-wing path, #19 and the diagnostic relabel are in scope;
- the convention lives in `run_metadata.json`, not `dataset.units.json`;
- `visualize.py forces` is removed;
- four PRs.

After review round 2, the order is fixed as **PR1 → PR2a → PR2b → PR3**. Each PR is opened off `main`
after its predecessor merges.

## Evidence

The oracle plan was pre-registered with the user before the blind lines were computed. Lines seen
before pre-registration are marked.

1. **Blind, primary — work from rest.** `M_hinge · Ω = Σ F_i · U_wing(x_i)`, with `Ω` from the analytic
   kinematics and `θ = 0` in every deck.
   - For the diffused forcing this is the work done on the fluid plus a non-negative slip term
     `Σ|U_w − u*|² dv/dt`. Starting from rest, `W(t)` should not go negative. With open outflow
     boundaries that is an assumption, not a theorem, so its margins are measured.
   - On the solver's moments shifted to the hinge, `W(t) ≥ 0` at **every row of all 57 runs**: the 54
     corpus configurations plus the T2a, medium and fine validation CSVs. The minimum is exactly 0, at
     `t = 0`.
   - With `W₀` the value at the first row with `t ≥ 0.05`, the late increment `W(t) − W₀` is never
     negative.
   - The impulsive start supplies 31–65 % of `W₀`, which is why the late form is guarded too.
   - **Revised in the PR1 review (`/review-pr 134`).** The late form is start-specific: it holds
     for every `t₀` in [0.001, 0.05] but fails 14/57 runs from `t₀ = 0.1` and 45/57 from 0.2,
     because the power is negative within a beat on up to 23 % of rows. The guard therefore
     starts it at the end of the impulsive-start transient (`t ≥ 0.005`, the bound in the
     `STEADY_WINDOW_T0` comment), where it holds 57/57. The margin that lets `W ≥ 0` go untoleranced is `min W[1:] / max|W| = 0.0059`. Shifting
     `Ω` one step either way changes nothing (57/57 both ways).
   - On coefficient-scaled moments, `min W` over `t ≥ 0.05` is +0.961 (fine corpus) and +2.10 (coarse
     corpus).
   - Under the opposite convention every run would be ≤ 0.
2. **Blind — one convention for force and moment.** On the solver's **unshifted** columns,
   `corr(Mz, −Fx) ≥ +0.870` and `corr(Mx, +Fz) ≥ +0.740` in all 57 runs. The first pre-registered form,
   `corr(Mz_hinge, −Fx)`, was found in review to be near-tautological (the shift adds `−1.5·Fx`) and was
   replaced.
3. **Seen before pre-registration (disclosed):**
   - The settled-beat mean of the committed `CF_z` is −0.50 (coarse) and −0.49 (fine), while the deck's
     kinematics give upward lift on the wing (`α = α_amp·cos ωt` raises the forward edge on both
     half-strokes). The C++ rotation matrix matches the Python mirror entry for entry.
   - The ellipsoid (same writer) has `Fx < 0` against a `+x` freestream.
   - The non-negative Sane–Dickinson lift sits at RMSE 1.7785 (coarse) / 1.7588 (fine) from the
     committed `CF_z`, against 0.5175 / 0.4782 from its negation.
4. **Secondary — source.** The marker force is *added* to the Eulerian forcing.
   `docs/aerodynamics_validation/t1a-findings.md:73-80` already writes `F_drag = −ρ_f·F_ib`.

The pre-registered "settled-beat cycle-mean power" variant is not computable: no corpus run has a
complete beat after beat 0, and the validation CSVs span less than one beat. The work-from-rest form is
strictly stronger and is used instead. This is recorded here rather than substituted silently.

## Decisions

### D1 — One helper owns the sign; applied after the hinge shift

`force_on_wing(*components)` in `force_surrogate/normalization.py` returns the elementwise negation of
each array it is given. Its docstring says it returns the IB reaction on the wing to the solver's
on-fluid `ib_force`/`ib_moment`, and links the canonical section; the evidence lives only there. It is
the only `−1` in the wing paths. Those paths are:
- dataset extraction;
- `flapping_wing.py`'s `reconstruct_wing_forces`, `reconstruct_wing_body_forces` and
  `body_frame_added_mass_subtracted`;
- `generate_all_figures.plot_f1_forces` and `generate_validation_figures.fig_v1_three_convention`,
  both of which compute CF directly from the CSV.

The sphere and ellipsoid paths keep their own, already on-body negation. `IB_FORCE_ACTS_ON = "fluid"`
is exported for metadata and docs.

Extraction shifts the solver's moments to the hinge with the solver's forces (`shift_moment_reference`,
unchanged), applies `force_on_wing` to `F` and to the shifted `M`, then normalizes. The shift is linear,
so negating first would give the same bits. The order is chosen so the shift stays a statement about
solver quantities.

**Spy test.** At each use site (a name import defeats module patching), an identity spy replaces
`force_on_wing`. The assertions:
- `build_dataset` emits exactly `+F/f_ref` and `+(M + d×F)/m_ref`;
- every series that **is** the IB force equals the pre-change on-fluid series bitwise. These are
  `cf_*_ib`, the body-frame `CF_chord`/`CF_normal`, the T4 CFD series, `peak_cf_*_ib`, and the
  `plot_f1_forces`/V1 coefficients;
- every **composite** equals its formula evaluated on the spied output (`cf_hydro == cf_added +
  ρ_f·cf_ib_spied`; `peak_cf_*_6dof` from `ρ_f·(SumU + ib_spied)`). Round 3 showed that requiring the
  old composite series is unsatisfiable by correct code, because the 6-DOF formula is written in `ib_w`;
- across all calls, the multiset of arrays passed equals the expected set, each passed exactly once
  (identity-compared, not counted per call).

A doubling spy would not prove "no other site applies the sign", so it is not used.

**Why not inside `compute_force_coefficients`?** It is a pure normalization, shared by tests and
fixtures, with exact-decimal helper tests. The `ForceCoefficients` / `MomentCoefficients` containers
stay sign-agnostic. Their docstrings say so, link the canonical section, and correct the "span-normal"
description of `cf_z` to "lab vertical (z)". **They carry no interim status** (D4), so `normalization.py`
never changes after PR2b's extraction.

### D2 — Raw columns stay as written; guards comparing CF with raw are rewritten

This follows #108 D7. Scenarios asserting `CF_x == Fx/f_ref` or `CF_mx == (Mx + a·Fz)/m_ref` are
rewritten to the negated form, each with a non-vacuity clause (not `allclose` to the unnegated form).
The IB-part arm uses the coefficients scaled back, `b = CF_mx·m_ref / (CF_z·f_ref)`: the sign cancels,
and a half-flip inside extraction fails. Exact negation of a re-extracted corpus is specified once, in
the verifier scenario (D8). Every other mention cross-references it.

### D3 — The convention is pinned by physics, not by re-running the algebra

`wing_kinematics.angular_velocity(t, frequency, stroke_amp_rad, pitch_amp_rad, deviation_amp_rad=0)`
returns lab-frame `Ω = φ̇ ẑ + α̇ Rz(φ) ŷ + θ̇ Rz(φ)Ry(α) x̂`. It is tested against the skew part of
`Ṙ Rᵀ` from a central finite difference of `rotation_matrix`, with `rtol=1e-6` and
`atol=1e-9·max|Ω|`. Known answer at `t = 0`, with `deviation_amp = 0`: `Ω = (0, 0, φ_amp·2πf)`.

Guards in `tests/test_ib_force_sign_convention.py`:

- **Raw, on-fluid, 57 runs.**
  - Assertions: `W ≥ 0` at every row, `W > 0` after the first, and `W(t) − W₀ ≥ 0` after `W₀` (the
    first row with `t ≥ 0.005`, the end of the impulsive-start transient).
  - Non-vacuity: exactly 57 runs, ≥ 2 late rows each; a NaN, zero-row or too-short run fails. Corpus
    runs start at `t = 0` with strictly increasing time.
  - Keep-last `iStep` dedup.
  - **Deck mapping by sha256.** Each validation CSV's deck sha equals the `inputs.hash` in its run
    metadata: `forces_t2a_newconv.csv` → `inputs.3d.validation` (`run_metadata_t2a.json`, `f9b69d98…`),
    `forces_medium.csv` → `inputs.3d.convergence_medium` (`run_metadata_t3b.json`, `1e6c0c59…`),
    `forces_fine.csv` → `inputs.3d.convergence_fine` (`run_metadata_t3c.json`, `c4f0db57…`). Each hinge
    equals the literal `(4.0, 0.5, 4.0)`.
  - The `X,Y,Z` = `particle_inputs` check stays only as a sanity check. All five decks share `(4, 2, 4)`,
    so it cannot tell them apart (round-2 review, verified).
- **Raw consistency:** `corr(Mz, −Fx) > 0` and `corr(Mx, Fz) > 0` on the **unshifted** columns, per run.
- **Coefficients, on-wing, 54 corpus configurations.**
  - Assertions: `W_wing ≤ 0` (rows and late increment) and `corr(CF_mz, −CF_x) > 0`.
  - The sign predicates raise a dedicated `CoefficientsOnFluid(AssertionError)`; the non-vacuity checks
    use plain `assert`. They include `CF_*` finite and equal to `|F|/f_ref`, `|M_hinge|/m_ref` in
    magnitude, so zeroed, NaN or rescaled coefficients FAIL rather than XFAIL.
  - In PR1 the test is `xfail(strict=True, raises=CoefficientsOnFluid)`. A non-vacuity break therefore
    FAILs rather than XFAILs, and task 7 includes that mutant.
  - The raw-side checks live in separate, never-xfail tests.

Expected mutation table. Task 7 re-runs every row on saved-bytes copies and records the measured
counts; a differing row is a finding to reconcile:

| mutant | raw `W` | raw corr | coeff `W` | coeff corr |
|---|---|---|---|---|
| all six raw negated | fails 57/57 | passes | — | — |
| raw `M` only negated | fails 57/57 (settled in round 3 under the full rows-plus-late form) | fails | — | — |
| raw `F` only negated | fails 57/57 | fails | — | — |
| hinge shift dropped (raw) | not detected (owned by #108's reconcile guard) | — | — | — |
| all `CF_*` negated (today's corpus) | — | — | fails | passes |
| `CF_m*` only negated | — | — | fails | fails |
| `CF_x..z` only negated | — | — | passes | fails |
| wrong deck for T2a (`validation_v2`) | caught by the deck-sha check | | | |
| one config dropped, under the PR1 xfail | FAIL (not XFAIL) | | | |

### D4 — Where the convention is recorded

- **Data:** `force_sign_convention` in each corpus `run_metadata.json`, specified in the MODIFIED
  "Dataset build provenance" requirement beside `moment_reference`. A committed-artifact test checks
  both corpora, plus a literal pin of each `dataset.units.json`.
- **Prose:** one `## Force and moment sign` section in `docs/coordinate-convention.md`.
  - It uses "lab-frame `CF_x..CF_z`" and "body-frame `CF_chord/CF_normal`" explicitly.
  - It links the existing raw-vs-derived paragraph (`:116-127`).
  - It notes the internal-fluid term and the on-body sphere/ellipsoid paths.
  - It is the only carrier of the work-inequality evidence. A scan with fixed tokens over a fixed
    search set enforces this; the coordinate-convention ADDED requirement defines both.
- **Links:** the fixed document list links the anchor. Each link lands in the named PR, and the guard's
  list grows in the same commit.
- **Interim truth, section only.** Three pending phrases. Each is an exact pinned literal (the
  coordinate-convention ADDED requirement), occurs at most once, and is governed by a guard:
  - **Corpus phrase:** present iff the committed coarse `CF_x` is not `allclose` to `−Fx/f_ref`. Tied to
    data; tested with a parquet copy whose `CF_*` alone are negated. Removed in PR2b.
  - **Flapping-wing phrase:** present iff `reconstruct_wing_forces(forces_t2a_newconv.csv).cf_x_ib` is
    not `allclose` to `−Fx/f_ref`. Tied to the **code path**: negating the CSV negates both sides.
    Tested by monkeypatching `force_on_wing` at the use site. Removed in PR2a.
  - **Surrogate phrase:** present iff **both** corpus READMEs carry the staleness banner. Added in PR2b,
    removed in PR3.

  The section is true at every pushed head in any landing order. Docstrings carry no interim status,
  which keeps the extraction scope frozen (D9).
- **Stage-2:** in **PR3**, one `docs/field_surrogate/roadmap.md` sentence: "the force-surrogate outputs
  are the IB force and moment on the wing; the solver's free-body balance would add a grid-dependent
  internal-fluid term, whose physical status is open (follow-up issue)", plus
  the link.

### D5 — The flapping-wing path (PR2a)

- `reconstruct_wing_forces`: `cf_*_ib` is `ib_w`; `cf_hydro = cf_added + ρ_f·cf_ib`, with `ρ_f = 1` in
  every committed run. A test checks the raw identity `cf_hydro·F_ref = ρ_f·(SumU − ib_force)`.
- `reconstruct_wing_body_forces` rotates `ib_w`, and T4 inherits it.
  - Graded T4 quantities use `|·|` and are unchanged.
  - The independent pin is the **existing** graded literals in `test_wing_body_frame.py` and the T4
    tests, which stay green with no edit. Re-running new code on a negated CSV would be circular.
- `plot_f1_forces` and `fig_v1_three_convention` route through `force_on_wing`.
- **The added-mass-subtracted diagnostic is relabelled.**
  - Today "subtracted" (`ib − ρ·SumU`) is exactly the negated 6-DOF force, and "total" is IB-only.
  - Return keys become `peak_cf_{chord,normal}_{6dof,ib}`, `{chord,normal}_drop_frac = 1 − peak_ib/peak_6dof`
    and `am_rms_share_*` (unchanged).
  - **Degeneracy floors on both denominators:** `peak_6dof` (for `drop_frac`) and `rms(ib)` (for the
    share), each raising a `ValueError` that names it. Tested with a zero-6-DOF case
    (`ρ_f·SumU = −ib_w`) and a zero-`ib_w` case; a guard on only one denominator fails.
  - Predicted values, computed during review from the current magnitudes:

    | | 6-DOF | `ib_w` | `drop_frac` | i.e. removing `ρ_f·SumU` raises the peak by |
    |---|---|---|---|---|
    | chord | 0.6517 | 0.9231 | −0.4165 | 42 % |
    | normal | 2.2851 | 2.6060 | −0.1404 | 14 % |

  - The shares 0.8392 / 0.1278 are unchanged. The chord peaks are 1094 timesteps apart. At the 6-DOF
    chord peak, `1 − |ib_w|/|F_6dof| = −0.394`, so `|ib_w|` exceeds `|F_6dof|` by 39 % there.
  - Percent values are always phrased as rises; a bare "−42 %" is never printed.
  - **Vocabulary.**
    - "Total" keeps its one existing meaning, `ib_w` (T4's "CFD total"), and the 6-DOF force is always
      called "6-DOF".
    - The requirement and function names stay; RESULTS.md and the spec carry one sentence saying the
      name is historical (`ib_w` is the 6-DOF force minus `ρ_f·SumU`).
    - `ρ_f·SumU` is "the solver's internal-fluid momentum term (called 'added mass' in this code); it is
      not van Veen's added-mass component". Which CFD force van Veen should be compared with is left to
      the follow-up issue; nothing claims `ib_w` contains van Veen's added mass.
- **RESULTS.md edits** (every literal comes from the reproducibility tests):
  - `:27-28` "Our `ib_force` is the **total** hydrodynamic force" → "'Total' here means all aerodynamic
    mechanisms (as opposed to van Veen's translational-only), measured as the IB force on the wing `ib_w`.
    It is not the solver's free-body 6-DOF balance, which would add the internal-fluid term
    `ρ_f·SumU`. For this zero-thickness wing that term is fluid momentum in a one-cell slab around the
    sheet."
  - `ib_force`-as-coefficient sites → `ib_w` / "IB force on the wing": `:170` header, `:188`,
    `:196`, `:209-210`, `:218`, `:253`, `:322`. Line numbers are at `a2e8f64`; PR2a re-locates them.
  - Interim table header `:222` → "6-DOF `ρ_f·(SumU + ib_w)` | IB force on wing `ib_w` | van Veen".
    Cells: 0.652 / 0.923 and 2.285 / 2.606, with "removing the term raises the peak 42 % / 14 %".
  - `:230-232` peak and instantaneous wording, as above. `:231` and `:322-323` "added mass dominates" →
    "the term is large (84 % of chord RMS); at the 6-DOF chord peak `|ib_w|` exceeds `|F_6dof|` by 39 %".
  - `:241` "even added-mass-subtracted, CF_chord ≈ 0.652" → "even IB-only, CF_chord ≈ 0.923 (~3× van
    Veen's 0.3; the 6-DOF 0.652 is ~2×)". `:35` is reworded to match.
  - Phase table: the `Fz` cells keep solver values, labelled "solver `ib_force`, on the fluid". The
    `CF_z (lab)` column becomes `−Fz/F_ref` (+0.049 / +1.449 / +0.092 / +1.459), and the `:410` caption
    gives `−Fz / F_ref` with the link.
  - Lab ranges become `CF_x ≈ [−2.37, +2.35]` and `CF_z ≈ [−0.03, +1.46]`.
  - `:279` gains a #133 pointer. There is no RMSE literal, so none changes.
- **Other labels:**
  - `figures/README.md:69` "CFD total `ib_force`" → "CFD IB force on the wing".
  - `figures/README.md:46`: **keeps ~10 % / ~40 %**, which is correct for the contrast-baseline
    `forces.csv` that V4 plots. It is labelled as such, and only "fraction of `ib_force`" is reworded.
  - `generate_validation_figures.py`: `:146` docstring; legend `:155` "IB force on wing (gated)"; `:156`
    and `:163` "added-mass" → "internal-fluid term ρ_f·SumU".
  - `make_force_decomposition_figure.py:4,75` "CFD total (ib_force)" → "CFD IB force on wing". The edit
    to `test_flapping_wing_validation_figures.py:52`, which looks that label up exactly, goes in the
    same commit.
  - `make_force_timeseries_3grid_figure.py:80` "body-frame lift force" → "wing-normal force".
  - `generate_all_figures.py:317` "span-axis" → "lab vertical".
  - `docs/aerodynamics_validation/roadmap.md:97`, keeping `test_no_false_diffused_ib_claim`'s T4-row
    guard green.
  - `flapping_wing.py:519-524, 543-544, 579-589, 604, 679-690`: comments, docstrings and the error
    message "of the total ib_force".
- `visualize.py`: remove `extract_forces`, `visualize_forces` and the `forces` subparser.
- **Figure regeneration: exactly 8 files.**
  - Call only `plot_f1_forces`, `fig_v1_three_convention`, `fig_v4_added_mass`,
    `make_force_decomposition_figure.main` and `make_force_timeseries_3grid_figure.main`. Never call the
    two `main()`s, which rewrite V2/V3/V5, `validation_figures_summary.json` (V3 is #124's) and the
    planform/kinematics/phase PDFs.
  - Write PDFs with `metadata={"CreationDate": None}`. **Render twice and `cmp`** as a gate.
  - `git status --porcelain` lists exactly the 8 files, and `validation_figures_summary.json` is
    unchanged.
  - **PR2a figure scope:** `flapping_wing.py`, `wing_kinematics.py`, `normalization.py`, the five entry
    points and their modules, the three validation CSVs, and `uv.lock`. A diff in this scope after
    rendering means re-render.
  - The generating commit is recorded in the PR body. Whether the 3-grid CF_chord band (positive side
    only, `:59`) still sits on the series is checked, not assumed.

### D6 — The stale interval between PR2b and PR3 is pinned, not exempted

After PR2b the committed surrogates predict the on-fluid sign. The MODIFIED "Committed surrogate
artifacts are tied to the dataset…" has exactly one pinned state, present iff both corpus READMEs carry
the staleness banner:

- every holdout `<target>_true` equals **−dataset**, and the column is not `allclose` to `+dataset`.
  Any all-zero column is excepted and reported; none is expected, and the clause only keeps the
  `allclose` check well-defined;
- `inputs.hash` equals the pinned sha256 of that corpus's `a2e8f64` parquet — coarse `01c88ae9…`, fine
  `2092f0fd…` (verified equal to the committed surrogate `inputs.hash` and the coarse `seed_variation`
  sha) — and not the current sha;
- the phase-baseline skill recomputes against `−dataset`;
- the coarse `seed_variation.json` `datasets.hinge_referenced.dataset_sha256` equals the same pinned
  literal.

The banner and the section's surrogate phrase tell a consumer that the committed surrogate predicts the
on-fluid sign, so its outputs must be negated. A tmp-copy test exercises the stale branch (negated
parquet plus a banner README) so it keeps CI coverage before PR2b and after PR3. PR3 removes the
banners, and the tests revert to the unconditional branch with no code change. The fine reproducibility
scenario's carve-out replaces only its `<target>_true`, `inputs.hash` and `phase_baseline_skill`
clauses.

### D7 — The pre-registered retrain gate (PR3)

Retraining on `−y` equals retraining on `y` with the output layer's initial weights and bias negated, so
the networks are genuinely new draws.

- **G0 — equivariance.**
  - It lives in `tests/test_force_surrogate_train_gpu.py` (gpu-marked, `device="cpu"`) because torch and
    physicsnemo are only in the `train` group. It is a one-shot WSL gate.
  - It drives the trainer's per-seed path (`Standardizer` → `train_model` with `x_val`/`y_val` →
    `predict` → `inverse_transform`), patching `build_model` to negate the final `Linear`'s W and b under
    `no_grad`. It first asserts that exactly those two parameters were negated.
  - Pass: `np.array_equal(p_neg, −p)`.
  - Mutants that must fail: an output activation appended; only W negated; an asymmetric loss. Weight
    decay and gradient clipping are sign-symmetric and need no mutant.
  - First verify that physicsnemo's final layer has no `weight_norm`, `weight_fact` or adaptive
    activation.
- **G1 — run-twice reproducibility, both corpora.**
  - Two separate processes from one clean commit.
  - In WSL: `git status --porcelain` empty, `test ! -e .venv/bin`, and `git rev-parse HEAD` equal to the
    recorded commit.
  - Both runs record `dirty: false`.
- **G2 — data identity:** D6's unconditional branch.
- **G3 — skill ranges overlap.**
  - For each corpus and target, the new `seed_sweep.range.<target>.skill` intersects the `a2e8f64`
    interval (12 test literals).
  - The same CI test asserts that `inputs.hash` equals sha256(`dataset.parquet`) and differs from the
    pinned pre-change sha, so it cannot pass vacuously on the old surrogate.
  - **Pre-registered false-alarm rate:** ≈ 0.8 % per pair and ≈ 9 % family-wise, if the seed sets were
    exchangeable; correlation lowers it. A failure is evidence to examine. The user decides between more
    seeds and the exact negation transform; switching is an OpenSpec amendment and re-review.
  - Config-resolved R² is not gated.
- **G4 — exact sidecar invariants** (test literals):
  - `overshoot_factor` equals 1.3435407346470738 / 1.4074274138248275 exactly;
  - `baseline_rmse_cf_z` recomputes to `rel=1e-12`, and `round(·, 4)` is 0.5175 / 0.4782.
- **Retirement.** The G3 and G4 test docstrings name this change and say a later change's OpenSpec
  proposal may retire them (#114/#125 will legitimately retrain).

### D8 — Re-extraction is verified externally (PR2b)

`scripts/verify_force_sign_reextraction.py --baseline-ref <merge-base>` takes the PR2b branch's
merge-base with `origin/main`, recorded in the PR body. It checks:

- **Parquet:** schema, row order and non-`CF_*` columns value-identical; `CF_* == −baseline` exactly,
  with NaN positions identical.
- **Metadata:**
  - `run_id`, `timestamp` and `git` may differ. **`hardware` is reported, not compared**: a driver
    update or another host must not halt a correct re-extraction.
  - Exactly one key is added, `force_sign_convention`, with its pinned value.
  - Every other key is identical: `inputs` (`file` and `hash`), `extraction_inputs` (every `csv_sha256`
    and `input_dir`), `moment_reference`, `docker_image` and `dropped_configs`.
  - `git.dirty == false`.
- **Chain:** sha256(baseline parquet) equals the committed surrogate's `inputs.hash` and the D6 pinned
  literal.

The extraction is run with **native PowerShell command lines pinned in task 39**. They are built
verbatim from the baseline metadata: `inputs.file` (Windows separators as recorded), `input_dir`,
`docker_image`, and `--run-metadata-name run_metadata.json` for coarse only. An identical `csv_sha256`
is the strongest guard against the `prelim_sweep_fine_runs_pr91_snapshot_20260918` trap; the frozen raw
shas are a second tripwire. The synthetic tests use throwaway repos and mutation-test every check.

`verify_moment_reextraction.py`: its zero-offset control compares against the **negated** baseline (the
#109 sign). Its docstring records that the `--baseline-ref fea817a` recipe predates #109.

### D9 — Delivery, commit discipline and provenance scopes

- **Order PR1 → PR2a → PR2b → PR3**, each off `main` after its predecessor merges. Shared files
  (CHANGELOG, tasks.md check-offs) then never conflict semantically. If a branch must absorb `main`
  after its recorded commits are pushed, merge `main`; never rebase.
- **Never push a red head.** The push units are:
  - **PR2b:** tasks 32–37 (code, green), tasks 38–41 (local; 38–40 red), and the PR-number commit
    after `gh pr create`. Tasks 32–41 are pushed together; the head is task 41.
  - **PR3:** tasks 43–50 (local, red until 50), then the PR-number commit.
- **Scopes:**
  - *Extraction scope* (PR2b): `dataset.py`, `normalization.py`, `constants.py`, `geometry_guard.py`,
    `sidecar.py`, `force_surrogate/__init__.py`, `scripts/extract_forces.py`, `benchmarks/metadata.py`
    and `uv.lock`. It is frozen from task 37, and nothing in it changes afterwards: the pending phrases
    live only in `docs/`.
  - *Surrogate* and *figure* scopes (PR3), as in #110 D8.
  - *PR2a figure scope*: see D5.
  - A non-empty scope diff after its data commit means regenerate.
- **Recorded commits are immutable once recorded, even while unpushed.** Fixes go on top. Before every
  push, run `git merge-base --is-ancestor <recorded git.commit> HEAD`:
  - PR2b: both corpus `run_metadata.json`;
  - PR3: both surrogate and both figure records.

  Pushed commits stay resolvable via `refs/pull/<n>/head`.
- **One blob per binary path**, checked with `git rev-list --objects origin/main..HEAD -- <paths>`. A
  fresh reviewer checks code, captions and wording **before** rendering. PR3 renders figures **after**
  its surrogate data commit, so each figure's recorded commit contains its inputs.
- **`sweep_provenance.json`** (coarse) `downstream_artifacts_regenerated_from`:
  - PR2b rewrites `re_extraction` and PR3 `retrain`.
  - #108's record moves into a `history` list, as with the fine corpus's `supersession_history`
    (asserted at `tests/test_full_corpus_deck.py:363-370`).
  - `docker_image_digest` is kept, because `_cfd_digests` reads it.
  - Until the PR exists, the stage records `pull_request: null`, which the test accepts. The
    post-`gh pr create` commit changes the JSON and the test literal together.
- **CHANGELOG:** one entry per PR, numbers from committed JSON.
- **Closing keywords:** none in any commit message. Only PR3's hand-written squash body carries
  "Closes #109."; #19 is closed by hand after PR1.
- **Preconditions:**
  - **PR2b:** `Z:` mounted; all 27 `IB_Particle_1.csv` per corpus present under the baseline
    `input_dir`; all 27 coarse `run_metadata.json` anchors present (`--run-metadata-name` fails closed).
  - **Every data commit:** `git diff --exit-code <merge-base> -- uv.lock`.

## Risks

- **G3 may fail through an unlucky draw** (≈ 9 % family-wise at most). The decision path is in D7.
- **`Z:` availability** blocks only PR2b.
- **Prose drift.** Every quoted number comes from a reproducibility test or committed JSON; a fresh
  reviewer checks each artifact and docs commit.
- **Surrogate `docker_image` records the CFD image** (data lineage, test-enforced precedent), while
  training ran in WSL. This is unchanged here, and the README says so.
- **Consumers of the IB force.** The corpus and surrogate carry `ib_w`. The solver's free-body balance
  would add `ρ_f·SumU`, but for this wing that term is a grid-dependent slab quantity, never evaluated
  by the solver for prescribed motion. A flight-dynamics consumer should therefore treat `ib_w` as the
  aerodynamic force, pending the follow-up issue. The corpus does not carry `SumU`. The section and the
  Stage-2 sentence say this.
