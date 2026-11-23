"""The bench driver scripts/run_surrogate_bench.py (add-surrogate-comparison-bench, 7c; CPU tier).

Scenario "The driver rejects unsafe invocations" and the driver's flags; plus a CPU smoke run of the
ridge entries on the real fine and coarse corpora with torch, physicsnemo, scipy and sklearn
imports blocked.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from test_surrogate_bench_runner import DIGEST, synthetic_corpus

REPO = Path(__file__).resolve().parents[1]
DRIVER = REPO / "scripts" / "run_surrogate_bench.py"
FINE = REPO / "examples" / "prelim_sweep_fine" / "dataset.parquet"
COARSE = REPO / "examples" / "prelim_sweep" / "dataset.parquet"
CLEAN = {"commit": "c" * 40, "branch": "results-branch", "dirty": False}


def _load():
    spec = importlib.util.spec_from_file_location("run_surrogate_bench", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def driver(monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "get_git_info", lambda *a, **k: dict(CLEAN))
    monkeypatch.setattr(module, "get_hardware_info", lambda: {"hostname": "h"})
    return module


@pytest.fixture
def corpora(tmp_path):
    fine, coarse = tmp_path / "fine.parquet", tmp_path / "coarse.parquet"
    synthetic_corpus().to_parquet(fine, index=False)
    synthetic_corpus(scale=1.1).to_parquet(coarse, index=False)
    return fine, coarse


def _argv(fine, coarse, out, *extra):
    return [
        "--dataset",
        str(fine),
        "--coarse-dataset",
        str(coarse),
        "--out-dir",
        str(out),
        "--docker-digest",
        DIGEST,
        "--timestamp",
        "2026-11-22T12:00:00Z",
        *extra,
    ]


def test_every_flag_is_wired(driver):
    args = driver.build_parser().parse_args(
        [
            *_argv("f", "c", "o"),
            "--device",
            "cuda",
            "--entries",
            "ridge,ridge_fixed",
            "--epochs",
            "5",
            "--allow-dirty",
        ]
    )
    assert (args.dataset, args.coarse_dataset, args.out_dir) == ("f", "c", "o")
    assert args.docker_digest == DIGEST and args.timestamp == "2026-11-22T12:00:00Z"
    assert args.device == "cuda" and args.epochs == 5 and args.allow_dirty is True
    assert driver.parse_entries(args.entries) == ["ridge", "ridge_fixed"]
    defaults = driver.build_parser().parse_args(_argv("f", "c", "o"))
    assert defaults.device == "cpu" and defaults.epochs == 2000
    assert defaults.allow_dirty is False and defaults.entries is None


@pytest.mark.parametrize(
    "extra",
    [
        ["--entries", "mlp_h1,nope"],
        ["--entries", "ridge,ridge"],
        ["--epochs", "0"],
    ],
)
def test_bad_arguments_exit_non_zero_without_writing(driver, corpora, tmp_path, extra):
    out = tmp_path / "out"
    assert driver.main([*_argv(*corpora, out), *extra]) != 0
    assert not out.exists()


def test_a_mutable_digest_exits_non_zero(driver, corpora, tmp_path):
    out = tmp_path / "out"
    argv = _argv(*corpora, out)
    argv[argv.index(DIGEST)] = "ghcr.io/talmolab/mosquito-cfd:latest"
    assert driver.main(argv) != 0 and not out.exists()


def test_a_missing_timestamp_exits_non_zero(driver, corpora, tmp_path):
    out = tmp_path / "out"
    argv = _argv(*corpora, out)
    i = argv.index("--timestamp")
    del argv[i : i + 2]
    with pytest.raises(SystemExit) as exc:
        driver.main(argv)
    assert exc.value.code != 0 and not out.exists()


def test_a_dirty_tree_exits_non_zero(driver, corpora, tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "get_git_info", lambda *a, **k: dict(CLEAN, dirty=True))
    out = tmp_path / "out"
    assert driver.main(_argv(*corpora, out)) != 0 and not out.exists()


def test_unknown_git_state_counts_as_dirty(driver, corpora, tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "get_git_info", lambda *a, **k: {"commit": "x"})
    out = tmp_path / "out"
    assert driver.main(_argv(*corpora, out)) != 0 and not out.exists()


def test_a_non_empty_out_dir_is_left_unchanged(driver, corpora, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_bytes(b"precious")
    assert driver.main(_argv(*corpora, out)) != 0
    assert [p.name for p in out.iterdir()] == ["keep.txt"]


def test_a_coarse_corpus_missing_a_configuration_exits_non_zero(driver, tmp_path):
    fine, coarse = tmp_path / "fine.parquet", tmp_path / "coarse.parquet"
    synthetic_corpus().to_parquet(fine, index=False)
    c = synthetic_corpus(scale=1.1)
    c[c["config_name"] != "s45_f100_p45"].to_parquet(coarse, index=False)
    out = tmp_path / "out"
    assert driver.main(_argv(fine, coarse, out)) != 0 and not out.exists()


def test_allow_dirty_runs_and_records_dirty(driver, corpora, tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "get_git_info", lambda *a, **k: dict(CLEAN, dirty=True))
    out = tmp_path / "out"
    argv = [*_argv(*corpora, out), "--allow-dirty", "--entries", "ridge_fixed"]
    assert driver.main(argv) == 0
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["git"]["dirty"] is True


@pytest.mark.skipif(not COARSE.exists(), reason="coarse corpus not present")
def test_cpu_smoke_run_on_the_real_corpora_without_heavy_imports(tmp_path):
    out = tmp_path / "bench"
    argv = [
        str(DRIVER),
        *_argv(FINE, COARSE, out),
        "--entries",
        "ridge,ridge_fixed",
        "--device",
        "cpu",
        "--allow-dirty",
    ]
    wrapper = textwrap.dedent(
        f"""
        import importlib.abc, runpy, sys
        BLOCKED = ("torch", "physicsnemo", "scipy", "sklearn")
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError("blocked import: " + name)
                return None
        sys.meta_path.insert(0, Block())
        sys.argv = {argv!r}
        runpy.run_path({str(DRIVER)!r}, run_name="__main__")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", wrapper], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-4000:]
    assert {p.name for p in out.iterdir()} == {
        "results.parquet",
        "splits.json",
        "summary.json",
        "bench_summary.png",
        "run_metadata.json",
    }
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert set(summary["gate"]["entries"]) == {"ridge", "ridge_fixed"}
