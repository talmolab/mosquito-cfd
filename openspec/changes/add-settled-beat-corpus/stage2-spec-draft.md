# Stage 2 spec draft (moves into `specs/force-surrogate/spec.md` in PR 2)

**This file is not a spec delta.** It holds the text PR 2 adds to the delta, in the same commits as
the code, so the effective spec is never ahead of `main` (`design.md` D1). It is here so the whole
plan can be reviewed and approved now. Each MODIFIED entry is copied into the delta in PR 2 with
the requirement's **full** current text, then changed as listed. Headers are the exact live
`### Requirement:` names.

## ADDED (full text in PR 2)

1. **The training beat of a corpus is its final requested beat.**
   - `settling.training_wingbeat(manifest)` SHALL return `n_wingbeats − 1`. The corpus guards and
     the acceptance gate SHALL use it. The extractor SHALL keep writing every beat.
   - Scenarios:
     - on both 2-beat corpora, `wingbeat == training_wingbeat` selects exactly the rows
       `wingbeat >= 1` selects;
     - a 6-beat manifest returns 5.
2. **Settling acceptance of every configuration.**
   - For `n_wingbeats ≥ MIN_BEATS`, the post-run gate SHALL apply the truncated test (a) of the
     decision rule to every configuration.
   - It SHALL fail when the complete-beat count differs from `n_wingbeats`.
   - It SHALL write per-config values and the result to `cluster_run.settling`.
   - For `n_wingbeats < MIN_BEATS`, decided from the manifest, it SHALL record `not_applicable`.
   - Scenarios:
     - one configuration with CF_z `T = 0.013` fails the corpus and is named;
     - a 6-beat manifest whose runs have 2 complete beats fails, rather than being
       `not_applicable`;
     - a synthetic 2-beat corpus records `not_applicable`.
3. **Field capture at fixed phases with beat-boundary checkpoints.**
   - `generate_sweep(frames_per_beat=, checkpoints_per_beat=)` SHALL write
     `amr.plot_per = 1/(frames_per_beat · f*)` and `amr.check_per = 1/(checkpoints_per_beat · f*)`,
     and set `amr.plot_int` and `amr.check_int` to `-1`.
   - The manifest SHALL record both per config. Provenance `field_capture` SHALL record
     `frames_per_beat` and `checkpoints_per_beat`, with a rationale that names the time-triggered
     output.
   - Without these arguments the output SHALL be byte-identical to today's.
   - Scenarios:
     - `f*` 0.85 / 1.00 / 1.15 give `plot_per` 0.0588235… / 0.05 / 0.0434782… and
       `check_per = 1/f*`;
     - with the arguments omitted, both 2-beat corpora regenerate byte-identically;
     - applying AMReX's crossing rule to step end times `(iStep + 1)·dt` at `f* = 0.85` over
       8 beats puts frame `k` of every beat within one step of phase `k/20`.
4. **Storage manifest.**
   - `storage_manifest.json` SHALL list, per configuration: the run directory, its bytes, the
     plotfile and checkpoint steps present, and the SHA-256 of the force CSV and `run.log`.
   - A check SHALL compare it with the steps that the crossing rule implies from that run's time
     column.
   - Scenarios: a missing step, an unexpected step and a missing run directory are each reported,
     by configuration.
5. **Supersession writer.**
   - `append_supersession_entry(path, entry)` SHALL append to `supersession_history`, creating the
     list if absent.
   - Required fields: `superseded`, `reason`, `pr`. Optional: `cluster_workflows`, `note`.
   - Other keys SHALL be unchanged. An incomplete entry SHALL raise without writing the file. An
     identical entry SHALL be a no-op.
   - Scenarios: preserve, reject, idempotent.
6. **Cluster sizing rates are committed and recomputable.**
   - Each submittable corpus directory SHALL carry `cluster_sizing.json`
     (`seconds_per_step_mean`, `seconds_per_step_max`, `source`).
   - A test SHALL recompute it from the files `source` names.
   - Scenario: the `prelim_sweep_fine` and `settled_sweep_fine` rates recompute to 2.321
     (step-weighted) and 3.302.

