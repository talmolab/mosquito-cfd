"""CLI tests for scripts/make_coarse_vs_fine_figures.py (OpenSpec change add-real-comparison-figures).

The driver renders exactly one figure per invocation, passing ``root=Path.cwd()``, and argparse
refuses an unknown figure name or a missing flag with status 2 before anything is written.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from _comparison_corpus import COARSE_DIR, FINE_DIGEST, FINE_DIR, write_repo

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "make_coarse_vs_fine_figures.py"
)
TS = "2026-11-22T00:00:00Z"
GIT = {"commit": "b" * 40, "dirty": False, "branch": "add-real-comparison-figures"}


def _load_cli():
    spec = importlib.util.spec_from_file_location("make_coarse_vs_fine_figures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _argv(figure, out):
    return [
        "--figure",
        figure,
        "--coarse-dir",
        COARSE_DIR,
        "--fine-dir",
        FINE_DIR,
        "--out-dir",
        str(out),
        "--docker-digest",
        FINE_DIGEST,
        "--timestamp",
        TS,
    ]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    write_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.metadata.get_git_info", lambda *a, **k: GIT
    )
    return tmp_path


@pytest.mark.parametrize(
    "figure", ["skill_ranges", "error_histograms", "cycle_mean_r2_diagnostic"]
)
def test_one_figure_per_invocation(figure, repo):
    out = repo / "out"
    assert _load_cli().main(_argv(figure, out)) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        f"{figure}.png",
        f"{figure}_metrics.json",
        f"{figure}_run_metadata.json",
    ]


def test_an_unknown_figure_is_a_usage_error(repo):
    out = repo / "out"
    with pytest.raises(SystemExit) as excinfo:
        _load_cli().main(_argv("coarse_vs_fine_comparison", out))
    assert excinfo.value.code == 2
    assert not out.exists()


@pytest.mark.parametrize(
    "flag",
    [
        "--figure",
        "--coarse-dir",
        "--fine-dir",
        "--out-dir",
        "--docker-digest",
        "--timestamp",
    ],
)
def test_every_flag_is_required(flag, repo):
    out = repo / "out"
    argv = _argv("skill_ranges", out)
    i = argv.index(flag)
    del argv[i : i + 2]
    with pytest.raises(SystemExit) as excinfo:
        _load_cli().main(argv)
    assert excinfo.value.code == 2
    assert not out.exists()
