# Settling-metric fixtures (E0b coarse 6-beat runs)

Known-answer data for `tests/test_settling_known_answers.py` (OpenSpec change
`add-settled-beat-corpus`, task 1.2).

## Source

Exploration branch `explore-surrogate-experiments` (pushed, never merged), at commit `0f95eb2`,
study E0b: local 6-beat runs on the coarse grid (64×32×64). Each run used the coarse corpus deck
with `max_step` and `stop_time` raised to 6 beats. The image was
`ghcr.io/talmolab/mosquito-cfd@sha256:07625ce41bef8dae5983afddf5a3d09a3fb7706cb29292d19a479600967b24d3`,
on an RTX A5000.

| fixture | source path (in that branch) | source blob |
|---|---|---|
| `e0b_s45_f100_p45_6beat.parquet` | `experiments/e0b_long_run/outputs/long_run.parquet` | `f232bcafcb984bb790e81fb934aebf073ef3c2b3` |
| `e0b_s45_f100_p30_6beat.parquet` | `experiments/e0b_long_run/outputs_s45_f100_p30_fields/long_run.parquet` | `ef8f74aa1b7c0b381ff05d8bbb96a75b34fa002c` |
| `e0b_s45_f100_p45_beat_convergence.csv` | `experiments/e0b_long_run/outputs/beat_convergence.parquet` | `8c7361a692d173a5ff370801070a8e1f4bc7fab0` |
| `e0b_s45_f100_p30_beat_convergence.csv` | `experiments/e0b_long_run/outputs_s45_f100_p30_fields/beat_convergence.parquet` | `d15835b85ad7192679922c01c7062f2e52a57692` |

- **Parquet files:** only the columns the metric needs are kept: `config_name, time, phase,
  wingbeat, frequency_fstar, CF_x … CF_mz`.
- **CSV files:** E0b's own per-beat table, columns `beat, target, diff_from_previous_over_peak,
  diff_from_last_over_peak`. E0b computed these on a 256-point phase grid, with a `phase ≥ 0.05`
  mask on the differences and beat 6's peak over all 256 points.
- **Provenance caveat:** the source run records say `git_dirty: true`. These fixtures are
  reference data for the metric, not corpus data.

## SHA-256

```
63c8f0a100118509fe69d6b19e96f24503b1066f62a2bd932801c63af8677a83  e0b_s45_f100_p30_6beat.parquet
bbe7259525bb5055163b03f963719b6308ffc46e8b50b39b083e94c6ede63634  e0b_s45_f100_p30_beat_convergence.csv
aab87db223c85f088aa1e40d35cf1bd3904de8e1f185a2ec9d80b2df300e6041  e0b_s45_f100_p45_6beat.parquet
ac8e651494da56c6c43d676f7d096319781bcca68e76ab3f86a5a5e73bbeba21  e0b_s45_f100_p45_beat_convergence.csv
```
