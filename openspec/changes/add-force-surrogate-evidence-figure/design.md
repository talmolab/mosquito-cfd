# Design — Force-surrogate evidence figure (PR6)

## Context

PR5 committed `examples/prelim_sweep/surrogate/holdout_predictions.parquet` (12,535 rows × the 6
held-out configs; columns `config_name, time, phase, wingbeat, CF_{x,y,z,mx,my,mz}_{true,pred}`) and
`metrics.json` (per-target aggregate, `per_config`, the phase-honest `config_resolved`, and an
`inference` block). PR6 is the **figure only**: a local matplotlib script that reads those committed
artifacts and emits `examples/prelim_sweep/figures/evidence_figure.png`. No solver, cluster, GPU, or
new dependency (CC-6). The decisions below are the ones the roadmap row + the user scope review
flagged as deferred or non-obvious.

## D1 — Headline CF_m axis = CF_my, named as a component (not "pitch moment")

**Decision.** The third scatter panel is **CF_my**, labeled "**aerodynamic moment (M_y component)**".
PR4 D2 / PR5 D4 deliberately deferred this pick to PR6.

**Why CF_my (the data).** The evidence figure must demonstrate the **kinematics→force map**, not the
shared within-beat waveform. Of the three moments, only CF_my carries genuine config-to-config
signal:

| Moment | between-config spread (std of per-config means) | per-config mean range | `config_mean_r2` | `within_config_variance_fraction` |
|---|---|---|---|---|
| **CF_my** | **0.115** (≈ its full std 0.140) | **[−0.376, −0.132]** | **0.987** | 0.442 |
| CF_mx | 0.012 | ~[−0.013, 0.023] | 0.940 | 0.999 |
| CF_mz | 0.011 | ~[−0.016, 0.006] | 0.751 | 0.999 |

CF_my is a sustained, kinematics-dependent moment (`within_config_variance_fraction = 0.442`, so ≈56 %
of its variance is *between* configs); CF_mx
and CF_mz are ~99.9 % the shared phase waveform with near-zero between-config spread. Putting CF_mz
("pitch about span") in the headline would showcase a 0.75-R², waveform-dominated panel — the exact
inflation trap CC-4's caption is meant to expose.

**Why "M_y component", not "pitch moment".** The repo's coordinate convention does not match
biomechanics standard (GitHub **issue #1**: wing extends along z, stroke `Rz(φ)`, pitch `Rx(α)`), so
naming CF_my "pitch moment" would assert a biomechanical interpretation the inconsistent axes cannot
cleanly back. The figure names the **component** and the caption points at issue #1.

**Why not fix issue #1 here.** Its fix is a solver-level coordinate refactor (edit the IAMReX-fork
`WingKinematics.H`, re-orient `wing.vertex`, rewrite domain/BCs, rebuild the FP64 container, re-run
the 27-config A40 corpus + sphere/ellipsoid benchmarks, re-train the surrogate, regenerate all
artifacts). That breaks CC-6 (force-only) and misses the ~Jun-24 cutoff. Critically, moments are
**axis-invariant under a correct coordinate transform** — fixing #1 only *renames* the same physical
torque, it does not change which moment carries the signal. So the honest move is to caveat now and
leave #1 open as tracked tech-debt for the funded re-run.

**We do NOT relabel the axis inside the figure** (apply a sim→biomechanics mapping in labels only):
the issue itself flags the correct mapping as non-trivial/unverified, so asserting it in the headline
figure would be *less* honest than reporting the raw component.

## D2 — Sane–Dickinson quasi-steady: a computed reference, NOT a scatter overlay

**Decision (revised — see "Why reference instead of overlay" below).** Compute a **translational-only**
quasi-steady CF_z reference (Sane & Dickinson 2002; F_rot and F_added omitted) and report its
**overshoot factor** + RMSE in the sidecar, but **do not draw it on the scatter panels**. The original
plan (and CC-4) called for an overlay on the CF_z panel; building it revealed the overlay is
misleading at the coarse grid (next paragraph), so it was demoted to a reference number.

**Formula (dimensionless lift coefficient).** Using the validated flapping-wing kinematics
(`φ(t)=φ_amp·sin(ωt)`, `α(t)=α_amp·cos(ωt)`, `ω=2π·f*`; `examples/flapping_wing/generate_all_figures.py:euler_angles`):

