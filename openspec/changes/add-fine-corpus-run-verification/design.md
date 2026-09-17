# Design

## D1. Why `ns.cfl` is not a no-op under `ns.fixed_dt` (the root mechanism)

The decks carry both `ns.fixed_dt = 0.0005` and `ns.cfl = 0.3`, and it is natural to assume
`fixed_dt` simply wins. It does not. Verified against `IAMReX-fork/Source/`:

- `NavierStokesBase.cpp:1503` — `estTimeStep()` short-circuits with
  `if (fixed_dt > 0.0) … return factor*fixed_dt;` (guard at line 1503, return at line 1517),
  returning **above** the
  `estdt = estdt * cfl` at line 1604. This is what makes `ns.cfl` *look* inert.
- `NavierStokes.cpp:2471` — the diffused-IB advance calls `Real dt_test = predict_velocity(dt);`
- `NavierStokesBase.cpp:4603` / `4710` — `predict_velocity` computes
  `tempdt = cflmax==0 ? change_max : min(change_max, cfl/cflmax)` and returns `dt*tempdt`.
- `NavierStokesBase.cpp:1114` — `computeNewDt` then takes
  `dt_min[i] = min(dt_min[i], estTimeStep())`, where `dt_min[i]` arrives pre-populated with what
  `advance()` returned.

So the realized step is `dt = min(fixed_dt, dt_prev · min(change_max, cfl/cflmax))`. **`fixed_dt` is
a ceiling; `ns.cfl` is an independent limiter that can push below it.** With `fixed_dt > 0` the
`change_max` block in `computeNewDt` is skipped (line 1117), so when the CFL branch binds the
recurrence collapses to `dt = cfl·h/u_max`, independent of `dt_prev` — which is what lets us invert
the measured `dt_min` for the true `u_max` (D2).

