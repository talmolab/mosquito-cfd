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
    assert (out / "keep.txt").read_bytes() == b"precious"


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
    # The real fine corpus records its image; the driver refuses any other digest.
    recorded = json.loads(
        (FINE.parent / "run_metadata.json").read_text(encoding="utf-8")
    )
    real = _argv(FINE, COARSE, out)
    real[real.index(DIGEST)] = recorded["docker_image"]
    argv = [
        str(DRIVER),
        *real,
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
    inputs = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))[
        "inputs"
    ]
    # Inside the repository, paths are recorded relative to it (no local home directory).
    assert inputs["dataset_file"] == "examples/prelim_sweep_fine/dataset.parquet"
    assert inputs["coarse_dataset_file"] == "examples/prelim_sweep/dataset.parquet"
    assert inputs["docker_image_check"] == (
        "matches examples/prelim_sweep_fine/run_metadata.json"
    )


@pytest.mark.parametrize("entries", [",ridge,", "ridge,,ridge_fixed", ""])
def test_empty_entry_tokens_exit_non_zero(driver, corpora, tmp_path, entries, capsys):
    out = tmp_path / "out"
    assert driver.main([*_argv(*corpora, out), "--entries", entries]) != 0
    assert "empty token" in capsys.readouterr().err
    assert not out.exists()


def test_a_missing_dataset_exits_non_zero_with_a_message(
    driver, corpora, tmp_path, capsys
):
    out = tmp_path / "out"
    argv = _argv(tmp_path / "absent.parquet", corpora[1], out)
    assert driver.main(argv) == 2
    assert "absent.parquet" in capsys.readouterr().err
    assert not out.exists()


def test_an_out_dir_that_is_a_file_exits_non_zero(driver, corpora, tmp_path, capsys):
    out = tmp_path / "out"
    out.write_bytes(b"precious")
    assert driver.main(_argv(*corpora, out)) == 2
    assert "is not a directory" in capsys.readouterr().err
    assert out.read_bytes() == b"precious"


# --- Input provenance -------------------------------------------------------------------------


def _corpus_dirs(tmp_path, fine_digest=None, coarse_digest=None):
    fine_dir, coarse_dir = tmp_path / "fine", tmp_path / "coarse"
    fine_dir.mkdir()
    coarse_dir.mkdir()
    fine, coarse = fine_dir / "dataset.parquet", coarse_dir / "dataset.parquet"
    synthetic_corpus().to_parquet(fine, index=False)
    synthetic_corpus(scale=1.1).to_parquet(coarse, index=False)
    for d, digest in ((fine_dir, fine_digest), (coarse_dir, coarse_digest)):
        if digest is not None:
            (d / "run_metadata.json").write_text(
                json.dumps({"docker_image": digest}), encoding="utf-8"
            )
    return fine, coarse


def test_both_datasets_are_hashed_and_named(driver, tmp_path):
    import hashlib

    fine, coarse = _corpus_dirs(tmp_path)
    out = tmp_path / "out"
    assert driver.main([*_argv(fine, coarse, out), "--entries", "ridge_fixed"]) == 0
    inputs = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))[
        "inputs"
    ]
    assert inputs["dataset_sha256"] == hashlib.sha256(fine.read_bytes()).hexdigest()
    assert (
        inputs["coarse_dataset_sha256"]
        == hashlib.sha256(coarse.read_bytes()).hexdigest()
    )
    assert inputs["dataset_file"] == fine.as_posix()
    assert inputs["coarse_dataset_file"] == coarse.as_posix()
    assert (
        inputs["docker_image_check"] == "no run_metadata.json beside the fine dataset"
    )
    assert inputs["coarse_docker_image"] is None


def test_a_digest_other_than_the_fine_corpus_records_is_refused(
    driver, tmp_path, capsys
):
    other = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "e" * 64
    fine, coarse = _corpus_dirs(tmp_path, fine_digest=other)
    out = tmp_path / "out"
    assert driver.main([*_argv(fine, coarse, out), "--entries", "ridge_fixed"]) == 2
    assert other in capsys.readouterr().err
    assert not out.exists()