## MODIFIED (full current text plus these changes, in PR 2)

- **"Run duration scaled to whole wingbeats"**
  - Adds the drivers' `--n-wingbeats`, `--frames-per-beat`, `--checkpoints-per-beat` and the
    overwrite refusal.
  - Scenarios:
    - N = 6 gives 14118 / 12000 / 10435;
    - refusing to write into a directory with a different `n_wingbeats` leaves the tree hash
      unchanged;
    - a manifest without `n_wingbeats` raises;
    - omitting the flags reproduces the 2-beat corpora.
- **"Reproducible sweep manifest with units sidecar"**
  - Adds `plot_per`, `check_per` and `n_wingbeats` per corpus to the manifest, and the
    `field_capture` fields of ADDED 3.
- **"Surrogate input and target construction"**
  - Adds: `filter_converged_beat` and `build_phase_only_baseline` SHALL raise `ValueError` for a
    frame whose maximum `wingbeat` exceeds 1, naming the follow-up issue, until they select
    `training_wingbeat`.
  - Scenario: a 6-beat synthetic frame is refused by both, and no rows are pooled.
- **"Cluster-side Argo orchestration of the corpus"**
  - Smoke `max-step` comes from the manifest entry for `SMOKE_CONFIG_NAME`, and an environment
    value that disagrees with it is an error.
  - The committed `98280` is documented as the fallback for a direct `argo submit`; the
    "committed deadline ≥ formula" scenario is replaced by "`full` always patches a computed
    deadline".
- **"Argo sweep-submission parallelism is overridable without mutating the committed workflow"**
  - **BREAKING:** "submitted unpatched when `--parallelism` is omitted" becomes "the deadline is
    still patched; parallelism is left as committed".
- **"Argo sweep-submission provisions the NFS workspace before submitting"**
  - "`smoke` never requires the manifest" becomes "`smoke` reads the manifest for `max-step`".
- **"Argo sweep-submission deadline is overridable without mutating the committed workflow"**
  - Removes "when both flags are omitted the committed file is submitted unpatched".
  - Corrects 86400 s / 24 h to the committed 98280 s, as the direct-submit fallback.
- **"An overridden parallelism without an explicit deadline auto-scales the deadline instead of silently reusing a stale default"**
  - **BREAKING:** the deadline is always computed unless `--active-deadline-seconds` is given. It
    uses the step-based formula of `design.md` D9 and `cluster_sizing.json`; a missing file is an
    error naming the explicit alternative.
  - Zero configs is an error (was 14400 s).
  - Worked examples, with rates 2.321 / 3.302: 50400 s (3 configs × 3600 steps, `p = 1`) and
    25200 s (`p = 10⁶`, was 18000 s).
  - The interpreter-fallback and corpus-mismatch scenarios are kept.
  - A scenario covers `examples/prelim_sweep` (no `cluster_sizing.json`): `full` fails unless
    `--active-deadline-seconds` is given.
- **"retryStrategy backoff can cover the full configured retry limit"**
  - `maxDuration` is the committed `"105h"`: 6 attempts of N = 8 fine `s35_f085_p30` at 3.302 s/step
    plus 62 min of backoff. A test fails when any committed manifest with a `cluster_sizing.json`
    needs more.
- **"Post-run acceptance gate blocks dataset construction on an unverified corpus"**
  - Adds the settling check of ADDED 2.
  - The symmetry ratio is taken over the final requested beat.
  - CC-F1 is keyed on `field_capture.frames_per_beat > 0` or `plot_int > 0`.
- **"Committed corpora are guarded by cluster-free reconciliation tests"**
  - The symmetry ratio is taken over the final requested beat.
  - Adds the new registry entries, with `has_per_config_metadata = True` for `settled_sweep`.
