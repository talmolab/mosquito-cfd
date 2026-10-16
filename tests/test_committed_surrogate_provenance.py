"""Committed coarse surrogate and evidence figure are tied to their inputs and to a real commit.

fix-moment-reference-hinge PR3 retrains ``examples/prelim_sweep/surrogate/`` and regenerates the
evidence figure. These tests reconcile the committed artifacts against the files they were
produced from, unconditionally -- unlike the README staleness banner test, no state passes with a
mismatch:

- every ``<target>_true`` in the holdout predictions equals ``dataset.parquet``, for all six
  targets (the banner test checks only CF_mx/CF_mz, and only against the banner's presence);
- the surrogate's ``run_metadata.json`` names the dataset by sha256;
- the figure's ``run_metadata.json`` names the holdout predictions and ``metrics.json`` by sha256;
- every regenerated record carries a real git commit from a clean tree, not the
  ``git.error`` the pre-#78 surrogate record holds.

The recorded commits do not survive the squash-merge as ancestors of ``main``; they stay
resolvable via ``refs/pull/<n>/head``. The ``branch`` strings are frozen labels of the branch each
artifact was produced on.
"""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS

COARSE = Path("examples/prelim_sweep")
SURROGATE = COARSE / "surrogate"
FIGURES = COARSE / "figures"
_HEX40 = re.compile(r"[0-9a-f]{40}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("record", "branch"),
    [
        (SURROGATE / "run_metadata.json", "fix-moment-reference-hinge-pr3"),
        (FIGURES / "run_metadata.json", "fix-moment-reference-hinge-pr3"),
        (COARSE / "run_metadata.json", "fix-moment-reference-hinge-pr2"),
        (
            Path("examples/prelim_sweep_fine/run_metadata.json"),
            "fix-moment-reference-hinge-pr2",
        ),
    ],
    ids=["surrogate", "figure", "coarse-corpus", "fine-corpus"],
)
def test_regenerated_records_carry_a_clean_git_commit(record, branch):
    """Each record names a full commit, the branch it was produced on, and a clean tree.

    A ``git.error`` record, or the docker-build-arg fallback shape ``{commit, source}`` (which
    has a 40-hex commit but no branch or dirty flag), fails here.
    """
    git = _meta(record)["git"]
    assert "error" not in git, git
    assert _HEX40.fullmatch(git.get("commit", "")), git
    assert git.get("branch") == branch, git
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
