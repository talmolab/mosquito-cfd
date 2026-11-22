"""Tests of the committed-figure checker on synthetic layouts (add-real-comparison-figures, 9.1).

Each layout is a synthetic coarse/fine corpus pair rendered by the real builders into the committed
figure directory, with injected git metadata. The unmodified layout passes; each kind of staleness
fails with an ``AssertionError`` naming the figure and the field or role.
"""

from __future__ import annotations

import json
import shutil

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from _comparison_corpus import (  # noqa: E402
    COARSE_DIR,
    FINE_DIGEST,
    FINE_DIR,
    write_repo,
)
from _comparison_guards import FIGURE_DIR, check_committed_figure  # noqa: E402

from mosquito_cfd.force_surrogate import comparison_figure as cf  # noqa: E402

TS = "2026-11-22T00:00:00Z"
CLEAN = {"commit": "c" * 40, "dirty": False, "branch": "add-real-comparison-figures"}


def _render(root, monkeypatch, git=CLEAN):
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.metadata.get_git_info", lambda *a, **k: git
    )
    for build in (
        cf.build_skill_ranges,
        cf.build_error_histograms,
        cf.build_cycle_mean_r2_diagnostic,
    ):
        build(
            root=root,
            coarse_dir=COARSE_DIR,
            fine_dir=FINE_DIR,
            out_dir=root / FIGURE_DIR,
            docker_image_digest=FINE_DIGEST,
            timestamp=TS,
        )


@pytest.fixture(scope="module")
def layout(tmp_path_factory):
    root = tmp_path_factory.mktemp("layout")
    write_repo(root)
    mp = pytest.MonkeyPatch()
    try:
        _render(root, mp)
    finally:
        mp.undo()
    return root


@pytest.fixture
def copy(layout, tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(layout, dst)
    return dst


def _edit_json(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


def _meta(root, figure):
    return root / FIGURE_DIR / f"{figure}_run_metadata.json"


def _metrics(root, figure):
    return root / FIGURE_DIR / f"{figure}_metrics.json"


@pytest.mark.parametrize("figure", cf.FIGURES)
def test_an_unmodified_layout_passes(layout, figure):
    check_committed_figure(layout, figure)


@pytest.mark.parametrize("figure", cf.FIGURES)
def test_a_changed_input_fails_naming_the_role(copy, figure):
    path = copy / FINE_DIR / "surrogate" / "metrics.json"
    text = path.read_text(encoding="utf-8")
    i = text.index('"skill": ') + len('"skill": ')
    j = i
    while text[j] in "0123456789.-e":
        j += 1
    last = text[j - 1]
    path.write_text(
        text[: j - 1] + ("1" if last != "1" else "2") + text[j:], encoding="utf-8"
    )
    json.loads(path.read_text(encoding="utf-8"))  # still valid JSON
    with pytest.raises(
        AssertionError,
        match=f"{figure}: input fine_metrics .* changed since the figure was rendered",
    ):
        check_committed_figure(copy, figure)


@pytest.mark.parametrize("figure", cf.FIGURES)
def test_a_dirty_render_fails(copy, figure):
    _edit_json(_meta(copy, figure), lambda d: d["git"].update(dirty=True))
    with pytest.raises(AssertionError, match=f"{figure}.*git.dirty"):
        check_committed_figure(copy, figure)


@pytest.mark.parametrize(
    "bad_path",
    [
        "examples\\prelim_sweep\\dataset.parquet",
        "C:/repo/examples/prelim_sweep/dataset.parquet",
    ],
)
def test_a_non_portable_path_fails(copy, bad_path):
    figure = "skill_ranges"
    _edit_json(
        _meta(copy, figure),
        lambda d: d["input_files"]["coarse_dataset"].update(path=bad_path),
    )
    with pytest.raises(AssertionError, match=f"{figure}.*coarse_dataset path"):
        check_committed_figure(copy, figure)


def test_a_moved_verbatim_skill_fails(copy):
    figure = "skill_ranges"

    def edit(d):
        values = d["targets"]["CF_x"]["coarse"]["values"]
        values[1] = values[1] * (1 + 1e-10)

    _edit_json(_metrics(copy, figure), edit)
    with pytest.raises(AssertionError, match=f"{figure}.*targets.CF_x.coarse.values"):
        check_committed_figure(copy, figure)


def test_a_moved_computed_eps_fails(copy):
    figure = "cycle_mean_r2_diagnostic"

    def edit(d):
        eps = d["grids"]["fine"]["CF_z"]["eps"]
        eps[2] = eps[2] * (1 + 1e-10)

    _edit_json(_metrics(copy, figure), edit)
    with pytest.raises(AssertionError, match=f"{figure}.*grids.fine.CF_z.eps"):
        check_committed_figure(copy, figure)


def test_a_moved_histogram_count_fails(copy):
    figure = "error_histograms"

    def edit(d):
        counts = d["grids"]["coarse"]["CF_y"]["counts_surrogate"]
        k = int(np.argmax(counts))
        counts[k] -= 1
        counts[k + 1] += 1

    _edit_json(_metrics(copy, figure), edit)
    with pytest.raises(AssertionError, match=f"{figure}.*counts_surrogate"):
        check_committed_figure(copy, figure)


@pytest.mark.parametrize("figure", cf.FIGURES)
def test_a_changed_renderer_hash_fails(copy, figure):
    _edit_json(
        _meta(copy, figure),
        lambda d: d["renderer_sources"].update({"comparison_figure.py": "0" * 64}),
    )
    with pytest.raises(AssertionError, match=f"{figure}.*renderer_sources"):
        check_committed_figure(copy, figure)


def test_wrong_corpus_images_and_digest_fail(copy):
    figure = "error_histograms"
    _edit_json(
        _meta(copy, figure), lambda d: d["corpus_docker_images"].update(coarse="x")
    )
    with pytest.raises(AssertionError, match="corpus_docker_images"):
        check_committed_figure(copy, figure)


def test_a_wrong_figure_digest_fails(copy):
    figure = "cycle_mean_r2_diagnostic"
    _edit_json(
        _meta(copy, figure), lambda d: d.update(docker_image="sha256:" + "9" * 64)
    )
    with pytest.raises(AssertionError, match="docker_image"):
        check_committed_figure(copy, figure)


def test_incomplete_library_versions_fail(copy):
    figure = "skill_ranges"
    _edit_json(
        _meta(copy, figure), lambda d: d["library_versions"].update(pyarrow=None)
    )
    with pytest.raises(AssertionError, match="library_versions"):
        check_committed_figure(copy, figure)


def test_a_bad_commit_fails(copy):
    figure = "skill_ranges"
    _edit_json(_meta(copy, figure), lambda d: d["git"].update(commit="main"))
    with pytest.raises(AssertionError, match="git.commit"):
        check_committed_figure(copy, figure)


def test_a_verbatim_skill_one_ulp_off_fails(copy):
    figure = "skill_ranges"

    def edit(d):
        values = d["targets"]["CF_mz"]["fine"]["values"]
        values[3] = float(np.nextafter(values[3], 2.0))

    _edit_json(_metrics(copy, figure), edit)
    with pytest.raises(AssertionError, match=f"{figure}.*targets.CF_mz.fine.values"):
        check_committed_figure(copy, figure)