```
U(t)/U_tip   = cos(2π · phase)                      # taken from the parquet `phase` column
α_eff(t)     = α_amp · |cos(2π · phase)|            # hovering quasi-steady AoA, 0 at reversal, α_amp at mid-stroke
C_L(α)       = 0.225 + 1.58 · sin(2.13·α_rad − 0.1257)   # Dickinson, Lehmann & Sane 1999 Robofly fit
#   ↑ canonical fit is `2.13·α_deg − 7.2°`; this is the *same* expression in radians: since radians() is
#     linear, radians(2.13·α_deg) = 2.13·α_rad exactly (the per-degree slope is preserved, NOT rescaled),
#     and radians(7.2) = 0.1257. Verified equal to the degree form to ~1e-4 over α∈[0,90]°.
F_trans(t)   = q_tip · S · (U(t)/U_tip)² · C_L(α_eff(t))  # q_tip, S, U_tip from compute_force_reference (CC-3)
CF_trans(t)  = F_trans(t) / F_ref = (U(t)/U_tip)² · C_L(α_eff(t))
```

**CC-3 reuse is genuine, not algebraic-cancellation-hidden.** Although `q_tip·S` cancels between
`F_trans` and `F_ref`, the baseline is **computed through** `compute_force_reference(f_star, φ_amp,
r_tip, span, chord)` → `F_ref` and `u_tip_max`, and `F_trans` is divided by `F_ref` — the helper is
the single source for the reference quantities (CC-3), and the code path divides explicitly so the
normalization is auditable rather than pre-cancelled inline. Per-config `f*`, `φ_amp`, `α_amp` are
parsed from `config_name` (e.g. `s45_f115_p60` → φ=45°, f*=1.15, α=60°); `r_tip, span, chord` and
`dt` are **imported from `mosquito_cfd.force_surrogate.constants`** (`R_TIP, SPAN, CHORD, DT` =
3.0, 3.0, 1.0, 5e-4 — the validated geometry), **not** re-declared locally (single-source, the same
DRY discipline as CC-3). (D4's per-config rows come from the actual parquet counts, ≈`1/(f*·dt)`.)

**Why translational-only.** The translational term is the dominant, best-sourced quasi-steady
contribution and needs no extra derivatives (F_rot needs `dα/dt`, F_added needs `d|U|/dt` and an
added-mass volume). Against the cutoff, fewer terms = fewer places to be wrong. The omission is
disclosed in the reference note.

### Why reference instead of overlay? (CC-4 deviation, found during implementation)

Drawing the baseline on the CF_z scatter is **misleading at this coarse grid**, for a reason that only
became clear once it was computed against real data:

- The uncalibrated QS model predicts a peak lift coefficient ~1.6–1.8; the coarse-grid CFD `CF_z`
  peaks at only ~0.5 — an RMS overshoot of **~2.3×** (recorded as `overshoot_factor` in the sidecar).
- That gap is **dominated by the ~2.4× diffused-IB underestimate** (the coarse IAMReX CFD is biased
  *low*; `examples/flapping_wing/RESULTS.md`) plus the QS model's **tip-velocity overprediction**
  (lift integrates over the span where inboard sections move slower; tip-scaling over-weights it).
- The surrogate is trained to reproduce the **(IB-biased) coarse CFD** — which it does faithfully. So
  an overlay showing "surrogate RMSE 0.056 ≪ baseline RMSE 0.985" mostly **re-displays the IB bias**,
  not surrogate skill over the analytic model — a hollow, ~17×-looking "win." The large analytic loops
  also visually dominated the lift panel (a reviewer/PI flagged it as confusing).

**Resolution.** Keep the QS computation (it's a useful sanity number and the CC-3 reuse is genuine),
but report it as a **reference**: `overshoot_factor = rms(CF_trans)/rms(CFD-true CF_z)` + RMSE in the
sidecar, and one honest caption sentence ("an uncalibrated translational Sane–Dickinson model
overshoots the coarse-grid CFD lift ~2.3× — dominated by the ~2.4× diffused-IB underestimate plus
tip-velocity overprediction — so it is not used as a quantitative baseline at this resolution"). The
CC-4 intent (surrogate ≥ analytic model) is **not cleanly achievable** at the coarse grid because the
IB bias confounds the comparison; this is the honest call and is recorded as a deviation in the
proposal + spec. (A *fair* comparison would scale-calibrate the QS to the CFD — but that makes it a
fitted, not zero-parameter, model and is out of scope before the cutoff.)

**Why AoA = α_amp·|cos(2π·phase)|.** With the prescribed kinematics (`α=α_amp·cos(ωt)` in quadrature
with `φ=φ_amp·sin(ωt)`), this is the **symmetric-rotation** flat-plate hovering AoA: it peaks at the
pitch amplitude at mid-stroke (max velocity) and → 0 at stroke reversal, matching the validated
α_amp≈45° mid-stroke AoA. It is *a* defensible reference, **not** "the" universal hovering profile —
rotation *timing* (advanced/delayed) shifts α relative to reversal and is exactly Sane & Dickinson's
2002 point; here it is fixed by the prescribed kinematics. It is an **approximate analytic reference**,
explicitly not a tuned fit, and `(U/U_tip)²` makes the translational lift stroke-symmetric (it cannot
represent the up/down-stroke asymmetry the CFD shows) — all stated in the caption.

**Projection caveat (honest, in the caption).** The QS translational lift is defined **stroke-plane-
normal** (⟂ instantaneous velocity); the CFD `CF_z` is the **lab z** (span-normal) force. The
*normalization* is apples-to-apples (both ÷ `F_ref = q_tip·S`; `q_tip·S` cancels in `CF_trans`), but
the *projection* aligns only near mid-stroke for a horizontal stroke plane. The baseline is an
approximate bound, not a like-for-like force; the caption discloses the projection difference
alongside the omitted F_rot/F_added terms.

**Overlay style.** On the CF_z scatter panel, plot two point series against the same CFD-true x-axis:
the **surrogate** (`CF_z_pred`, primary marker) and the **Sane–Dickinson baseline** (`CF_trans`,
secondary marker, lower alpha). Both RMSEs (vs CFD-true CF_z) are annotated; the baseline scatters
farther from the 1:1 line, visually + numerically showing the surrogate wins. Scope: hovering only
(Sane & Dickinson 2002).

## D3 — Honest caption: per-axis config-resolved R² + RMSE, aggregate flagged as waveform-inflated

**Decision.** The caption headline reports, for the three figure axes, the **config-resolved** R²
(read from `metrics.json config_resolved.<coefficient>.config_mean_r2` — the per-coefficient path,
**not** a flat `config_resolved.config_mean_r2`: CF_x 0.94, CF_z 0.83, CF_my 0.99) and the per-axis
RMSE (`per_target.<coefficient>.rmse`), and states explicitly that the aggregate R²≈0.98 is ~99.9 %
the shared phase waveform and **overstates** skill — naming that CF_y's config-resolved R² is negative
(−3.61) as the concrete tell. The caption also states: coarse grid 64×32×64, ~2.4× diffused-IB force
underestimate, pipeline readiness **not** validated aerodynamics. Numbers are **read** from
`metrics.json` (not hard-coded), so the caption can never silently drift from the artifact.

A `config_mean_r2` may be the JSON `null` NaN-sentinel (the trainer emits `null` when a coefficient's
between-config variance is near zero); the caption/annotation render `null` as an explicit "n/a"
token and a negative value verbatim, never crashing or dropping it. The figure also **fails loud** if
a key it reads (`config_resolved`, `inference`, a panel coefficient's `per_target`) is absent — it
raises before writing any artifact rather than emitting a partial figure.

> The per-axis R² literals quoted throughout this design (0.94 / 0.83 / 0.99 / −3.61) are
> **illustrative of the committed PR5 artifact, not a contract** — the figure code reads them from
> `metrics.json` at generation time, so a re-train updates the figure without a doc edit.

**Two additional honesty disclosures the caption MUST carry (round-2 review):**

1. **Fitted-vs-unfitted asymmetry.** The surrogate is *fit* to sibling configs of this corpus; the
   Sane–Dickinson curve is a *zero-parameter* analytic model with no fit to any CFD data. So
   "surrogate RMSE < baseline RMSE" means the trained interpolator reproduces held-out forces
   **within the swept kinematic range** — **not** that ML is more accurate than quasi-steady theory in
   general. The baseline is present to *bound* the surrogate, not as a fair-fit competitor. The
   caption states this explicitly so the comparison cannot be read as "ML beats theory."

2. **Why only M_y among the moments.** The caption discloses that M_x and M_z are excluded because
   they are ≈99.9% the shared within-beat waveform (`within_config_variance_fraction ≈ 0.999`) with
   no between-config signal, so they cannot demonstrate a kinematics→force map — i.e. the exclusion is
   stated with its reason, not silent. (M_y carries ≈56% between-config variance.)

## D4 — Speedup annotation: headline the batched **throughput** speedup, report latency honestly too

**The >1,000× claim is a throughput claim, not a single-row-latency claim.** Round-2 review caught that
a single-row latency comparison is only ~310×, **below** 1,000× — and that dividing the per-*wingbeat*
CFD cost (144 s) by the per-*row* surrogate latency (0.232 ms) to get "620,000×" is a units error
(it implicitly sets rows-per-wingbeat = 1). The honest, RL-relevant >1,000× number is **batched
GPU throughput** (the surrogate is a pointwise kinematics→force map with no time-stepping, so all
rows evaluate in parallel; CFD must sequentially integrate) — exactly the metric the surrogate notes
call the real requirement ("GPU-batchable inference across thousands of parallel environments").

**Decision — two clearly-labeled numbers, both derived from `metrics.json` + the parquet:**

```
# Per-config CFD throughput (coarse A40), from the parquet's own per-config converged-beat row count:
rows_per_wingbeat(cfg) = ACTUAL parquet rows for cfg # 2353 / 2000 / 1738 — ≈1/(f*·dt) (the real
                                                     #   converged-beat count; differs ≤1 row from the
                                                     #   analytic value at the beat boundary), NOT a constant
cfd_rows_per_s(cfg)    = rows_per_wingbeat(cfg) / CFD_SECONDS_PER_WINGBEAT   # e.g. 2000/144 = 13.9 rows/s

# HEADLINE — batched throughput speedup (the >1,000× claim):
throughput_speedup = inference.throughput_rows_per_s / cfd_rows_per_s   # 5.17e7 / 13.9 ≈ 3.7e6×

# SECONDARY — single-row latency speedup, reported honestly (NOT >1000×):
t_cfd_per_row      = CFD_SECONDS_PER_WINGBEAT / rows_per_wingbeat(cfg)   # 144/2000 = 72 ms
latency_speedup    = t_cfd_per_row / (inference.latency_ms/1000)         # 72/0.232 ≈ 310×
```

`CFD_SECONDS_PER_WINGBEAT = 144.0` is the **coarse-grid** A40 cost (~2.4 min/wingbeat, roadmap
Hardware row) — the annotation labels the denominator "coarse-grid A40 CFD" so the speedup cannot be
read as "fast *and* validated". `rows_per_wingbeat` is **per-config** (from the parquet, recorded per
config in `evidence_figure_metrics.json`), not a single constant; the representative config (f*=1.0,
2000 rows) is named explicitly for the headline literal. **Units reconciled explicitly** (`latency_ms`
→ s); a **known-answer test pins both factors** (throughput ≈3.7e6×, latency ≈310×) so a units mix-up
cannot pass.

**The throughput headline MUST disclose it is batch-size-driven (round-3 skeptic).** Arithmetically
`throughput_speedup = latency_speedup × batch_size` (3.7e6× ≈ 310× × 12,535) — ~12,000× of the
headline is simply the **batch size** (the whole 12,535-row holdout set, from the `inference.basis`
string), *not* a per-evaluation advantage, and the CFD denominator is an **inherently sequential**
timestep rate (a time integration cannot be batched) while the surrogate is a pointwise map that can.
So the >1,000× annotation SHALL be labeled verbatim as **"batched GPU throughput, N=12,535 parallel
evaluations, vs sequential coarse-grid A40 CFD"**, and the **conservative per-evaluation latency
speedup (~310×)** SHALL be stated alongside as the like-for-like floor. `evidence_figure_metrics.json`
records both factors, both denominators (and that the CFD rate is sequential), the **batch size**, the
implied **parallelism factor** (≈12,009×), and the per-config rows-per-wingbeat — so the headline is
fully decomposable and the "speedup of *what*?" question is answered in the artifact. This keeps the
roadmap's >1,000× deliverable (the RL-relevant batched-throughput metric the surrogate notes call
"the real requirement") **honest** rather than a batch-size sleight of hand.

## D5 — Committed artifacts + provenance (CC-1)

`examples/prelim_sweep/figures/`:
- `evidence_figure.png` — ≥200 dpi (`savefig(dpi=200)`). The dpi is asserted by **spying on the
  `savefig` call** (the `dpi` kwarg ≥ 200), not by re-reading the PNG's `pHYs` chunk (which is
  matplotlib-version-sensitive and flaky).
- `evidence_figure_metrics.json` — per-axis surrogate RMSE, Sane–Dickinson baseline RMSE (CF_z), the
  `config_mean_r2` annotated, and the speedup derivation inputs. Every number printed on the figure is
  sourced here.
- `run_metadata.json` — via `capture_surrogate_run_metadata` (CC-1): git commit, a pinned container
  **digest** (`validate_image_digest` rejects a mutable tag), seeds, the **inputs hash** of the
  consumed parquet + metrics.json, and a **caller-supplied** timestamp (never wall-clock baked into
  logic). Reuses the PR1/PR5 provenance helper unchanged. Mechanism note: the helper takes a *single*
  `inputs_file` (it computes `inputs.hash` from it) — pass the **predictions parquet** as `inputs_file`
  and record the **metrics.json** SHA256 (and the seeds) under the helper's `extra=` dict, so both
  consumed inputs are hashed and auditable from one metadata file.

Determinism: the figure has no RNG; given the same committed inputs it regenerates identical numbers
(matplotlib raster bytes are not asserted bit-for-bit — only the data/annotations are).

## D6 — Cluster-free, two-tier-free TDD (CC-2)

All tests are pure-CPU, no RunAI/GPU/plotfiles/`train` group. The module forces the **Agg backend**
(`matplotlib.use("Agg")` before importing `pyplot`, matching the existing `examples/*/generate_*.py`
scripts) so the structure tests and `savefig` run headless in CI. Committed JSON sidecars are written
**LF-newline UTF-8** (matching `write_units_sidecar`) so the Windows-authored artifacts do not churn
against Linux CI. Fixtures: a **tiny synthetic predictions parquet** (2 configs × a few timesteps,
analytically known CF_z/CF_my; **no `split` column**, matching the committed parquet) and a **tiny
metrics dict** (with `config_resolved.<c>.config_mean_r2`, including a `null`-sentinel and a negative
case). Tests assert: (a) the Sane–Dickinson formula on a known `(phase, α_amp)` array;
(b) config-name parsing → (φ, f*, α); (c) the baseline normalizes through `compute_force_reference`
(CC-3) — patched/​spied to prove the helper is the single source; (d) per-panel RMSE/R² match the
metrics the figure reads; (e) the three artifacts write + re-load with the right schema; (f) the
digest guard rejects a mutable tag; (g) the force-only scope guard. Plot-rendering tests assert
**figure structure** (3 axes, the CF_z panel carries 2 labeled series, titles/annotation text
present) via the Matplotlib object model — not pixels. `build_figure(...)` returns a
`matplotlib.figure.Figure`; "labeled series" means entries returned by
`ax.get_legend_handles_labels()`, so the implementation adds a per-axis legend on the CF_z panel and
the tests key off the legend handles/labels (the `generate_all_figures.py` pattern).

## D7 — Force-only scope guard (CC-6)

The module consumes **only** `holdout_predictions.parquet` + `metrics.json` (+ module constants for
geometry). It never reads a plotfile/field path, builds an encoder/latent state, or touches RL. A
test asserts the public entrypoint neither accepts nor requires a field/plotfile argument.

## References

- Sane & Dickinson (2002). *J. Exp. Biol.* 205:1087 — quasi-steady decomposition, hovering-scoped.
- Dickinson, Lehmann & Sane (1999). *Science* 284:1954 — Robofly `C_L(α)` / `C_D(α)` empirical fits.
- Bomphrey et al. (2017). *Nature* 544:92 — Aedes kinematics anchoring.
- GitHub issue #1 — repo axis-convention inconsistency (left open). GitHub issue #24 — this PR.
