"""The three coarse-vs-fine figures: values, captions, labels and end-to-end writes.

OpenSpec change ``add-real-comparison-figures``. Synthetic corpora only, except where a test reads
the committed ``metrics.json`` files or the fine README to check agreement with the README guard.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from _comparison_corpus import (  # noqa: E402
    COARSE_DIR,
    FINE_DIGEST,
    FINE_DIR,
    CorpusSpec,
    default_error,
    default_truth,
    write_repo,
)
from _readme_guards import (  # noqa: E402
    _BANNED,
    _COMPARATIVE,
    _FINE_COMPARATIVE,
    _section,
    overlap_cell,
)

from mosquito_cfd.force_surrogate import comparison_figure as cf  # noqa: E402
from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DIGEST = FINE_DIGEST
TS = "2026-11-22T00:00:00Z"
GIT = {"commit": "a" * 40, "dirty": False, "branch": "add-real-comparison-figures"}

pytestmark = pytest.mark.filterwarnings("error")


@pytest.fixture(autouse=True)
def _fake_git(monkeypatch):
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.metadata.get_git_info", lambda *a, **k: GIT
    )


def _build(builder, root):
    out = root / "out"
    result = builder(
        root=root,
        coarse_dir=COARSE_DIR,
        fine_dir=FINE_DIR,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    return result, out


def _fine(**kw):
    return CorpusSpec(salt=0.013, digest=FINE_DIGEST, **kw)


def _assert_clean_wording(*texts, banned=False):
    for text in texts:
        assert not cf.FORBIDDEN_WORDS.search(text), text
        assert not _COMPARATIVE.search(text), text
        assert not _FINE_COMPARATIVE.search(text), text
        if banned:
            assert not _BANNED.search(text), (text, _BANNED.findall(text))


def _constant_target(column, value=0.75, salt=0.0):
    base = default_truth(salt)
    j = TARGET_COLUMNS.index(column)

    def truth(split, index, phase, beat):
        cols = base(split, index, phase, beat)
        cols[:, j] = value
        return cols

    return truth


# --- shared constants and wording -----------------------------------------------------------


def test_target_labels_are_lab_frame():
    assert cf.TARGET_LABELS == {
        "CF_x": "CF_x (lab x force)",
        "CF_y": "CF_y (lab y force)",
        "CF_z": "CF_z (lab vertical force)",
        "CF_mx": "CF_mx (lab M_x about the hinge)",
        "CF_my": "CF_my (lab M_y about the hinge)",
        "CF_mz": "CF_mz (lab M_z about the hinge)",
    }


@pytest.mark.parametrize(
    "text,matches",
    [
        ("normalised", False),
        ("timespan", False),
        ("wing-normal", True),
        ("spanwise", True),
        ("chordwise", True),
        ("spans", True),
        ("rolling", True),
    ],
)
def test_forbidden_pattern_matches_whole_framings_only(text, matches):
    assert bool(cf.FORBIDDEN_WORDS.search(text)) is matches


def test_fine_readme_carries_the_shared_constants():
    readme = (REPO / FINE_DIR / "README.md").read_text(encoding="utf-8")
    section, _ = _section(readme, "Coarse vs fine")
    flat = " ".join(section.split()).lower()
    assert cf.OWN_BASELINE_PHRASE.lower() in flat
    assert cf.RULE_SENTENCE.format(n=5).lower() in flat


@pytest.mark.parametrize(
    "n_beats,label,regen", [(2, "second wingbeat of 2-beat runs", True)]
)
def test_beat_label_two_beats(n_beats, label, regen):
    text = cf.beat_sentence(n_beats)
    assert label in text
    assert (cf.REGENERATION_PHRASE in text) is regen


def test_beat_label_four_beats():
    text = cf.beat_sentence(4)
    assert "wingbeats 2–4 of 4-beat runs" in text
    assert cf.REGENERATION_PHRASE not in text


# --- ranges_overlap -----------------------------------------------------------------------------

_PAIRS = [
    ({"min": 0.97, "max": 0.98}, {"min": 0.98, "max": 0.99}, "yes"),
    (
        {"min": 0.97, "max": 0.98},
        {"min": float(np.nextafter(0.98, 1.0)), "max": 0.99},
        "no",
    ),
    ({"min": 0.97, "max": 0.985}, {"min": 0.98, "max": 0.99}, "yes"),
    ({"min": 0.97, "max": 0.98}, None, "n/a"),
]


@pytest.mark.parametrize("coarse,fine,cell", _PAIRS)
def test_ranges_overlap_follows_the_rule_and_the_readme_guard(coarse, fine, cell):
    assert cf.ranges_overlap(coarse, fine) == cell
    assert overlap_cell(coarse, fine) == cell


def test_ranges_overlap_on_the_committed_metrics_marks_cf_y_only():
    def load(d):
        return json.loads((REPO / d / "surrogate" / "metrics.json").read_text("utf-8"))

    coarse, fine = load(COARSE_DIR), load(FINE_DIR)
    cells = {}
    for c in TARGET_COLUMNS:
        rc = coarse["seed_sweep"]["range"][c]["skill"]
        rf = fine["seed_sweep"]["range"][c]["skill"]
        cells[c] = cf.ranges_overlap(rc, rf)
        assert cells[c] == overlap_cell(rc, rf)
    assert {c for c, v in cells.items() if v == "no"} == {"CF_y"}


# --- skill_ranges ------------------------------------------------------------------------------


def test_skill_ranges_values_are_the_seed_sweep_verbatim(tmp_path):
    written = write_repo(tmp_path)
    result, _ = _build(cf.build_skill_ranges, tmp_path)
    for corpus in ("coarse", "fine"):
        metrics = written[corpus]["metrics"]
        runs = metrics["seed_sweep"]["runs"]
        others = set()
        for c in TARGET_COLUMNS:
            others.update(
                {
                    metrics["per_target"][c]["r2"],
                    metrics["per_target"][c]["rmse"],
                    metrics["config_resolved"][c]["config_mean_r2"],
                    metrics["phase_baseline_skill"]["per_target"][c][
                        "phase_baseline_r2"
                    ],
                    metrics["phase_baseline_skill"]["per_target"][c][
                        "phase_baseline_rmse"
                    ],
                }
            )
        for c in TARGET_COLUMNS:
            entry = result["targets"][c][corpus]
            assert entry["seeds"] == [r["seed"] for r in runs]
            assert entry["values"] == [r["per_target"][c]["skill"] for r in runs]
            assert not set(entry["values"]) & others
            primary = metrics["phase_baseline_skill"]["per_target"][c]["skill"]
            assert entry["values"][0] == primary
            assert entry["range"] == metrics["seed_sweep"]["range"][c]["skill"]


def _only_cf_y_differs(seed_index, holdout_index, phase):
    err = default_error((1.0, 1.4, 0.7, 1.2, 0.9))(seed_index, holdout_index, phase)
    err[:, TARGET_COLUMNS.index("CF_y")] *= 12.0
    return err


def test_only_disjoint_targets_get_a_note(tmp_path):
    same = CorpusSpec(digest=FINE_DIGEST)  # identical data: every range overlaps
    write_repo(tmp_path / "a", fine=same)
    result_a, _ = _build(cf.build_skill_ranges, tmp_path / "a")
    assert result_a["notes"] == {}

    write_repo(
        tmp_path / "b", fine=CorpusSpec(digest=FINE_DIGEST, error=_only_cf_y_differs)
    )
    result_b, _ = _build(cf.build_skill_ranges, tmp_path / "b")
    assert set(result_b["notes"]) == {"CF_y"}
    assert result_b["notes"]["CF_y"] == (
        "ranges disjoint at 5 seeds each; see README before reading this as a grid effect"
    )
    assert result_b["targets"]["CF_y"]["overlap"] == "no"
    _assert_clean_wording(result_b["caption"], *result_b["notes"].values(), banned=True)


def test_an_all_null_target_is_drawn_n_a(tmp_path):
    truth_c = _constant_target("CF_z")
    truth_f = _constant_target("CF_z", salt=0.013)
    write_repo(
        tmp_path,
        coarse=CorpusSpec(truth=truth_c),
        fine=_fine(truth=truth_f),
    )
    result, _ = _build(cf.build_skill_ranges, tmp_path)
    for corpus in ("coarse", "fine"):
        entry = result["targets"]["CF_z"][corpus]
        assert entry["values"] == [None] * 5
        assert entry["range"] is None
        assert entry["markers"] == 0
        assert entry["bar"] is None
        assert entry["na"] is True
    assert result["targets"]["CF_z"]["overlap"] == "n/a"
    assert "CF_z" not in result["notes"]


def test_skill_ranges_caption_and_labels(tmp_path):
    seeds = (42, 43, 44)
    scales = (1.0, 1.3, 0.8)
    write_repo(
        tmp_path,
        coarse=CorpusSpec(seeds=seeds, error_scales=scales),
        fine=_fine(seeds=seeds, error_scales=scales),
    )
    result, _ = _build(cf.build_skill_ranges, tmp_path)
    caption = result["caption"]
    for phrase in (
        cf.SHIPPED_PHRASE,
        cf.LAB_FRAME_PHRASE,
        cf.OWN_BASELINE_PHRASE,
        "seed 42",
        "3 seeds",
        "observed spread, not a confidence interval",
        cf.RULE_SENTENCE.format(n=3),
        "not a measurement of the effect of grid resolution on its own",
        "second wingbeat of 2-beat runs",
        cf.REGENERATION_PHRASE,
    ):
        assert phrase in caption, phrase
    assert "1234" not in caption and "5 seeds" not in caption
    assert result["labels"] == [cf.TARGET_LABELS[c] for c in TARGET_COLUMNS]
    _assert_clean_wording(caption, *result["labels"], banned=True)


def test_skill_ranges_caption_for_a_four_beat_corpus(tmp_path):
    write_repo(tmp_path, coarse=CorpusSpec(n_beats=4), fine=_fine(n_beats=4))
    result, _ = _build(cf.build_skill_ranges, tmp_path)
    assert "wingbeats 2–4 of 4-beat runs" in result["caption"]
    assert cf.REGENERATION_PHRASE not in result["caption"]


def test_skill_ranges_end_to_end(tmp_path):
    write_repo(tmp_path)
    before = plt.get_fignums()
    result, out = _build(cf.build_skill_ranges, tmp_path)
    assert sorted(p.name for p in out.iterdir()) == [
        "skill_ranges.png",
        "skill_ranges_metrics.json",
        "skill_ranges_run_metadata.json",
    ]
    assert plt.get_fignums() == before
    written = json.loads(
        (out / "skill_ranges_metrics.json").read_text(encoding="utf-8")
    )
    recomputed = cf.compute_skill_ranges_metrics(
        root=tmp_path, coarse_dir=COARSE_DIR, fine_dir=FINE_DIR
    )
    assert written == json.loads(cf._dumps(recomputed))
    assert written == json.loads(cf._dumps(result))
    meta = json.loads(
        (out / "skill_ranges_run_metadata.json").read_text(encoding="utf-8")
    )
    assert meta["figure"] == "skill_ranges"
    assert set(meta["input_files"]) == {
        f"{c}_{r}" for c in ("coarse", "fine") for r in cf.ROLE_FILES
    }
    assert meta["git"] == GIT
    assert math.isclose(len(written["targets"]), 6)
