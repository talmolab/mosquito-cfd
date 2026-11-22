"""Input guards, provenance and writing discipline of the coarse-vs-fine figures.

OpenSpec change ``add-real-comparison-figures`` (spec: "Comparison figures validate their inputs
before writing anything", "Committed comparison figures stay current with their inputs and
renderer"). Synthetic corpora only (``_comparison_corpus.write_repo``); never the committed data.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
from pathlib import Path, PurePosixPath, PureWindowsPath

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from _comparison_corpus import (  # noqa: E402
    COARSE_DIGEST,
    COARSE_DIR,
    FINE_DIGEST,
    FINE_DIR,
    CorpusSpec,
    write_repo,
)

from mosquito_cfd.force_surrogate import comparison_figure as cf  # noqa: E402

DIGEST = FINE_DIGEST
TS = "2026-11-22T00:00:00Z"
BUILDERS = [
    cf.build_skill_ranges,
    cf.build_error_histograms,
    cf.build_cycle_mean_r2_diagnostic,
]
ROLE_FILES = {
    "dataset": "dataset.parquet",
    "predictions": "surrogate/holdout_predictions.parquet",
    "metrics": "surrogate/metrics.json",
    "surrogate_run_metadata": "surrogate/run_metadata.json",
}


def _call(builder, root, out):
    return builder(
        root=root,
        coarse_dir=COARSE_DIR,
        fine_dir=FINE_DIR,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )


def _expect_refusal(builder, root, *needles):
    out = root / "out"
    before = plt.get_fignums()
    with pytest.raises(ValueError) as excinfo:
        _call(builder, root, out)
    message = str(excinfo.value)
    for needle in needles:
        assert needle in message, (needle, message)
    assert not out.exists() or not any(out.iterdir())
    assert plt.get_fignums() == before


def _corpus_path(root, corpus, role):
    base = COARSE_DIR if corpus == "coarse" else FINE_DIR
    return root / base / ROLE_FILES[role]


def _rewrite_parquet(path, fn):
    df = pd.read_parquet(path)
    fn(df).to_parquet(path)


def _rewrite_json(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    data = fn(data) or data
    path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


# --- guard 1: the digest, before any file ---------------------------------------------------


@pytest.mark.parametrize("builder", BUILDERS)
def test_digest_is_checked_before_any_file(builder, tmp_path):
    with pytest.raises(ValueError, match="docker_image_digest"):
        builder(
            root=tmp_path,
            coarse_dir="does/not/exist",
            fine_dir="nor/this",
            out_dir=tmp_path / "out",
            docker_image_digest=":latest",
            timestamp=TS,
        )


# --- guards 2-11, one defect at a time --------------------------------------------------------


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize("corpus", ["coarse", "fine"])
@pytest.mark.parametrize("role", list(ROLE_FILES))
def test_missing_input_is_refused(builder, corpus, role, tmp_path):
    write_repo(tmp_path)
    _corpus_path(tmp_path, corpus, role).unlink()
    _expect_refusal(builder, tmp_path, f"{corpus}_{role}", "missing")


@pytest.mark.parametrize("builder", BUILDERS)
def test_json_input_that_is_not_an_object_is_refused(builder, tmp_path):
    write_repo(tmp_path)
    _corpus_path(tmp_path, "coarse", "metrics").write_text("[]", encoding="utf-8")
    _expect_refusal(builder, tmp_path, "coarse_metrics", "JSON object")


@pytest.mark.parametrize("builder", BUILDERS)
def test_nan_literal_in_metrics_is_refused(builder, tmp_path):
    write_repo(tmp_path)
    path = _corpus_path(tmp_path, "fine", "metrics")
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('"latency_ms": ', '"latency_ms": NaN, "x": ', 1), "utf-8"
    )
    _expect_refusal(builder, tmp_path, "fine_metrics", "NaN")


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize(
    "role,column",
    [
        ("predictions", "config_name"),
        ("predictions", "time"),
        ("predictions", "phase"),
        ("predictions", "wingbeat"),
        ("predictions", "CF_mz_true"),
        ("predictions", "CF_x_pred"),
        ("dataset", "split"),
        ("dataset", "CF_my"),
    ],
)
def test_missing_column_is_refused(builder, role, column, tmp_path):
    write_repo(tmp_path)
    _rewrite_parquet(
        _corpus_path(tmp_path, "coarse", role), lambda df: df.drop(columns=column)
    )
    _expect_refusal(builder, tmp_path, f"coarse_{role}", column)


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize("corpus", ["coarse", "fine"])
def test_dataset_hash_mismatch_is_refused(builder, corpus, tmp_path):
    written = write_repo(tmp_path)
    bad = "0" * 64

    def edit(meta):
        meta["inputs"]["hash"] = bad

    _rewrite_json(_corpus_path(tmp_path, corpus, "surrogate_run_metadata"), edit)
    _expect_refusal(builder, tmp_path, corpus, bad, written[corpus]["sha"])


@pytest.mark.parametrize("builder", BUILDERS)
def test_empty_predictions_are_refused(builder, tmp_path):
    write_repo(tmp_path)
    _rewrite_parquet(
        _corpus_path(tmp_path, "coarse", "predictions"), lambda df: df.iloc[:0]
    )
    _expect_refusal(builder, tmp_path, "coarse_predictions", "empty")


@pytest.mark.parametrize("builder", BUILDERS)
def test_a_single_configuration_is_refused(builder, tmp_path):
    write_repo(tmp_path)
    _rewrite_parquet(
        _corpus_path(tmp_path, "coarse", "predictions"),
        lambda df: df[df["config_name"] == "h00"],
    )
    _expect_refusal(builder, tmp_path, "coarse_predictions", "two configurations")


@pytest.mark.parametrize("builder", BUILDERS)
def test_a_repeated_key_is_refused(builder, tmp_path):
    write_repo(tmp_path)
    _rewrite_parquet(
        _corpus_path(tmp_path, "coarse", "predictions"),
        lambda df: pd.concat([df, df.iloc[:1]], ignore_index=True),
    )
    _expect_refusal(builder, tmp_path, "coarse_predictions", "duplicate")


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize("column", ["CF_z_true", "CF_z_pred"])
@pytest.mark.parametrize("value", [np.inf, -np.inf, np.nan])
def test_a_non_finite_coefficient_is_refused(builder, column, value, tmp_path):
    write_repo(tmp_path)

    def edit(df):
        df.loc[3, column] = value
        return df

    _rewrite_parquet(_corpus_path(tmp_path, "fine", "predictions"), edit)
    _expect_refusal(builder, tmp_path, "fine_predictions", "non-finite", column)


@pytest.mark.parametrize("builder", BUILDERS)
def test_non_contiguous_wingbeats_are_refused(builder, tmp_path):
    def edit(df):
        return df.assign(wingbeat=df["wingbeat"].replace({1: 2}))

    write_repo(tmp_path, coarse=CorpusSpec(edit_dataset=edit))
    _expect_refusal(builder, tmp_path, "coarse_dataset", "wingbeat")


@pytest.mark.parametrize("builder", BUILDERS)
def test_one_configuration_with_an_extra_beat_is_refused(builder, tmp_path):
    def edit(df):
        extra = df[(df["config_name"] == "h03") & (df["wingbeat"] == 1)].copy()
        extra["wingbeat"] = 2
        extra["time"] = extra["time"] + 1.0
        return pd.concat([df, extra], ignore_index=True)

    write_repo(tmp_path, coarse=CorpusSpec(edit_dataset=edit))
    _expect_refusal(builder, tmp_path, "coarse_dataset", "wingbeat")


@pytest.mark.parametrize("builder", BUILDERS)
def test_converged_min_wingbeat_mismatch_is_refused(builder, tmp_path):
    def edit(metrics):
        metrics["phase_baseline_skill"]["phase_baseline"]["converged_min_wingbeat"] = 0

    write_repo(tmp_path, coarse=CorpusSpec(edit_metrics=edit))
    _expect_refusal(builder, tmp_path, "coarse_metrics", "converged_min_wingbeat")


@pytest.mark.parametrize("builder", BUILDERS)
def test_a_prediction_row_from_the_transient_beat_is_refused(builder, tmp_path):
    write_repo(tmp_path)

    def edit(df):
        df.loc[0, "wingbeat"] = 0
        return df

    _rewrite_parquet(_corpus_path(tmp_path, "coarse", "predictions"), edit)
    _expect_refusal(builder, tmp_path, "coarse_predictions", "wingbeat")


@pytest.mark.parametrize("builder", BUILDERS)
def test_predictions_not_tied_to_the_dataset_are_refused(builder, tmp_path):
    write_repo(tmp_path)

    def edit(df):
        df.loc[5, "CF_x_true"] = np.nextafter(df.loc[5, "CF_x_true"], np.inf)
        return df

    _rewrite_parquet(_corpus_path(tmp_path, "coarse", "predictions"), edit)
    _expect_refusal(builder, tmp_path, "coarse_predictions", "CF_x_true")


@pytest.mark.parametrize("builder", BUILDERS)
def test_predictions_swapped_between_corpora_are_refused(builder, tmp_path):
    write_repo(tmp_path)
    fine = _corpus_path(tmp_path, "fine", "predictions").read_bytes()
    _corpus_path(tmp_path, "coarse", "predictions").write_bytes(fine)
    _expect_refusal(builder, tmp_path, "coarse_predictions", "dataset")


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize("end", ["min", "max"])
@pytest.mark.parametrize("corpus", ["coarse", "fine"])
def test_a_range_off_by_one_ulp_is_refused(builder, end, corpus, tmp_path):
    def edit(metrics):
        rng = metrics["seed_sweep"]["range"]["CF_x"]["skill"]
        rng[end] = float(np.nextafter(rng[end], np.inf))

    spec = CorpusSpec(edit_metrics=edit)
    if corpus == "fine":
        spec = CorpusSpec(salt=0.013, digest=FINE_DIGEST, edit_metrics=edit)
        write_repo(tmp_path, fine=spec)
    else:
        write_repo(tmp_path, coarse=spec)
    _expect_refusal(builder, tmp_path, f"{corpus}_metrics", "range", "CF_x", "skill")


@pytest.mark.parametrize("builder", BUILDERS)
def test_a_first_run_that_is_not_the_primary_seed_is_refused(builder, tmp_path):
    def edit(metrics):
        metrics["seed_sweep"]["primary_seed"] = 4321

    write_repo(tmp_path, coarse=CorpusSpec(edit_metrics=edit))
    _expect_refusal(builder, tmp_path, "coarse_metrics", "primary_seed")


@pytest.mark.parametrize("builder", BUILDERS)
def test_phase_baseline_skill_disagreeing_with_the_primary_run_is_refused(
    builder, tmp_path
):
    def edit(metrics):
        entry = metrics["phase_baseline_skill"]["per_target"]["CF_x"]
        entry["skill"] = float(np.nextafter(entry["skill"], np.inf))

    write_repo(tmp_path, coarse=CorpusSpec(edit_metrics=edit))
    _expect_refusal(builder, tmp_path, "coarse_metrics", "phase_baseline_skill", "CF_x")


@pytest.mark.parametrize("builder", BUILDERS)
def test_a_partial_null_skill_is_refused(builder, tmp_path):
    def edit(runs):
        runs[2]["per_target"]["CF_y"]["skill"] = float("nan")

    write_repo(tmp_path, coarse=CorpusSpec(edit_runs=edit))
    _expect_refusal(builder, tmp_path, "coarse_metrics", "CF_y", "skill", "null")


@pytest.mark.parametrize("builder", BUILDERS)
@pytest.mark.parametrize("value", [1.5, float(np.nextafter(1.0, 2.0))])
def test_a_config_mean_r2_above_one_is_refused(builder, value, tmp_path):
    def edit(runs):
        runs[3]["per_target"]["CF_mx"]["config_mean_r2"] = value

    write_repo(tmp_path, coarse=CorpusSpec(edit_runs=edit))
    _expect_refusal(
        builder, tmp_path, "coarse_metrics", "CF_mx", "config_mean_r2", "1237"
    )


@pytest.mark.parametrize("builder", BUILDERS)
def test_differing_configuration_sets_are_refused(builder, tmp_path):
    write_repo(tmp_path, fine=CorpusSpec(salt=0.013, digest=FINE_DIGEST, n_holdout=7))
    _expect_refusal(builder, tmp_path, "configuration")


@pytest.mark.parametrize("builder", BUILDERS)
def test_differing_seed_lists_are_refused(builder, tmp_path):
    fine = CorpusSpec(
        salt=0.013, digest=FINE_DIGEST, seeds=(1234, 1235, 1236, 1237, 1239)
    )
    write_repo(tmp_path, fine=fine)
    _expect_refusal(builder, tmp_path, "seed", "1238", "1239")


@pytest.mark.parametrize("builder", BUILDERS)
def test_differing_validation_carves_are_refused(builder, tmp_path):
    def edit(runs):
        runs[1]["val_configs"] = ["t05", "t04", "t03"]

    write_repo(
        tmp_path, fine=CorpusSpec(salt=0.013, digest=FINE_DIGEST, edit_runs=edit)
    )
    _expect_refusal(builder, tmp_path, "val_configs")


@pytest.mark.parametrize("builder", BUILDERS)
def test_differing_beat_counts_are_refused(builder, tmp_path):
    write_repo(tmp_path, fine=CorpusSpec(salt=0.013, digest=FINE_DIGEST, n_beats=3))
    _expect_refusal(builder, tmp_path, "beat")


def test_a_valid_pair_passes_every_guard(tmp_path):
    write_repo(tmp_path)
    coarse = cf._load_corpus(tmp_path, COARSE_DIR, "coarse")
    fine = cf._load_corpus(tmp_path, FINE_DIR, "fine")
    assert cf._check_pair(coarse, fine) == 2


# --- provenance helpers -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,root",
    [
        (
            PureWindowsPath("C:/repo/examples/prelim_sweep/dataset.parquet"),
            PureWindowsPath("C:/repo"),
        ),
        (
            PurePosixPath("/repo/examples/prelim_sweep/dataset.parquet"),
            PurePosixPath("/repo"),
        ),
    ],
)
def test_portable_path_is_repo_relative_with_forward_slashes(path, root):
    assert cf._portable_path(path, root) == "examples/prelim_sweep/dataset.parquet"


def test_portable_path_resolves_a_relative_path_against_the_root(tmp_path):
    assert (
        cf._portable_path(Path("examples/prelim_sweep"), tmp_path)
        == "examples/prelim_sweep"
    )


@pytest.mark.parametrize(
    "path",
    [
        PurePosixPath("/elsewhere/x.parquet"),
        PurePosixPath("/repo/../elsewhere/x.parquet"),
    ],
)
def test_portable_path_refuses_a_path_outside_the_root(path):
    with pytest.raises(ValueError, match="outside"):
        cf._portable_path(path, PurePosixPath("/repo"))


def _lf_sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_provenance_records_every_input_and_the_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.metadata.get_git_info",
        lambda *a, **k: {"commit": "a" * 40, "dirty": False, "branch": "b"},
    )
    write_repo(tmp_path)
    coarse = cf._load_corpus(tmp_path, COARSE_DIR, "coarse")
    fine = cf._load_corpus(tmp_path, FINE_DIR, "fine")
    extra = tmp_path / "renderer.py"
    extra.write_bytes(b"x = 1\r\n")
    meta = cf._provenance(
        root=tmp_path,
        coarse=coarse,
        fine=fine,
        docker_image_digest=DIGEST,
        timestamp=TS,
        figure="skill_ranges",
        renderer_files={
            "comparison_figure.py": Path(cf.__file__),
            "renderer.py": extra,
        },
    )
    assert set(meta["input_files"]) == {
        f"{c}_{r}" for c in ("coarse", "fine") for r in ROLE_FILES
    }
    for role, entry in meta["input_files"].items():
        corpus, _, kind = role.partition("_")
        expected = _corpus_path(tmp_path, corpus, kind)
        assert entry["path"] == expected.relative_to(tmp_path).as_posix()
        assert entry["sha256"] == hashlib.sha256(expected.read_bytes()).hexdigest()
        assert "\\" not in entry["path"]
    assert meta["inputs"]["file"] == f"{COARSE_DIR}/surrogate/metrics.json"
    assert meta["inputs"]["hash"] == meta["input_files"]["coarse_metrics"]["sha256"]
    assert meta["corpus_docker_images"] == {
        "coarse": COARSE_DIGEST,
        "fine": FINE_DIGEST,
    }
    versions = meta["library_versions"]
    assert versions["python"] == platform.python_version()
    for dist in ("numpy", "pandas", "pyarrow", "matplotlib"):
        assert versions[dist] == importlib.metadata.version(dist)
    assert meta["renderer_sources"] == {
        "comparison_figure.py": _lf_sha(cf.__file__),
        "renderer.py": hashlib.sha256(b"x = 1\n").hexdigest(),
    }
    assert meta["figure"] == "skill_ranges"
    assert meta["docker_image"] == DIGEST
    assert meta["timestamp"] == TS


def test_renderer_sources_records_a_missing_file_as_null(tmp_path):
    sources = cf._renderer_sources({"gone.py": tmp_path / "gone.py"})
    assert sources == {"gone.py": None}


def test_default_renderer_files_are_the_module_and_the_driver():
    assert set(cf.RENDERER_FILES) == {
        "comparison_figure.py",
        "scripts/make_coarse_vs_fine_figures.py",
    }
    assert cf.RENDERER_FILES["comparison_figure.py"] == Path(cf.__file__).resolve()


# --- writing discipline ------------------------------------------------------------------------


def _trivial_figure():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    return fig


def test_write_outputs_writes_exactly_three_files(tmp_path):
    out = tmp_path / "out"
    before = plt.get_fignums()
    cf._write_outputs(
        out, "skill_ranges", _trivial_figure(), {"a": 1.0}, {"b": float("nan")}
    )
    assert sorted(p.name for p in out.iterdir()) == [
        "skill_ranges.png",
        "skill_ranges_metrics.json",
        "skill_ranges_run_metadata.json",
    ]
    assert (out / "skill_ranges.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    meta = json.loads(
        (out / "skill_ranges_run_metadata.json").read_text(encoding="utf-8")
    )
    assert meta == {"b": None}
    assert b"\r\n" not in (out / "skill_ranges_metrics.json").read_bytes()
    assert plt.get_fignums() == before


def test_write_outputs_leaves_nothing_when_savefig_fails(tmp_path, monkeypatch):
    out = tmp_path / "out"
    before = plt.get_fignums()
    fig = _trivial_figure()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(fig, "savefig", boom)
    with pytest.raises(OSError):
        cf._write_outputs(out, "skill_ranges", fig, {}, {})
    assert not out.exists() or not any(out.iterdir())
    assert plt.get_fignums() == before


def test_write_outputs_partial_set_after_the_second_replace_fails(
    tmp_path, monkeypatch
):
    out = tmp_path / "out"
    real_replace = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("replace failed")
        return real_replace(src, dst)

    monkeypatch.setattr(cf.os, "replace", flaky)
    with pytest.raises(OSError):
        cf._write_outputs(out, "skill_ranges", _trivial_figure(), {}, {})
    assert sorted(p.name for p in out.iterdir()) == ["skill_ranges.png"]
    assert plt.get_fignums() == []


def test_metrics_payload_numpy_scalars_serialise(tmp_path):
    out = tmp_path / "out"
    payload = {
        "n": np.int64(3),
        "x": np.float64(0.5),
        "inf": math.inf,
        "arr": [np.int64(1)],
    }
    cf._write_outputs(out, "skill_ranges", _trivial_figure(), payload, {})
    metrics = json.loads(
        (out / "skill_ranges_metrics.json").read_text(encoding="utf-8")
    )
    assert metrics == {"n": 3, "x": 0.5, "inf": None, "arr": [1]}


@pytest.mark.parametrize("builder", BUILDERS)
def test_a_missing_prediction_row_is_refused_by_the_row_match(builder, tmp_path):
    write_repo(tmp_path)
    _rewrite_parquet(
        _corpus_path(tmp_path, "coarse", "predictions"),
        lambda df: df.drop(index=7).reset_index(drop=True),
    )
    _expect_refusal(
        builder, tmp_path, "coarse_predictions", "are not exactly", "holdout rows"
    )
