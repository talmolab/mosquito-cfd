"""Committed coarse surrogate and evidence figure are tied to their inputs and to a real commit.

fix-moment-reference-hinge PR3 retrains ``examples/prelim_sweep/surrogate/`` and regenerates the
evidence figure. These tests reconcile the committed artifacts against the files they were
produced from, unconditionally -- no state passes with a mismatch:

- every ``<target>_true`` in the holdout predictions equals ``dataset.parquet``, for all six
  targets;
- the surrogate's ``run_metadata.json`` names the dataset by sha256;
- the figure's ``run_metadata.json`` names the holdout predictions and ``metrics.json`` by sha256;
- every regenerated record carries a real git commit from a clean tree, not the
  ``git.error`` the pre-#78 surrogate record holds;
- the committed seed-variation record agrees with the committed surrogate, and the README's
  5-seed table is that record's min/max.

The recorded commits do not survive the squash-merge as ancestors of ``main``; they stay
resolvable via ``refs/pull/<n>/head``. Branch names are deliberately not pinned, so a later
regeneration (#110, #114, #125) does not have to edit this file.
"""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.evidence_figure import format_metric
from mosquito_cfd.force_surrogate.train import (
    TARGET_COLUMNS,
    build_phase_only_baseline,
    compute_baseline_skill,
    filter_converged_beat,
    make_config_splits,
)

REPO = Path(__file__).resolve().parents[1]
COARSE = REPO / "examples" / "prelim_sweep"
SURROGATE = COARSE / "surrogate"
FIGURES = COARSE / "figures"
_HEX40 = re.compile(r"[0-9a-f]{40}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "record",
    [
        SURROGATE / "run_metadata.json",
        FIGURES / "run_metadata.json",
        COARSE / "run_metadata.json",
        REPO / "examples" / "prelim_sweep_fine" / "run_metadata.json",
    ],
    ids=["surrogate", "figure", "coarse-corpus", "fine-corpus"],
)
def test_regenerated_records_carry_a_clean_git_commit(record):
    """Each record names a full commit, a feature branch, and a clean tree.

    A ``git.error`` record, or the docker-build-arg fallback shape ``{commit, source}`` (which
    has a 40-hex commit but no branch or dirty flag), fails here. The branch must be a real
    branch name -- not missing, empty, ``main`` (artifacts are produced on a PR branch) or a
    detached ``HEAD`` -- but which one is not pinned.
    """
    git = _meta(record)["git"]
    assert "error" not in git, git
    assert _HEX40.fullmatch(git.get("commit", "")), git
    assert isinstance(git.get("branch"), str), git
    assert git["branch"].strip() not in ("", "main", "HEAD"), git
    assert git.get("dirty") is False, git


def test_surrogate_holdout_targets_equal_the_committed_dataset():
    """Every holdout ``<target>_true``, for all six targets, is the committed dataset's value.

    A surrogate trained on any other corpus -- including the pre-#108 parquet, which differs only
    in CF_mx/CF_mz -- fails, naming the target.
    """
    holdout = pd.read_parquet(SURROGATE / "holdout_predictions.parquet")
    dataset = pd.read_parquet(
        COARSE / "dataset.parquet", columns=["config_name", "time", *TARGET_COLUMNS]
    )
    joined = holdout.merge(
        dataset, on=["config_name", "time"], how="left", validate="one_to_one"
    )
    assert len(joined) == len(holdout)
    for c in TARGET_COLUMNS:
        assert joined[c].notna().all(), f"{c}: holdout rows absent from dataset.parquet"
        mismatched = int((joined[f"{c}_true"] != joined[c]).sum())
        assert mismatched == 0, (
            f"{c}: {mismatched} holdout rows differ from dataset.parquet"
        )


def test_surrogate_metadata_names_the_committed_dataset():
    """The surrogate's provenance hashes the exact committed dataset it was trained on."""
    inputs = _meta(SURROGATE / "run_metadata.json").get("inputs")
    assert inputs, "surrogate run_metadata.json records no training dataset"
    assert Path(inputs["file"].replace("\\", "/")).name == "dataset.parquet", inputs
    assert inputs["hash"] == _sha256(COARSE / "dataset.parquet")


