# Stage 2 spec draft (moves into `specs/force-surrogate/spec.md` in PR 2)

This file is not a spec delta. It is the text PR 2 adds to the delta, in the same commits as the
code, so the effective spec is never ahead of `main` (`design.md` D1). It is here so the whole plan
can be reviewed and approved now. Each MODIFIED entry below is copied into the delta in PR 2 with
the requirement's **full** current text, then the changes listed here.

## ADDED (full text in PR 2)

1. **The training beat of a corpus is its final requested beat.**
   - `settling.training_wingbeat(manifest)` SHALL return `n_wingbeats − 1`. The corpus guards and
     the acceptance gate SHALL use it.
   - The dataset extractor SHALL keep writing every beat.
   - Scenarios:
     - On both 2-beat corpora, `wingbeat == training_wingbeat` selects exactly the rows
       `wingbeat >= 1` selects.
     - A 6-beat manifest returns 5.
2. **Settling acceptance of every configuration.**
   - For a manifest with `n_wingbeats ≥ MIN_BEATS`, the post-run gate SHALL apply the
     decision rule's truncated test (a) to every configuration.
   - It SHALL fail when the complete-beat count differs from `n_wingbeats`.
   - It SHALL write per-config values and the result to `cluster_run.settling`.
   - For `n_wingbeats < MIN_BEATS`, decided from the manifest, it SHALL record `not_applicable`.
   - Scenarios:
     - One configuration with `T = 0.013` in CF_z fails the corpus and is named.
     - A 6-beat manifest whose runs have 2 complete beats fails; it is not `not_applicable`.
     - A synthetic 2-beat corpus records `not_applicable`.
3. **Field capture at fixed phases with beat-boundary checkpoints.**
   - `generate_sweep(frames_per_beat=, checkpoints_per_beat=)` SHALL write
     `amr.plot_per = 1/(frames_per_beat · f*)` and `amr.check_per = 1/(checkpoints_per_beat · f*)`,
     and set `amr.plot_int` and `amr.check_int` to `-1`.
   - The manifest SHALL record both per config.
   - Without these arguments the output SHALL be byte-identical to today's.
   - Scenarios:
     - `f*` 0.85 / 1.00 / 1.15 give `plot_per` 0.0588235… / 0.05 / 0.0434782… and `check_per`
       1/f*.
     - With the arguments omitted, both 2-beat corpora regenerate byte-identically.
     - In a simulated 8-beat `f* = 0.85` time series, applying AMReX's crossing rule puts frame
       `k` of every beat within one step of phase `k/20`.
4. **Storage manifest.**
   - `storage_manifest.json` SHALL list per configuration: the run directory, its bytes, the
     plotfile and checkpoint steps present, and the SHA-256 of the force CSV and `run.log`.
   - A check SHALL compare it with the steps the crossing rule implies from that run's time
     column.
   - Scenarios: a missing step, an unexpected step and a missing run directory are each reported
     by configuration.
5. **Supersession writer.**
   - `append_supersession_entry(path, entry)` SHALL append to `supersession_history`, creating
     the list if absent.
   - Required fields are `superseded`, `reason` and `pr`; `cluster_workflows` and `note` are
     optional. Other keys stay unchanged.
   - An incomplete entry SHALL raise without writing the file. An identical entry is a no-op.
   - Scenarios: preserve, reject, idempotent.

## MODIFIED (full current text plus these changes, in PR 2)

- **"Run duration scaled to whole wingbeats"**
  - Adds the drivers' `--n-wingbeats` and the overwrite refusal.
  - Adds three scenarios:
    - N = 6 gives `max_step` 14118 / 12000 / 10435.
    - A driver refuses `--n-wingbeats 6` into a 2-beat directory, with no file changed (checked by
      a tree hash).
    - Omitting the flag reproduces the 2-beat corpora.
- **"An overridden parallelism … auto-scales the deadline"** (renamed "The submitted deadline is
  computed from the manifest's step counts")
  - **BREAKING:** the deadline is now always computed unless `--active-deadline-seconds` is given.
  - The formula is the step-based one in D9, with rates from `cluster_sizing.json`; a missing
    file is an error.
  - Zero configs is an error (was 14400 s).
  - Worked examples: 50400 s (3 × 3600 steps, p = 1) and 25200 s (p = 10⁶, was 18000 s).
  - The interpreter-fallback and corpus-mismatch scenarios are kept.
- **"Argo sweep-submission deadline is overridable without mutating the committed workflow"**
  - Removes "when both flags are omitted the committed file is submitted unpatched".
  - Corrects 86400 s / 24 h to the committed 98280 s, documented as the direct-`argo submit`
    fallback.
- **"retryStrategy backoff can cover the full configured retry limit"**
  - The per-attempt cost is `max(max_step) · s_max` of the submitted manifest.
  - `maxDuration` is set at submission, or is a static `"105h"` with a test that every committed
    manifest fits.
- **The workflow requirement that the committed deadline is at least the formula**
  - Replaced by: `full` always patches a computed deadline. The YAML value is the fallback for
    direct `argo submit` only.
- **The smoke workflow requirement**
  - `max-step` comes from the manifest entry for `SMOKE_CONFIG_NAME`. An environment value that
    disagrees with it is an error.
- **"Post-run acceptance gate"**
  - Adds the settling check.
  - The symmetry ratio is taken over the final requested beat.
  - `plot_per > 0` counts as field capture for CC-F1.
- **"Committed corpora are guarded by cluster-free reconciliation tests"**
  - The symmetry ratio is taken over the final requested beat.
  - Explains the new registry entries and `has_per_config_metadata = True` for the settled
    coarse corpus.
- **The trainer requirement ("converged beat (`wingbeat ≥ 1`)")**
  - Adds: the trainer SHALL raise `ValueError` for a dataset whose maximum `wingbeat` exceeds 1,
    naming the follow-up issue, until the trainer selects `training_wingbeat`.
  - Scenario: a 6-beat synthetic dataset is refused, and no rows are pooled.
