# Settling check (Stage 1 of `add-settled-beat-corpus`, #192)

Eight-wingbeat runs of three configurations on both grids. They decide how many wingbeats the
regenerated force-surrogate corpora need.

The question, the metric, the criterion, the controls and the decision rule are in
[`PREREGISTRATION.md`](PREREGISTRATION.md). That file is fixed before any run, so this README
does not restate it.

## Files

| path | what | written by |
|---|---|---|
| `PREREGISTRATION.md` | the criterion (single narrative home; hash-pinned by every run record) | hand, before the runs |
| `generate_decks.py` | generates every deck and both manifests below (hash-pinned) | hand |
| `settling_manifest.json` | runs, controls, deck hashes, declared keys, images | `generate_decks.py` |
| `<grid>/inputs/inputs.3d.<config>` | the six 8-beat decks | `generate_decks.py` |
| `<grid>/controls/inputs.3d.c1_s55_f115_p30` | the two 400-step C1 control decks | `generate_decks.py` |
| `<grid>/sweep_manifest.json` | the three configs in the sweep-manifest schema, for `scripts/extract_forces.py` | `generate_decks.py` |
| `records/<run>.json` | one record per run and control (schema below) | `scripts/record_settling_run.py` |
| `<grid>/dataset.parquet` (+ units, run metadata) | the extracted forces of each grid's three long runs | `scripts/extract_forces.py` |
| `settling_report.json` | every force-derived number, the controls and the decision | `scripts/check_settling.py` |
| `settling_figure.png` (+ `_metrics.json`, `_run_metadata.json`) | step change per beat, one panel per coefficient | `scripts/make_settling_figure.py` |
| `DECISION.md` | the rule applied, `N*`, the field change, the mean-lift drift, the domain caveat, the downstream reruns | hand, from the report |
| `deviations.json` | any edit to a hash-pinned file after the runs started | hand, only if needed |

Raw runs are not in git. Directories named `runs/` here are ignored.

## Where the raw data lives

There is **one copy only**, on the cluster share:
`Z:\users\eberrigan\mosquito-cfd\examples\settling_check_2026-11\<run>\`.

Each run is written on gh-04, copied there with `scp` straight from gh-04, and verified by file
count and force-CSV SHA-256. It is never staged on the workstation's `C:`.

Each run directory holds:
- `IB_Particle_1.csv` and `run.log`;
- the deck and `wing.vertex`;
- `command.txt` and `hardware.json`;
- the plotfiles (20 per beat);
- the checkpoints (one per beat; not usable for restarts until #205 is fixed).

## Procedure

Each launch needs the user's explicit go-ahead.

1. **On gh-04.** From a clean checkout of the `main` commit that holds this directory:
   - pull both images by digest;
   - record their `com.mosquito-cfd.iamrex-commit` labels;
   - confirm the GPU is idle and the disk has space.
2. **C1.** Run the two control decks (400 steps each), then record them:
   ```bash
   uv run python scripts/record_settling_run.py --name fine_c1_s55_f115_p30 \
       --run-dir <run dir> --start-commit "$(git rev-parse HEAD)" \
       --git-dirty "$( [ -z "$(git status --porcelain)" ] && echo false || echo true )" \
       --iamrex-commit <label> --command "$(cat <run dir>/command.txt)" \
       --hardware-json <run dir>/hardware.json
   ```
   C1 also measures seconds per step. Report it and the projected wall time before asking for
   the long runs.
3. **Long runs.** Run the six long runs one at a time, and record each the same way.
   - For the fine runs, add `--field-change`.
   - The record runs C3 and C4.
   - A failed control stops the work.
4. **Extract** each grid's dataset:
   ```bash
   uv run python scripts/extract_forces.py --manifest examples/settling_check/<grid>/sweep_manifest.json \
       --input-dir <runs of that grid> --out examples/settling_check/<grid>/dataset.parquet \
       --units examples/settling_check/<grid>/dataset.units.json \
       --metadata examples/settling_check/<grid>/run_metadata.json \
       --docker-digest <grid image> --timestamp <ISO-8601>
   ```
5. **Report and figure:**
   ```bash
   uv run python scripts/check_settling.py --git-commit "$(git rev-parse HEAD)"
   uv run python scripts/make_settling_figure.py --report examples/settling_check/settling_report.json \
       --out-dir examples/settling_check --git-commit "$(git rev-parse HEAD)" --timestamp <ISO-8601>
   ```
   `check_settling.py` exits non-zero unless every declared record and control is present, has
   passed, and every run has data.
6. **Decide.** Write `DECISION.md` from the report.

## Schemas

### `settling_manifest.json`

Top-level keys:
- `n_wingbeats` (8), `frames_per_beat` (20), `checkpoints_per_beat` (1);
- `images` (per grid), `preregistration`;
- `runs`: the long runs;
- `controls`: the C1 decks.

Each entry has:
- `name`, `grid`, `config`, `kind` (`long` or `C1`);
- `deck` and `deck_sha256`;
- `source_deck` and `source_deck_sha256` (the committed corpus deck);
- `declared_keys` (the exact set of keys that differ from the source deck);
- `image`, `max_step`, `stop_time`.

Long runs also have `n_wingbeats` and `controls` (`["C3", "C4"]`). C1 entries also have
`reference` (the committed dataset compared against).

### `records/<run>.json`

| key | meaning |
|---|---|
| `run`, `grid`, `config`, `kind` | identity (from the settling manifest) |
| `start_commit`, `git_dirty` | the `main` commit the run started from, and the checkout state (must be `false`) |
| `file_sha256` | SHA-256 of `PREREGISTRATION.md`, `generate_decks.py` (both gated) and `settling.py` (reported) |
| `image`, `iamrex_commit` | the digest-pinned image and its IAMReX label |
| `command`, `hardware` | the exact container command, and the GPU and host |
| `wall_time_s`, `steps`, `seconds_per_step` | timing (from `run.log`'s run-time line and the de-duplicated CSV) |
| `force_csv_sha256`, `run_log_sha256` | hashes of the raw files kept on the share |
| `controls` | `C1`, or `C3` and `C4`: each has `passed`, plus the comparison counts and failures (C1, C3) or the realized-timestep summary (C4) |
| `field_change` | optional (fine long runs): `beats` → per-frame median and fraction above 0.1 of the vector-difference change against the last beat; `plotfile_header_sha256` |

### `settling_report.json`

Top-level keys:
- `status`: `complete`, `controls_incomplete`, `control_failed` or `data_incomplete`, with lists
  `missing`, `failed` and `data_missing`;
- `constants`, `preregistration_sha256`, `git_commit`;
- `settling_py_sha256` and `settling_py_matches_records`;
- `controls`, `runs`, `decision`.

Each run in `runs` has:
- `b_last`, `incomplete_beats`, `n_star`, `passes`;
- `contracting`, `max_noise`, `noise_target`, `binding_beat`, `binding_target`;
- `mean_cf_z` and `field_change`;
- `targets`, which for each coefficient holds `steps`, `steps_max_abs`, `distances`,
  `distances_max_abs`, `estimate`, `jitter`, `noise_floor`, `tail`, `rho`, `contracting`,
  `ratios` and `skipped`.

Beats are string keys. An infinite value (`tail` of a non-contracting target) is written as
`null`.