def test_figure_metadata_names_the_committed_surrogate_outputs():
    """The figure's provenance hashes the committed predictions and metrics it was drawn from."""
    meta = _meta(FIGURES / "run_metadata.json")
    assert meta["inputs"]["hash"] == _sha256(SURROGATE / "holdout_predictions.parquet")
    assert meta["metrics_json_sha256"] == _sha256(SURROGATE / "metrics.json")


def _seed_record() -> dict:
    return _meta(SURROGATE / "seed_variation.json")


def test_seed_variation_record_matches_the_committed_surrogate():
    """The committed seed-variation record's corrected seed-1234 run *is* the committed surrogate.

    Its six config_mean_r2 equal metrics.json exactly and its dataset hash is the committed
    dataset's. (Its commit is not compared with the surrogate's: a retrain at a later commit,
    such as the seed-sweep regeneration, must not break this.) Both datasets cover seeds 1234-1238, from
    clean trees, at one epoch count. (The pre-#108 entries cannot be reconciled in CI: the old
    metrics.json is only in history, which CI's depth-1 checkout does not fetch.)
    """
    record = _seed_record()
    targets = list(TARGET_COLUMNS)
    assert record["targets"] == targets
    old, new = record["datasets"]["pre_108"], record["datasets"]["hinge_referenced"]
    assert old["dataset_sha256"] != new["dataset_sha256"]
    for ds in (old, new):
        assert sorted(r["seed"] for r in ds["runs"]) == [1234, 1235, 1236, 1237, 1238]
        for r in ds["runs"]:
            assert r["dataset_sha256"] == ds["dataset_sha256"], r["seed"]
            assert r["git_dirty"] is False and _HEX40.fullmatch(r["git_commit"]), r[
                "seed"
            ]
            assert r["epochs"] == 2000 and set(r["config_mean_r2"]) == set(targets)

    assert new["dataset_sha256"] == _sha256(COARSE / "dataset.parquet")
    (committed,) = [r for r in new["runs"] if r["seed"] == 1234]
    metrics = _meta(SURROGATE / "metrics.json")
    assert committed["config_mean_r2"] == {
        c: metrics["config_resolved"][c]["config_mean_r2"] for c in targets
    }


_TABLE_ROW = re.compile(
    r"^\s*\|\s*`(CF_\w+)`\s*\|\s*(\S+) to (\S+)\s*\|\s*(\S+) to (\S+)\s*\|\s*$", re.M
)


def test_readme_seed_table_is_the_seed_record():
    """The README's 5-seed table is the committed record's per-target min/max (2 dp), for both
    datasets, and "negative for four of the five seeds" is counted, not asserted."""
    readme = (COARSE / "README.md").read_text(encoding="utf-8").replace("−", "-")
    rows = {m[0]: m[1:] for m in _TABLE_ROW.findall(readme)}
    assert set(rows) == set(TARGET_COLUMNS), sorted(rows)
    record = _seed_record()["datasets"]
    for c, (new_lo, new_hi, old_lo, old_hi) in rows.items():
        for ds, lo, hi in (
            ("hinge_referenced", new_lo, new_hi),
            ("pre_108", old_lo, old_hi),
        ):
            values = [r["config_mean_r2"][c] for r in record[ds]["runs"]]
            assert (float(lo), float(hi)) == (
                round(min(values), 2),
                round(max(values), 2),
            ), (
                c,
                ds,
            )
    negative_cf_x = sum(
        r["config_mean_r2"]["CF_x"] < 0 for r in record["hinge_referenced"]["runs"]
    )
    if "for four of the five seeds" in readme:
        assert negative_cf_x == 4


# --- Seed sweep and phase-only baseline skill (replace-config-r2-with-baseline-skill) -----


def _dataset() -> pd.DataFrame:
    return filter_converged_beat(pd.read_parquet(COARSE / "dataset.parquet"))