**This exact assumption is the documented origin of #92.** The archived
`2026-08-03-add-wing-fine-grid-convergence` design §D6 states: *"with `ns.fixed_dt = 5e-4` the solver
uses the fixed timestep regardless of the CFL criterion (it's an inputs cap, not an enforcement)."*
That parenthetical is false. The same section also computed *"At Δx = 0.03125 and max |u| ≈ 28, CFL ≈
0.45 … CFL = 0.45 is borderline"* — the number was right; only the belief that the limiter would not
intervene was wrong.

Why it bites at 256³ and not 64³: the domain is `8 × 4 × 8` for both, so `h` falls from 0.125 to
0.03125. At `|u|max ≈ 20` the CFL ceiling is ~1.9e-3 coarse (≈4× headroom over nominal 5e-4) but
~4.6e-4 fine — below nominal. The corrected root hinge compounded it by lengthening the moment arm.

**Landmine to lint for:** `NavierStokes.cpp:2589` has `dt_test = dt;` inside `if (prescribed_vel)`,
in the *same* function as the 2471 call. If it fired it would disable the CFL limiter entirely and
invert this whole analysis. It does not: `ns.prescribed_vel` defaults to 0
(`NavierStokesBase.cpp:228`), its body reads `prob.blob_*` (the PVF blob test, unrelated to IB wing
motion), it is a different variable from `particle_inputs.do_prescribed_motion`, and no fine deck
sets it. A deck lint asserting `ns.prescribed_vel` is absent-or-0 — and likewise `ns.num_steps`,
which can silently *lower* the effective `max_step` (`main.cpp:94–100`) — is cheap insurance.

## D2. Why raise `ns.cfl` rather than re-size `max_step` per config

Two routes close #92: give each config more steps so it reaches `stop_time` despite a reduced dt, or
raise `ns.cfl` so the nominal dt binds and nothing is reduced. We take the second.

**Sizing per config cannot be done predictively.** An analytic `dt_cfl = cfl·h/U_tip` with
`U_tip = 2πf*φR` predicts only 3 configs bind (3 more marginal) against **15 measured**. It omits the
wake velocity and the pitch-rotation contribution — note the single worst config varies with *pitch*
amplitude, which that model does not contain at all. Sizing from measured `realized_dt` instead works
(it is empirical), but carries three costs: a per-config manifest schema addition, a corpus where 9
configs ran under one sizing rule and 18 under another, and — decisively — it leaves 15 configs
running at a **non-uniform, config-dependent dt** that correlates with stroke amplitude and
frequency, i.e. with the surrogate's own input features. That is the same structural defect class as
#92, an order of magnitude smaller.

**What `ns.cfl` must be.** Inverting `dt_min = cfl·h/u_max` on the measured minima gives the true
peak velocity and hence the required `cfl` per config:

| config | measured `dt_min` | implied `u_max` | required `cfl` at dt=5e-4 |
|---|---|---|---|
| s55_f115_p30 | 3.0607e-4 | 30.63 | **0.490** |
| s55_f115_p45 | 3.1620e-4 | 29.65 | 0.474 |
| s55_f100_p30 | 3.5958e-4 | 26.07 | 0.417 |
| s45_f115_p60 | 4.0209e-4 | 23.32 | 0.373 |

`ns.cfl = 0.5` leaves only **2%** margin over the worst requirement; **0.6 leaves 22%**. We take 0.6.

Note `u_max = 30.63` inferred from `dt_min` exceeds the 24.2 measured from a plotfile by the CC-F1
check, because `predict_velocity` takes `norm0` over ghost cells. **The CC-F1 plotfile check
therefore under-reports the CFL-relevant velocity** and must not be used to size `cfl`.

## D3. Why `realized_dt` must not be summarized by its median

The obvious summary statistic is wrong in a way that would reproduce #93 inside the fix for #93.
Measured over interior steps on the affected corpus:

| config | `dt` **median** | `dt` min | % steps below nominal | cycles |
|---|---|---|---|---|
| s55_f115_p30 | **5.0000e-4** | 3.0607e-4 | 40.7% | 1.8290 |
| s55_f115_p60 | **5.0000e-4** | 3.1621e-4 | 48.8% | 1.8403 |
| s35_f085_p30 (healthy) | 5.0000e-4 | 5.0000e-4 | 0% | 1.9996 |

**The median interior `dt` is exactly 5.0000e-4 for all 27 configs** — min equals max across the
whole corpus — because even the worst config keeps 59% of its steps at the ceiling. A median-based
`stability` reports `stable_at_5e-4` for every config including the worst.

`min` and `frac_below_nominal` are the discriminating statistics. Conversely, `min` over *interior*
steps does **not** false-positive: for all 12 healthy fine configs and all 27 coarse configs,
`min == max == 5.000e-4` exactly.

**Excluding only the final step is correct, and verified empirically rather than argued.** Across
all healthy configs every interior `dt` is exactly nominal, so plotfile writes do not shorten a step
(the fine corpus runs `amr.plot_int = 100` and still shows uniform interior dt), checkpoint writes do
not, and there is no initial ramp (the first step is exactly 5e-4, so `ns.init_shrink` is not in
play). The only legitimately short step is the final one, clamped by `stop_time`
(`NavierStokesBase.cpp:1168–1169`; termination itself is `main.cpp:122–124`, which honours `stop_time`
and `max_step` as independent conditions).

**Precision:** the force CSV writes `time` at six significant figures, which at `t ≈ 2` quantizes a
differenced `dt` to ~±2% of nominal — the committed data contains `dt = 5.004e-4`, *above* the
ceiling, which is impossible. A local run of the same deck and image gives exactly `5.000000e-4` in
`run.log`, confirming the artifact is the CSV writer's rounding. So `realized_dt` is parsed from
`run.log`'s per-step `DT`, which `metadata_capture` already opens for the arena figure. Caveat for
the implementation: `run.log` emits roughly two `dt` lines per step, so it is not 1:1 and needs
deduplication before use.

## D4. The local stability probe, and what it establishes

Raising `ns.cfl` removes a guardrail, so it was tested before committing. Both cases ran on the dev
A5000 against **the exact corpus image digest** (`a03151af`, whose baked
`IAMREX_COMMIT=f93dc794…` matches `docker/build-args.env`), using the worst config `s55_f115_p30`,
the two decks differing in `ns.cfl` alone.

**Setup validation — bit-exact.** The `cfl = 0.3` control reproduced the cluster corpus over its
first 400 steps with `max |time difference| = 0`, identical `dt_min`/`dt_max`, identical 195
CFL-reduced steps, and `Fx`/`Fz` differing by **0.000e+00** at correlation exactly `1.00000000`.
(Incidentally this demonstrates the CFD is bit-reproducible across GPU models, A40 → A5000.)

**Stability over the probed window — passes.** At `cfl = 0.6`: `dt` held at exactly `5.000000e-04`
for all 199 intervals (zero CFL-reduced steps, so `fixed_dt` binds), no NaN or Inf, and `|u|max`
*decayed* from 25.5 in the first quarter to 17.3 in the last, peaking at 28.98 — an instantaneous
CFL of 0.464 over the window actually run.

**Accuracy — passes.** Against the control on a common time grid, the `Fz` deviation is confined to
the impulsive start:

| window | phase | max deviation |
|---|---|---|
| t 0.00–0.02 | 0.000–0.023 | 24.2% |
| t 0.02–0.04 | 0.023–0.046 | **0.38%** |
| t 0.08–0.10 | 0.092–0.115 | **0.03%** |

Agreement is 0.03–0.38% outside the first 2% of the window and improving. The 24% spike is the
`1/dt`-divergent impulsive-start artifact (D5), which the trainer's `wingbeat >= 1` filter discards.

**What this does not establish, and why task 7.2 is mandatory, not optional.** `s55_f115_p30`'s
period is `T = 1/f* ≈ 0.870`; the 199-step probe covers `199 × 5e-4 ≈ 0.0995` — **11.4% of one
period, 22.9% of the way to the first stroke reversal at `t = T/2`**. It never reaches a reversal,
let alone the 4 that occur over the intended 2-wingbeat run. Flapping-wing aerodynamics has a
well-documented mechanism — wake-capture and rotational effects at stroke reversal — by which peak
local fluid velocity can occur there rather than only during the impulsive start. The probe cannot
rule this out, because it never gets there. The "August borderline at 0.45" concern is addressed for
the startup transient only; it is not yet addressed for the settled beat.

This is a real gap, not a formality: raising `ns.cfl` removes a guardrail, and the resulting corpus
costs ~65 GPU-h. What *is* already covered: the `cfl >= 0.490` **requirement** in D2 is derived by
inverting the measured `dt_min` over the **entire** `cfl = 0.3` run (all ~3478 steps, spanning both
wingbeats and every reversal), so the sizing target already reflects whatever peak velocity occurred
anywhere in the real physics, including at reversal. What is *not* yet established is whether the
solver remains **stable** at `cfl = 0.6` all the way through — a different question from whether
0.490 is the right number.

A stability failure at reversal would only appear past step ~870 (the first half-stroke), which the
200-step probe never reaches — only a full config run can confirm it. Task 7.2 (one full config at
`cfl = 0.6`, ~2.4 GPU-h, run and gated **before** the other 26 are submitted) closes this gap for
~4% of the total re-run cost. It is a precondition on the fan-out, not an optional nice-to-have.

## D5. Why `keep="last"` and not "drop all `t=0` rows"

`NavierStokes.cpp:1311` is `for (int iter = 0; iter < init_iter; iter++)`, each iteration advancing
at the same `strt_time`, so the CSV carries `1 + init_iter` rows at `iStep = 0`. Confirmed on fresh
local output: `rows at iStep==0` is exactly 3 for `init_iter = 2`. The first is all-zero forces, the
rest are the `post_init_press` iterations.

The physics argument for dropping *all* `t=0` rows is correct — with fluid at rest the IB force is
`≈ U_wing/dt`, which scales as `1/dt` and has no limit — but it applies to **any** `t=0` row,
including the converged one, and therefore to **both** corpora equally. Dropping all of them would
either make the two corpora structurally different or, applied uniformly, rebuild the coarse parquet
and break its frozen-corpus guarantee for a corpus with no defect.

`drop_duplicates(subset="iStep", keep="last")` instead restores `len(df) == max_step` for the fine
corpus, is a **provable no-op** on the coarse corpus, and keeps both identical in shape.
`keep="first"` would place a spurious zero-force sample at `phase = 0` in every config.

**Latent trap:** the coarse no-op is often attributed to the *manifest* field `init_iter = None`. The
actual cause is that the coarse **deck** carries `ns.init_iter = 0` explicitly
(`examples/prelim_sweep/inputs/inputs.3d.s35_f085_p30:22`), and `NavierStokesBase::init_iter`
**defaults to 2** (`NavierStokesBase.cpp:111`). A manifest `init_iter = None` that failed to emit the
deck line would silently produce duplicates. A test pins the deck line, not just the manifest field.

The residual "a `t=0` row is unphysical at all" concern is pre-existing, shared by both corpora, and
already masked downstream by the trainer's `wingbeat >= 1` filter. Out of scope; recorded so it is
not lost.

## D6. The gate is the backstop, and it must not certify itself

Sizing and `cfl` choices can be wrong for a *new* corpus, where no measured `dt` exists. The durable
protection is that a defective run cannot reach a committed parquet, so the gate runs **after**
`generate_run_metadata.py` and **before** `extract_forces.py` — both #92's truncation and #94's bad
rows enter at the extract step.

**The gate must recompute at least one quantity from raw output.** As otherwise specified it reads
`realized_dt`/`reached_stop_time` back from the same JSON that `generate_run_metadata.py` wrote; if
that derivation is wrong — and per D3 the obvious derivation *is* wrong — the gate certifies the
corpus.

**Physical check must be normalized, and it is a secondary backstop, not the primary detector.** The
settled-beat mean `CF_x` is *not* ≈0: it scales with pitch amplitude and reaches −0.0289 on the
healthy coarse corpus, against a truncated minimum of +0.0387 — a usable window of only **1.33×**,
tighter than the coarse corpus's own worst value. Normalizing by the settled-beat peak,
`|mean CF_x| / max|CF_x|`, gives non-truncated `[−0.0091, +0.0001]` versus truncated
`[+0.0150, +0.1648]` — roughly **150×** separation at the extremes, and dimensionally a proper
symmetry ratio (truncation shrinks `max|CF_x|` along with the numerator, so the ratio amplifies the
deviation rather than risking a masked cancellation).

**The 150× figure describes the worst-vs-mildest pair, not the whole affected population.** Five of
the fifteen `interior_dt_below_nominal` configs (`frac_below_nominal` 0.45–1.0%) have normalized
ratios of −0.0023 to −0.0071 — statistically indistinguishable from the healthy band, and the sign
only flips once `frac_below_nominal` exceeds ~6.8%. So the normalized ratio detects **severe**
truncation reliably; it is not a robust detector of mild CFL-limiting on its own. The **hard, exact**
gate is `interior_dt_below_nominal` — a full-precision boolean that separates all 15 affected
configs from the 12 healthy ones exactly, with no threshold to tune. The normalized ratio is
defense-in-depth against a case where the observed-dt derivation itself is wrong (the self-
certification concern above), not the primary mechanism.

Similarly `|CF_x| < 5` as a tripwire has only 20% headroom over the coarse corpus's own 4.015,
so it is stated as provisional and re-derived against the fine corpus.

**A `cycles_completed` scalar tolerance is not viable and is not used as a gate.** The healthy
shortfall band is `[3.75e-4, 7.25e-4]` and the affected band starts at `7.50e-4`, so a threshold must
land in a 3.3% window — about 2× the CSV's own 1e-5 representation noise. `cycles_completed` is
recorded as a diagnostic; the hard gate is `interior_dt_below_nominal`, which separates exactly.

**Mid-sweep and post-run semantics differ and must not be conflated.** `/submit-cluster-sweep`
Step 4 evaluates a *partial* corpus where most configs legitimately have not reached `stop_time`
because they are still running; post-run the same signal is a defect. The same fields are used with
different pass criteria, and a partial record does not satisfy the post-run gate.

**Cheap in-run detection.** The failure signature appears in the first wingbeat — 40.7% of
`s55_f115_p30`'s steps are CFL-reduced — and `run.log` prints `DT` every step. Checking the first
completed pod at the existing Step 4 human gate, ~2 h into a 22 h sweep, converts a 64 GPU-h loss
into ~2 GPU-h.

## D7. Deck-generation constraints that bound the implementation

**The `ns.cfl` override must be opt-in and must not touch the base deck.** Two tests call
`generate_sweep` with no overrides and byte-compare against the frozen committed **coarse** decks
(`test_committed_sweep_matches_regeneration`,
`test_generate_sweep_defaults_are_byte_identical_to_before`), and a third pins the fine base deck to
differ from the coarse base deck in `amr.n_cell` **only**
(`test_fine_pilot_deck_matches_coarse_base_except_n_cell`). Editing `ns.cfl` in either base deck
breaks the third; changing `generate_sweep`'s defaults breaks the first two and would regenerate a
corpus with no physical reason to change. Threading `ns.cfl` as an optional targeted key, exactly as
`ns.init_iter` already is, satisfies all three.

`render_inputs` preserves the text around a rewritten value and writes deterministic numerics, so
rewriting a key with an **unchanged** value produces byte-identical output — which is what makes an
opt-in key safe.

**The manifest must record the override.** `test_committed_fine_corpus_matches_regeneration` replays
generation arguments *out of the committed artifacts* (`seed`, `n_holdout`, `timestamp`, `plot_int`,
`init_iter`) to byte-compare all 27 decks. A `cfl` override that is not recorded cannot be replayed,
so the test would have to be weakened rather than updated.

## D8. Deadline and retry interact, in the wrong direction

Measured from the 27 committed `wall_time_s` values: total work **64.58 GPU-h**, mean 2.392 h/config,
max 2.860 h, 2.121 s/step. LPT makespan at `parallelism: 3` is **21.54 h**, not the 24.4 h quoted
earlier — 24.4 h was the *observed makespan including the preemption and manual resubmit*
(21.54 + 2.86 = 24.40, which is where that figure came from). So the committed 24 h deadline is
insufficient because of **preemption-retry headroom**, not work volume. That distinction sets how
much headroom is needed.

Fixing #90 (`retryPolicy: "Always"`) makes preemption retries actually fire. Using one consistent
derivation (LPT makespan 21.54 h, longest-config retry cost 2.86 h): a 26 h deadline absorbs only
~1.5 retries of the longest config; two preemptions on the critical path reach
`21.54 + 2 × 2.86 = 27.26 h` and re-trigger the #95 kill. The deadline is therefore sized for **two**
retries — **27.3 h**, the single literal that goes into the committed YAML and the "committed ≥
formula" test, so an implementer is not left choosing between two different roundings of the same
scenario.

**Constraint linking the two tasks, and a follow-up the fix does not close.** The auto-scale formula
is `ceil(n × PER_CONFIG_HOURS / p + RETRY_MARGIN_HOURS)`. At `n=27, p=3, PER_CONFIG_HOURS=2.4` it
gives 26 h. Re-deriving `PER_CONFIG_HOURS` from the `pzdhl` measurement (2.392 h) keeps the formula
at 26 h only while the constant stays ≤ 2.444; rounding it to 2.5 pushes the formula to 27 h and
would make the new "committed ≥ formula" test fail against a 26 h committed value. Both must move
together (task 4.7).

**`RETRY_MARGIN_HOURS = 4h` is left unchanged, and by this same design's two-retry standard that is
under-provisioned for the *conditional* auto-scale path.** At `p=3` it buys only ~1.4 retries, not
two, for anyone who explicitly passes `--parallelism` without `--active-deadline-seconds` — a milder
recurrence of #95 through a code path this change does not touch. Raising it to match the two-retry
standard is out of scope for this change (the committed-default fix is what matters for the actual
re-run, since it does not go through the conditional path); recorded as a follow-up alongside making
auto-scale itself unconditional, below.

The auto-scale path itself is left **conditional** (it fires only when `--parallelism` is given
without `--active-deadline-seconds`). Making it unconditional would break
`test_omitting_both_deadline_and_parallelism_is_a_true_noop` and its spec scenario — a behaviour
change beyond this change's purpose. Recorded as a follow-up alongside `RETRY_MARGIN_HOURS` above.

## D9. Sequencing against PR #91

PR #91 is open and carries the corpus, the `cluster_run` provenance block, and the `project.md`
edits; at this change's base commit `dataset.parquet` does not exist and the 27 committed metadata
files are stale `vb8t5` artifacts from August.

Order: this change lands on `main` with **no corpus** → the full 27 configs are re-run at
`ns.cfl = 0.6` → metadata regenerated → parquet rebuilt → PR #91 updated and merged last.

Because the `ns.cfl` change alters every deck, **all 27 configs are re-run** (~65 GPU-h / 2.7
GPU-days) rather than a subset. This is the deliberate trade for a uniform corpus: it removes the
per-config override mechanism, the mixed-vintage provenance, the non-uniform dt, and the
`rows == max_step` contradiction that a partial re-run would have created.

PR #91's branch must be synced onto post-merge `main` **before** any regeneration, because its
existing parquet was built by the pre-dedup extractor and is invalid — #91 needs full artifact
regeneration, not a rebase.

**Verified preconditions:** the raw `IB_Particle_1.csv`, plotfiles and checkpoints for all 27 configs
still exist on cluster NFS. CC-F1 was run manually and **passes** (`s35_f085_p30/plt01000`:
`x_velocity ∈ [-2.36, 10.39]`; `s55_f115_p60/plt01000`: `[-8.31, 24.22]`), so the existing
field-capture output is valid — B4's concern was that it was never *recorded*, not that it failed.

**Irreversibility to guard:** those NFS CSVs are the only remaining copy of the 18 healthy configs'
raw output (gitignored, and `main` has no parquet). Since the re-run writes into the same shared
workspace, and this repo has prior form with an NFS provisioning gap and a `provision()` data-loss
bug, the CSVs are snapshotted before the re-run touches anything. Everything else in the plan is
recoverable by re-running; this is not.

## D10. Known test impact

Beyond D7's three byte-identity tests:

| Test | Why it moves |
|---|---|
| `test_force_surrogate_dataset.py::test_one_row_per_config_and_timestep` | asserts `dropped == []` and `N × T` rows; dedup changes it |
| `test_force_surrogate_dataset.py::test_committed_units_contract_matches_module` | a new column is auto-"measured" unless added to `_NON_MEASURED` |
| `test_metadata_capture.py::test_assemble_metadata_produces_normalized_schema` | **exact dict equality** on the whole `timing` block |
| `test_metadata_capture.py::test_stability_derived_from_fixed_dt_alone` | asserts the deck-only semantics this change reverses; its *name* states the defect |
| `test_metadata_capture.py::test_pilot_fixture_matches_real_capture_…_shape` | `set(real.keys()) == set(fixture.keys())` on pod-side capture |
| `test_metadata_capture.py::test_read_final_time_from_csv_uses_last_row` | unpacks a **2-tuple**; preserve the arity or update every caller |
| `test_force_surrogate_sweep.py::test_render_inputs_minimal_diff` | asserts `differing == TARGET_KEYS` exactly against a no-override call — `TARGET_KEYS` is the always-rewritten set and does **not** gain `ns.cfl`, exactly as it does not contain `ns.init_iter` today; `ns.cfl` gets its own override-battery tests instead (mirroring `test_render_inputs_accepts_init_iter_override` et al.) |
| `test_force_surrogate_sweep.py::test_generate_sweep_duration_per_config` | pins that `f*` alone determines `(max_step, stop_time)` — still true under this approach |
| `test_argo_workflows.py:145` | `"activeDeadlineSeconds: 86400" in text` |
| `test_argo_workflows.py:55` | `retryPolicy: "OnFailure" in text` |
| `test_full_corpus_deck.py::test_committed_fine_corpus_matches_regeneration` | replays args from provenance; must replay `cfl` |
| `test_full_corpus_deck.py::test_fine_corpus_git_commit_names_a_capable_commit` | probes for `("--plot-int", "--init-iter")`; must grow |
| `test_full_corpus_deck.py::test_fine_corpus_provenance_flags_superseded_runs` | **exact list equality**; becomes a supersession history |
| `test_fine_pilot_deck.py::_STABILITY_TOKENS` | closed stability vocabulary; gains the `cfl_limited_*` values |
| `test_fine_pilot_deck.py::test_pilot_run_metadata_dt_reduced_correlates_with_fixed_dt` | pins the pilot's *deck-level* `dt_reduced`; the new observed field is named `interior_dt_below_nominal` to avoid the collision |
| `test_submit_workflow_active_deadline.py` (hardcoded `43200`/`25200`) | survive the 2.4 → 2.392 change only by `ceil` coincidence; the `# ceil(3 * 2.4 …)` comments go stale |

Six tests pin that `assemble_run_metadata` **raises** on status ≠ completed, deck-hash mismatch, and
`pod_rows != timesteps`. Keep raising by default; the row-count cross-check moves to the **raw** count
so it does not start failing on healthy `init_iter` runs.

`_FROZEN_RAW_FORCE_SHA` hashes the **coarse** parquet's force columns; D5's asserted no-op is what
keeps it valid.

Confirmed *not* a problem: every existing fixture CSV already carries `iStep` as its first column, so
adding it to `_REQUIRED_CSV_COLUMNS` breaks nothing.
