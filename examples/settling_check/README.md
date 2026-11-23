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
`Z:\users\eberrigan\mosquito-cfd\examples\settling_check_2026-11\<grid>\<config>\` for the long
runs, and `…\<grid>\c1_<config>\` for the C1 controls.

- Each run directory is named by its configuration so that `scripts/extract_forces.py`, which
  reads `<input-dir>/<config>/IB_Particle_1.csv`, works with `--input-dir …\<grid>` unchanged.
- Each run is written on gh-04 in the same layout, copied with `scp` straight from gh-04, and
  verified by file count and force-CSV SHA-256. It is never staged on the workstation's `C:`.

Each run directory holds:
- `IB_Particle_1.csv` and `run.log`;
- the deck (named as in the settling manifest's `deck`) and `wing.vertex`;
- `launch.json`, `command.txt` and `hardware.json`;
- the plotfiles (20 per beat);
- the checkpoints (one per beat; not usable for restarts until #205 is fixed).

## Procedure

Each launch needs the user's explicit go-ahead. One run per GPU at a time: every deck reserves a
12 GiB AMReX arena (`amrex.the_arena_init_size` is in bytes), coarse decks included.

1. **Prepare gh-04.** Use a clean checkout of the `main` commit that holds this directory, then:
   - pull both images by digest;
   - confirm the GPU is idle;
   - confirm the disk has room (a fine 8-beat run writes about 160 plotfiles).
2. **Before each run starts**, from the checkout:
   ```bash
   uv run python scripts/record_settling_run.py launch --run-dir <run dir>
   ```
   Then copy the deck into the run directory and start the container. Write the exact
   `docker run …` command (naming the pinned image digest) to `command.txt` and the GPU and host
   to `hardware.json`.
3. **C1.** Run the two control decks (400 steps each), then record each:
   ```bash
   uv run python scripts/record_settling_run.py record --name fine_c1_s55_f115_p30 --run-dir <run dir>
   ```
   The record step does five things:
   - derives the git provenance itself (HEAD still the launch commit, an ancestor of
     `origin/main`, clean at launch and now, gated files unchanged);
   - reads the image's IAMReX label with `docker image inspect`;
   - checks the deck hash, the step count and that the command names the pinned image;
   - runs C1;
   - refuses to write an invalid record.

   C1 also measures seconds per step. Report it and the projected wall time before asking for
   the long runs.
4. **Long runs.** Run the six long runs one at a time, and record each the same way.
   - For the fine runs, add `--field-change` (needs `yt`; it runs after validation).
   - The record runs C3 and C4.
   - A failed control stops the work.
5. **Extract** each grid's dataset:
   ```bash
   uv run python scripts/extract_forces.py --manifest examples/settling_check/<grid>/sweep_manifest.json \
       --input-dir <the grid's run folder> --out examples/settling_check/<grid>/dataset.parquet \
       --units examples/settling_check/<grid>/dataset.units.json \
       --metadata examples/settling_check/<grid>/run_metadata.json \
       --docker-digest <grid image> --timestamp <ISO-8601>
   ```
   The report checks that each dataset was extracted from the CSV its record hashes
   (`run_metadata.json` → `extraction_inputs.csv_sha256`).
6. **Report and figure:**
   ```bash
   uv run python scripts/check_settling.py --git-commit "$(git rev-parse HEAD)"
   uv run python scripts/make_settling_figure.py --report examples/settling_check/settling_report.json \
       --out-dir examples/settling_check --git-commit "$(git rev-parse HEAD)" --timestamp <ISO-8601>
   ```
   `check_settling.py` exits non-zero unless the status is `complete`:
   - every declared record is present and valid, and every control passed;
   - the precedence check passes;
   - every run has its declared beats and was extracted from its recorded CSV.
7. **Decide.** Write `DECISION.md` from the report.

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
| `provenance` | derived from git: `start_commit` (from `launch.json`), `head_commit`, `upstream_ref`, `ancestor_of_upstream`, `dirty_at_launch`, `dirty_at_record`, `file_sha256` (each gated file at the start commit), `working_tree_matches_commit` |
| `file_sha256` | the gated files' hashes (`PREREGISTRATION.md`, `generate_decks.py`, `settling.py`), as in `provenance` |
| `image`, `iamrex_commit` | the manifest's digest-pinned image, and its IAMReX label from `docker image inspect` |
| `command`, `deck_sha256` | the exact container command (must name the image), and the hash of the deck in the run directory (must be the committed deck) |
| `hardware` | the GPU and host |
| `wall_time_s`, `steps`, `seconds_per_step` | timing: the single run-time line in `run.log`, and the de-duplicated CSV row count (must equal the deck's `max_step`) |
| `force_csv_sha256`, `run_log_sha256` | hashes of the raw files kept on the share |
| `controls` | `C1`, or `C3` and `C4`: each has a boolean `passed`, plus the comparison counts and failures (C1, C3) or the realized-timestep summary (C4) |
| `field_change` | optional (fine long runs): `beats` → per-frame median, and fraction above `FIELD_CHANGE_THRESHOLD`, of the vector-difference change against the last beat; `plotfile_header_sha256` (each plotfile's `Header`) |

### `settling_report.json`

Top-level keys:
- `status`: `complete`, `controls_incomplete`, `control_failed`, `precedence_failed` or
  `data_incomplete`, with lists `missing`, `failed`, `precedence` and `data_missing`;
- `field_change_missing`: fine runs without a field change (reported only);
- `constants`, `preregistration_sha256`, `git_commit`;
- `settling_py_sha256` and `settling_py_matches_records`;
- `controls`, `runs`, `decision`.

Each run in `runs` has:
- `b_last`, `incomplete_beats`, `n_star`, `passes`;
- `contracting`, `max_noise`, `noise_target`, `binding_beat`, `binding_target`;
- `mean_cf_z`, `mean_cf_z_drift` (change from the previous beat) and `field_change`;
- `targets`, which for each coefficient holds `steps`, `steps_max_abs`, `distances`,
  `distances_max_abs`, `estimate`, `jitter`, `noise_floor`, `tail`, `rho`, `contracting`,
  `ratios` and `skipped`.

Beats are string keys. An infinite value (`tail` of a non-contracting target) is written as
`null`. The decision's `beat` and `target` describe the same beat: for `N*`, the beat below `N*`
that failed and its worst coefficient.