def test_committed_seed_sweep_is_internally_consistent():
    """The committed sweep agrees with itself, the run record and the dataset.

    ``seed_sweep.seeds`` is the primary seed then run_metadata's sweep seeds; the primary run
    entry's statistics equal the top-level blocks; each run's ``val_configs`` is the split
    recomputed from the dataset for that seed. Not a GPU-bitwise pin (design D5): nothing here
    asserts a sweep seed's metrics against a hand record.
    """
    metrics = _meta(SURROGATE / "metrics.json")
    seeds = _meta(SURROGATE / "run_metadata.json")["seeds"]
    sweep = metrics["seed_sweep"]
    assert sweep["primary_seed"] == seeds["global"] == 1234
    assert sweep["seeds"] == [seeds["global"], *seeds["sweep"]]
    assert [r["seed"] for r in sweep["runs"]] == sweep["seeds"]
    assert metrics["reproducibility"]["seeds"]["global"] == sweep["primary_seed"]

    primary = sweep["runs"][0]
    for c in TARGET_COLUMNS:
        assert primary["per_target"][c] == {
            "skill": metrics["phase_baseline_skill"]["per_target"][c]["skill"],
            "r2": metrics["per_target"][c]["r2"],
            "rmse": metrics["per_target"][c]["rmse"],
            "config_mean_r2": metrics["config_resolved"][c]["config_mean_r2"],
        }, c
    assert primary["val_configs"] == metrics["reproducibility"]["val_configs"]

    dataset = _dataset()
    for run in sweep["runs"]:
        split = make_config_splits(dataset, seed=run["seed"])
        assert run["val_configs"] == split.val_configs, run["seed"]


def test_committed_phase_baseline_skill_recomputes():
    """phase_baseline_skill recomputed from the committed dataset and predictions matches.

    Catches a row misalignment inside run_training: the baseline is rebuilt at the committed
    predictions' phases and scored against their true and predicted columns.
    """
    metrics = _meta(SURROGATE / "metrics.json")["phase_baseline_skill"]
    holdout = pd.read_parquet(SURROGATE / "holdout_predictions.parquet")
    dataset = _dataset()
    y_baseline, definition = build_phase_only_baseline(
        dataset, holdout["phase"].to_numpy(dtype=float), list(TARGET_COLUMNS)
    )
    assert metrics["phase_baseline"] == definition
    assert definition["reference_configs"] == sorted(
        dataset.loc[dataset["split"] == "train", "config_name"].unique()
    )
    y_true = holdout[[f"{c}_true" for c in TARGET_COLUMNS]].to_numpy(dtype=float)
    y_pred = holdout[[f"{c}_pred" for c in TARGET_COLUMNS]].to_numpy(dtype=float)
    recomputed = compute_baseline_skill(
        y_true, y_pred, y_baseline, list(TARGET_COLUMNS)
    )
    for c in TARGET_COLUMNS:
        for key, value in recomputed[c].items():
            assert metrics["per_target"][c][key] == pytest.approx(value, abs=1e-12), (
                c,
                key,
            )


# A README skill-table row: target, plotted-seed skill, seed range, phase-only baseline R².
_SKILL_ROW = re.compile(
    r"^\s*\|\s*`(CF_\w+)`\s*\|\s*(\S+)\s*\|\s*(\S+) to (\S+)\s*\|\s*(\S+)\s*\|\s*$",
    re.M,
)
_SKILL_HEADER = (
    "| target | skill, seed 1234 | skill, 5 seeds | phase-only baseline R² |"
)


def test_skill_and_config_r2_table_patterns_cannot_cross_match():
    """Each README table guard reads only its own table, and neither reads the header."""
    skill_row = "| `CF_x` | 0.988 | 0.988 to 0.992 | 0.955 |"
    config_row = "| `CF_x` | -4.17 to 0.09 | -0.01 to 0.09 |"
    assert _SKILL_ROW.search(skill_row) and not _TABLE_ROW.search(skill_row)
    assert _TABLE_ROW.search(config_row) and not _SKILL_ROW.search(config_row)
    for pattern in (_SKILL_ROW, _TABLE_ROW):
        assert not pattern.search(_SKILL_HEADER)


def test_readme_skill_table_is_metrics_json():
    """The README's skill table is metrics.json, for all six targets, as the figure prints it."""
    readme = (COARSE / "README.md").read_text(encoding="utf-8")
    assert _SKILL_HEADER in readme
    rows = {m[0]: m[1:] for m in _SKILL_ROW.findall(readme)}
    assert set(rows) == set(TARGET_COLUMNS), sorted(rows)
    metrics = _meta(SURROGATE / "metrics.json")
    for c, cells in rows.items():
        skill = metrics["phase_baseline_skill"]["per_target"][c]
        rng = metrics["seed_sweep"]["range"][c]["skill"]
        expected = (
            format_metric(skill["skill"]),
            format_metric(rng["min"]),
            format_metric(rng["max"]),
            format_metric(skill["phase_baseline_r2"]),
        )
        assert cells == expected, c