def test_the_matching_digest_and_the_coarse_digest_are_recorded(driver, tmp_path):
    coarse_digest = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "f" * 64
    fine, coarse = _corpus_dirs(
        tmp_path, fine_digest=DIGEST, coarse_digest=coarse_digest
    )
    out = tmp_path / "out"
    assert driver.main([*_argv(fine, coarse, out), "--entries", "ridge_fixed"]) == 0
    inputs = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))[
        "inputs"
    ]
    assert inputs["docker_image_check"] == (
        f"matches {(fine.parent / 'run_metadata.json').as_posix()}"
    )
    assert inputs["coarse_docker_image"] == coarse_digest


def _write_meta(path, text):
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("text", ["[1, 2]", "{not json", ""])
def test_an_unreadable_fine_record_is_refused_naming_it(driver, tmp_path, capsys, text):
    fine, coarse = _corpus_dirs(tmp_path)
    _write_meta(fine.parent / "run_metadata.json", text)
    out = tmp_path / "out"
    assert driver.main([*_argv(fine, coarse, out), "--entries", "ridge_fixed"]) == 2
    assert "run_metadata.json" in capsys.readouterr().err
    assert not out.exists()


def test_a_fine_record_without_an_image_is_recorded_as_such(driver, tmp_path):
    fine, coarse = _corpus_dirs(tmp_path)
    _write_meta(fine.parent / "run_metadata.json", json.dumps({"docker_image": None}))
    out = tmp_path / "out"
    assert driver.main([*_argv(fine, coarse, out), "--entries", "ridge_fixed"]) == 0
    inputs = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))[
        "inputs"
    ]
    assert inputs["docker_image_check"].endswith("records no docker_image")


@pytest.mark.parametrize(
    ("text", "phrase"),
    [
        ("{not json", "not valid JSON"),
        ("[1]", "not an object"),
        ("{}", "no docker_image"),
    ],
)
def test_a_bad_coarse_record_is_recorded_not_fatal(driver, tmp_path, text, phrase):
    fine, coarse = _corpus_dirs(tmp_path)
    _write_meta(coarse.parent / "run_metadata.json", text)
    out = tmp_path / "out"
    assert driver.main([*_argv(fine, coarse, out), "--entries", "ridge_fixed"]) == 0
    inputs = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))[
        "inputs"
    ]
    assert inputs["coarse_docker_image"] is None
    assert phrase in inputs["coarse_docker_image_source"]


def test_datasets_sharing_a_directory_do_not_borrow_the_fine_image(driver, tmp_path):
    folder = tmp_path / "both"
    folder.mkdir()
    fine, coarse = folder / "fine.parquet", folder / "coarse.parquet"
    synthetic_corpus().to_parquet(fine, index=False)
    synthetic_corpus(scale=1.1).to_parquet(coarse, index=False)
    _write_meta(folder / "run_metadata.json", json.dumps({"docker_image": DIGEST}))
    out = tmp_path / "out"
    assert driver.main([*_argv(fine, coarse, out), "--entries", "ridge_fixed"]) == 0
    inputs = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))[
        "inputs"
    ]
    assert inputs["coarse_docker_image"] is None
    assert (
        "shares the fine dataset's run_metadata.json"
        in inputs["coarse_docker_image_source"]
    )


def test_a_mutable_tag_is_reported_as_such_before_the_record_check(
    driver, tmp_path, capsys
):
    fine, coarse = _corpus_dirs(tmp_path, fine_digest=DIGEST)
    out = tmp_path / "out"
    argv = _argv(fine, coarse, out)
    argv[argv.index(DIGEST)] = "ghcr.io/talmolab/mosquito-cfd:latest"
    assert driver.main(argv) == 2
    assert "digest-pinned" in capsys.readouterr().err


def test_the_wrote_line_names_all_five_artifacts(driver, corpora, tmp_path, capsys):
    out = tmp_path / "out"
    assert driver.main([*_argv(*corpora, out), "--entries", "ridge_fixed"]) == 0
    printed = capsys.readouterr().out
    for name in (
        "results.parquet",
        "splits.json",
        "summary.json",
        "bench_summary.png",
        "run_metadata.json",
    ):
        assert name in printed, name


def test_git_state_is_read_from_the_repository_not_the_working_directory():
    source = DRIVER.read_text(encoding="utf-8")
    assert "get_git_info(REPO)" in source
