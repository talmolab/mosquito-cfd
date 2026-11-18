# Draft issue: the fine corpus's manifest copy on the cluster share lists 26 configs, not 27

**Status:** filed 2026-11-17 as #167. Found during the surrogate exploration (2026-11-16); nothing changed.

## What

`Z:\users\eberrigan\mosquito-cfd\examples\prelim_sweep_fine\sweep_manifest.json` (the copy the Argo
workflow read) has 26 configs. `s55_f115_p30` is absent. The committed
`examples/prelim_sweep_fine/sweep_manifest.json` has all 27, and the run directory
`runs/s55_f115_p30/` exists on the share with a full set of plotfiles.

## Evidence

- `FieldCorpus(<Z: corpus root>).config_ids()` returns 26 names; `steps("s55_f115_p30")` raises
  "is not in manifest".
- Addressed through the committed manifest, all 18 second-beat plotfiles of `s55_f115_p30` pass the
  same checks as every other config (`ns.cfl = 0.6`, `ns.fixed_dt = 0.0005`, `256 128 256`,
  IAMReX `f93dc794`, header time = step x 5e-4).

## Likely cause (not verified)

A manifest trimmed for a resubmission that covered only the configs still missing, left in place
afterwards.

## Why it matters

Any tool pointed at the corpus root on the share silently sees 26 configs. The field experiments
here use the committed manifest for that reason.

## Suggested next step

Replace the copy on the share with the committed manifest, or have corpus tooling compare the two
and warn.

## Related observation (not a defect)

The last plotfile of each run is not always at step x dt: for the f* = 0.85 group, `plt04706` has
header time 2.352941 (the deck's `stop_time`), not 4706 x 5e-4 = 2.353, because the solver shortens
its final step. A check that assumes time = step x dt must exempt the final plotfile.
