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


# --- error_histograms -------------------------------------------------------------------------

from mosquito_cfd.force_surrogate.evidence_figure import format_metric  # noqa: E402
from mosquito_cfd.force_surrogate.train import build_phase_only_baseline  # noqa: E402


def test_bin_counts_follow_the_numpy_edge_convention():
    counts, below, above = cf._bin_counts(
        np.array([-3.5, -3.0, 0.0, 3.0, 3.5]), cf.EDGES
    )
    assert len(cf.EDGES) == 601 and cf.EDGES[0] == -3.0 and cf.EDGES[-1] == 3.0
    assert (below, above) == (1, 1)
    assert counts[0] == 1 and counts[-1] == 1
    assert counts.sum() + below + above == 5


def _spike(seed_index, holdout_index, phase):
    err = default_error((1.0, 1.4, 0.7, 1.2, 0.9))(seed_index, holdout_index, phase)
    if holdout_index == 0:
        err[0, 0] += 50.0  # far outside +3 baseline RMSEs
        err[1, 0] -= 50.0
    return err


def test_histogram_counts_are_the_normalised_errors(tmp_path):
    written = write_repo(tmp_path, coarse=CorpusSpec(error=_spike))
    result, _ = _build(cf.build_error_histograms, tmp_path)
    edges = np.asarray(result["edges"])
    for corpus in ("coarse", "fine"):
        pred = written[corpus]["predictions"]
        base, _ = build_phase_only_baseline(
            written[corpus]["dataset"], pred["phase"].to_numpy(dtype=float)
        )
        for j, c in enumerate(TARGET_COLUMNS):
            entry = result["grids"][corpus][c]
            t = pred[f"{c}_true"].to_numpy()
            rmse0 = entry["rmse0"]
            for kind, values in (
                ("surrogate", pred[f"{c}_pred"].to_numpy()),
                ("baseline", base[:, j]),
            ):
                z = (values - t) / rmse0
                inside = z[(z >= -3) & (z <= 3)]
                expected, _ = np.histogram(inside, bins=edges)
                assert entry[f"counts_{kind}"] == expected.tolist()
                assert entry[f"below_{kind}"] == int((z < -3).sum())
                assert entry[f"above_{kind}"] == int((z > 3).sum())
                total = (
                    sum(entry[f"counts_{kind}"])
                    + entry[f"below_{kind}"]
                    + entry[f"above_{kind}"]
                )
                assert total == entry["n_rows"] == len(pred)
    spiked = result["grids"]["coarse"]["CF_x"]
    assert spiked["above_surrogate"] >= 1 and spiked["below_surrogate"] >= 1


def test_density_counts_every_row_including_out_of_range(tmp_path):
    write_repo(tmp_path, coarse=CorpusSpec(error=_spike))
    result, _ = _build(cf.build_error_histograms, tmp_path)
    entry = result["grids"]["coarse"]["CF_x"]
    widths = np.diff(np.asarray(result["edges"]))
    density = cf._density(
        np.asarray(entry["counts_surrogate"]),
        entry["n_rows"],
        np.asarray(result["edges"]),
    )
    assert np.array_equal(
        density, np.asarray(entry["counts_surrogate"]) / (entry["n_rows"] * widths)
    )
    assert (
        density * widths
    ).sum() < 1.0  # the out-of-range rows are not renormalised away


def test_recomputed_skill_is_consistent_with_its_rmses(tmp_path):
    written = write_repo(tmp_path)
    result, _ = _build(cf.build_error_histograms, tmp_path)
    for corpus in ("coarse", "fine"):
        runs0 = written[corpus]["metrics"]["seed_sweep"]["runs"][0]
        for c in TARGET_COLUMNS:
            e = result["grids"][corpus][c]
            assert math.isclose(
                (e["rmse_surrogate"] / e["rmse0"]) ** 2,
                1 - e["skill"],
                rel_tol=1e-12,
                abs_tol=0,
            )
            assert e["skill_recorded"] == runs0["per_target"][c]["skill"]
            assert (
                e["skill_range"]
                == written[corpus]["metrics"]["seed_sweep"]["range"][c]["skill"]
            )


def _scale_rmse(factor):
    def edit(metrics):
        metrics["phase_baseline_skill"]["per_target"]["CF_x"][
            "phase_baseline_rmse"
        ] *= factor

    return edit


def test_a_baseline_rmse_off_by_1e8_is_refused_and_1e11_accepted(tmp_path):
    write_repo(tmp_path / "a", coarse=CorpusSpec(edit_metrics=_scale_rmse(1 + 1e-8)))
    with pytest.raises(ValueError) as excinfo:
        _build(cf.build_error_histograms, tmp_path / "a")
    for needle in ("coarse", "CF_x", "phase-only baseline"):
        assert needle in str(excinfo.value)
    assert not (tmp_path / "a" / "out").exists()

    write_repo(tmp_path / "b", coarse=CorpusSpec(edit_metrics=_scale_rmse(1 + 1e-11)))
    _build(cf.build_error_histograms, tmp_path / "b")


def _perturbed_skill(factor):
    holder = {}

    def edit_runs(runs):
        old = runs[0]["per_target"]["CF_x"]["skill"]
        holder["new"] = 1 - (1 - old) * factor
        runs[0]["per_target"]["CF_x"]["skill"] = holder["new"]

    def edit_metrics(metrics):
        metrics["phase_baseline_skill"]["per_target"]["CF_x"]["skill"] = holder["new"]

    return CorpusSpec(edit_runs=edit_runs, edit_metrics=edit_metrics)


def test_a_recorded_skill_off_by_1e8_is_refused_and_1e11_accepted(tmp_path):
    write_repo(tmp_path / "a", coarse=_perturbed_skill(1 + 1e-8))
    with pytest.raises(ValueError) as excinfo:
        _build(cf.build_error_histograms, tmp_path / "a")
    for needle in ("coarse", "CF_x", "skill"):
        assert needle in str(excinfo.value)
    write_repo(tmp_path / "b", coarse=_perturbed_skill(1 + 1e-11))
    _build(cf.build_error_histograms, tmp_path / "b")


def test_a_reordered_baseline_definition_is_refused(tmp_path):
    def edit(metrics):
        definition = metrics["phase_baseline_skill"]["phase_baseline"]
        definition["reference_configs"] = list(
            reversed(definition["reference_configs"])
        )

    write_repo(tmp_path, coarse=CorpusSpec(edit_metrics=edit))
    with pytest.raises(ValueError) as excinfo:
        _build(cf.build_error_histograms, tmp_path)
    assert "coarse" in str(excinfo.value) and "reference_configs" in str(excinfo.value)
    assert not (tmp_path / "out").exists()


def test_a_null_recorded_skill_is_refused(tmp_path):
    write_repo(
        tmp_path,
        coarse=CorpusSpec(truth=_constant_target("CF_z")),
        fine=_fine(truth=_constant_target("CF_z", salt=0.013)),
    )
    with pytest.raises(ValueError) as excinfo:
        _build(cf.build_error_histograms, tmp_path)
    assert "CF_z" in str(excinfo.value) and "null" in str(excinfo.value)


def test_histogram_annotation_and_caption(tmp_path):
    seeds = (42, 43, 44)
    scales = (1.0, 1.3, 0.8)
    written = write_repo(
        tmp_path,
        coarse=CorpusSpec(seeds=seeds, error_scales=scales),
        fine=_fine(seeds=seeds, error_scales=scales),
    )
    result, _ = _build(cf.build_error_histograms, tmp_path)
    metrics = written["coarse"]["metrics"]
    x = metrics["seed_sweep"]["runs"][0]["per_target"]["CF_x"]["skill"]
    rng = metrics["seed_sweep"]["range"]["CF_x"]["skill"]
    assert result["annotations"]["coarse"]["CF_x"] == (
        f"seed 42 skill {format_metric(x)} "
        f"(3 seeds: {format_metric(rng['min'])} to {format_metric(rng['max'])})"
    )
    caption = result["caption"]
    for phrase in (
        cf.SHIPPED_PHRASE,
        cf.LAB_FRAME_PHRASE,
        cf.OWN_BASELINE_PHRASE,
        "seed 42",
        "skill = 1 − (RMSE / RMSE₀)²",
        "not compared across the two rows",
        "consecutive timesteps of 6 configurations, not independent samples",
        "second wingbeat of 2-beat runs",
        cf.REGENERATION_PHRASE,
    ):
        assert phrase in caption, phrase
    assert "1234" not in caption
    texts = [caption, *result["labels"]]
    texts += [a for grid in result["annotations"].values() for a in grid.values()]
    _assert_clean_wording(*texts)


def test_histogram_caption_for_a_four_beat_corpus(tmp_path):
    write_repo(tmp_path, coarse=CorpusSpec(n_beats=4), fine=_fine(n_beats=4))
    result, _ = _build(cf.build_error_histograms, tmp_path)
    assert "wingbeats 2–4 of 4-beat runs" in result["caption"]
    assert cf.REGENERATION_PHRASE not in result["caption"]


def _k2_truth(split, index, phase, beat):
    cols = default_truth(0.0)(split, index, phase, beat)
    cols[:, 0] = [-1.0, 0.0, 1.0][index] if split == "train" else 10.0
    return cols


def _k2_drop_rows(df):
    keep = np.ones(len(df), dtype=bool)
    for name, step in (("t00", 4), ("t01", 2)):
        rows = np.flatnonzero(df["config_name"].to_numpy() == name)
        keep[rows] = False
        keep[rows[::step]] = True
    return df[keep].reset_index(drop=True)


def test_k2_baseline_excludes_the_holdout_and_weights_configurations_equally(tmp_path):
    """Training CF_x constants -1, 0, +1 with 4, 8, 16 rows per beat; holdout CF_x = 10.
    Equal weighting gives baseline 0 and rmse0 = 10 exactly; row weighting or holdout leakage
    would not."""
    spec_c = CorpusSpec(
        n_train=3, rows_per_beat=16, truth=_k2_truth, edit_dataset=_k2_drop_rows
    )
    spec_f = CorpusSpec(n_train=3, rows_per_beat=16, salt=0.013, digest=FINE_DIGEST)
    write_repo(tmp_path, coarse=spec_c, fine=spec_f)
    result, _ = _build(cf.build_error_histograms, tmp_path)
    assert result["grids"]["coarse"]["CF_x"]["rmse0"] == 10.0


def _k3_truth(split, index, phase, beat):
    cols = default_truth(0.0)(split, index, phase, beat)
    cols[:, 0] = 0.0 if split == "train" else (1.0 if index == 0 else math.sqrt(2.0))
    return cols


def _k3_error(seed_index, holdout_index, phase):
    err = default_error((1.0, 1.4, 0.7, 1.2, 0.9))(seed_index, holdout_index, phase)
    alt = np.where(np.arange(phase.shape[0]) % 2 == 0, 1.0, -1.0)
    err[:, 0] = alt * (1 / math.sqrt(2.0) if holdout_index == 0 else 0.5)
    return err


def _k3_drop_rows(df):
    is_a = (df["config_name"] == "h00").to_numpy()
    keep = ~is_a | np.isin(df["phase"].to_numpy(), [0.0, 0.5])
    return df[keep].reset_index(drop=True)


def test_k3_skill_is_pooled_over_rows(tmp_path):
    """Holdout A: 2 rows, SSE_s 1, SSE0 2; B: 4 rows, SSE_s 1, SSE0 8. Pooled skill is 0.8, not
    the per-configuration mean 0.6875 nor the row-weighted mean 0.75."""
    spec_c = CorpusSpec(
        n_holdout=2,
        rows_per_beat=4,
        truth=_k3_truth,
        error=_k3_error,
        edit_dataset=_k3_drop_rows,
    )
    spec_f = CorpusSpec(n_holdout=2, rows_per_beat=4, salt=0.013, digest=FINE_DIGEST)
    write_repo(tmp_path, coarse=spec_c, fine=spec_f)
    result, _ = _build(cf.build_error_histograms, tmp_path)
    skill = result["grids"]["coarse"]["CF_x"]["skill"]
    assert math.isclose(skill, 0.8, rel_tol=1e-12, abs_tol=0)


def test_error_histograms_end_to_end(tmp_path):
    write_repo(tmp_path)
    before = plt.get_fignums()
    result, out = _build(cf.build_error_histograms, tmp_path)
    assert sorted(p.name for p in out.iterdir()) == [
        "error_histograms.png",
        "error_histograms_metrics.json",
        "error_histograms_run_metadata.json",
    ]
    assert plt.get_fignums() == before
    written = json.loads(
        (out / "error_histograms_metrics.json").read_text(encoding="utf-8")
    )
    recomputed = cf.compute_error_histograms_metrics(
        root=tmp_path, coarse_dir=COARSE_DIR, fine_dir=FINE_DIR
    )
    assert written == json.loads(cf._dumps(recomputed)) == json.loads(cf._dumps(result))


# --- cycle_mean_r2_diagnostic ----------------------------------------------------------------

_K1_OFFSETS = (1.0, 3.0, 2.0, 0.5, 1.5)  # per seed; the second gives R^2 = -73/35


def _k1_truth(salt=0.0):
    base = default_truth(salt)

    def truth(split, index, phase, beat):
        cols = base(split, index, phase, beat)
        if split == "holdout":
            cols[:, 0] = float(index + 1)  # true cycle means 1..6
        return cols

    return truth


def _k1_error(offsets=_K1_OFFSETS):
    base = default_error((1.0, 1.4, 0.7, 1.2, 0.9))

    def error(seed_index, holdout_index, phase):
        err = base(seed_index, holdout_index, phase)
        sign = 1.0 if holdout_index % 2 == 0 else -1.0
        alt = np.where(np.arange(phase.shape[0]) % 2 == 0, 0.5, -0.5)
        err[:, 0] = offsets[seed_index] * sign + alt
        return err

    return error


def _k1_repo(root, coarse_extra=None, offsets=_K1_OFFSETS):
    spec = CorpusSpec(
        truth=_k1_truth(), error=_k1_error(offsets), **(coarse_extra or {})
    )
    return write_repo(root, coarse=spec)


def _form_t(a, b):
    return abs(a - b) <= 1e-12 * max(1.0, abs(b))


def test_k1_identity_and_derived_errors(tmp_path):
    written = _k1_repo(tmp_path)
    result, _ = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    entry = result["grids"]["coarse"]["CF_x"]
    metrics = written["coarse"]["metrics"]
    sigma = math.sqrt(35 / 12)
    assert math.isclose(entry["sigma"], sigma, rel_tol=1e-12, abs_tol=0)
    assert math.isclose(entry["eps_primary_measured"], 1.0, rel_tol=1e-12, abs_tol=0)
    r2 = entry["config_mean_r2"]
    assert r2 == [
        r["per_target"]["CF_x"]["config_mean_r2"] for r in metrics["seed_sweep"]["runs"]
    ]
    assert r2[0] == metrics["config_resolved"]["CF_x"]["config_mean_r2"]
    assert _form_t(1 - r2[0], 1 - 23 / 35)
    assert _form_t(1 - r2[1], 1 + 73 / 35)
    for value, eps in zip(r2, entry["eps"], strict=True):
        assert math.isclose(
            eps, entry["sigma"] * math.sqrt(1 - value), rel_tol=1e-12, abs_tol=0
        )
    assert math.isclose(entry["eps"][1], 3.0, rel_tol=1e-12, abs_tol=0)
    assert entry["eps"][1] > entry["sigma"]
    assert _form_t(entry["eps_primary_measured"] ** 2 / entry["sigma"] ** 2, 1 - r2[0])


def test_k1_recorded_r2_is_not_another_block(tmp_path):
    written = _k1_repo(tmp_path)
    result, _ = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    metrics = written["coarse"]["metrics"]
    others = set()
    for c in TARGET_COLUMNS:
        others |= set(metrics["per_target"][c].values())
        others |= {
            v
            for k, v in metrics["phase_baseline_skill"]["per_target"][c].items()
            if isinstance(v, float)
        }
    assert result["grids"]["coarse"]["CF_x"]["config_mean_r2"][0] not in others


def _scale_config_resolved(factor):
    def edit(metrics):
        metrics["config_resolved"]["CF_x"]["config_mean_r2"] *= factor

    return edit


def test_a_recorded_r2_off_by_1e10_is_refused_and_1e14_accepted(tmp_path):
    _k1_repo(tmp_path / "a", {"edit_metrics": _scale_config_resolved(1 + 1e-10)})
    with pytest.raises(ValueError) as excinfo:
        _build(cf.build_cycle_mean_r2_diagnostic, tmp_path / "a")
    for needle in ("coarse", "CF_x", "config_mean_r2"):
        assert needle in str(excinfo.value)
    assert not (tmp_path / "a" / "out").exists()
    _k1_repo(tmp_path / "b", {"edit_metrics": _scale_config_resolved(1 + 1e-14)})
    _build(cf.build_cycle_mean_r2_diagnostic, tmp_path / "b")


def test_a_primary_r2_near_one_is_accepted(tmp_path):
    sigma = math.sqrt(35 / 12)
    offsets = (1e-3 * sigma, 3.0, 2.0, 0.5, 1.5)
    _k1_repo(tmp_path, offsets=offsets)
    result, _ = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    r2 = result["grids"]["coarse"]["CF_x"]["config_mean_r2"][0]
    assert math.isclose(1 - r2, 1e-6, rel_tol=1e-6, abs_tol=0)


def test_boundary_r2_values(tmp_path):
    def edit(runs):
        runs[1]["per_target"]["CF_x"]["config_mean_r2"] = 0.0
        runs[2]["per_target"]["CF_x"]["config_mean_r2"] = 1.0
        runs[3]["per_target"]["CF_x"]["config_mean_r2"] = -1e6

    _k1_repo(tmp_path, {"edit_runs": edit})
    result, _ = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    entry = result["grids"]["coarse"]["CF_x"]
    assert entry["eps"][1] == entry["sigma"]
    assert entry["eps"][2] == 0.0
    assert entry["floor_seeds"] == [1236]
    assert math.isclose(
        entry["eps"][3], entry["sigma"] * math.sqrt(1 + 1e6), rel_tol=1e-12
    )


def _null_truth(salt=0.0):
    base = default_truth(salt)

    def truth(split, index, phase, beat):
        cols = base(split, index, phase, beat)
        if split == "holdout":
            cols[:, 0] = 0.5 + np.where(np.arange(phase.shape[0]) % 2 == 0, 1.0, -1.0)
        return cols

    return truth


def test_a_null_cycle_mean_r2_passes_through_as_null(tmp_path):
    written = write_repo(
        tmp_path,
        coarse=CorpusSpec(truth=_null_truth()),
        fine=_fine(truth=_null_truth(0.013)),
    )
    # in memory the sentinel is NaN; the written metrics.json carries it as null
    assert cf._is_null(
        written["coarse"]["metrics"]["config_resolved"]["CF_x"]["config_mean_r2"]
    )
    assert written["coarse"]["metrics"]["phase_baseline_skill"]["per_target"]["CF_x"][
        "skill"
    ]
    result, _ = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    entry = result["grids"]["coarse"]["CF_x"]
    assert entry["config_mean_r2"] == [None] * 5
    assert entry["eps"] == [None] * 5
    assert entry["sigma"] == 0.0
    assert entry["na"] is True
    assert entry["waveform_rms"] == 1.0
    assert result["grids"]["coarse"]["CF_y"]["na"] is False


def test_diagnostic_caption(tmp_path):
    seeds = (42, 43, 44)
    scales = (1.0, 1.3, 0.8)
    write_repo(
        tmp_path,
        coarse=CorpusSpec(seeds=seeds, error_scales=scales),
        fine=_fine(seeds=seeds, error_scales=scales),
    )
    result, _ = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    caption = result["caption"]
    for phrase in (
        cf.SHIPPED_PHRASE,
        cf.LAB_FRAME_PHRASE,
        "3 seeds",
        "observed spread, not a confidence interval",
        "a diagnostic of the metric, not a comparison of the grids",
        "cycle-mean R² is computed on each grid's own 6 holdout configurations",
        "second wingbeat of 2-beat runs",
        cf.REGENERATION_PHRASE,
    ):
        assert phrase in caption, phrase
    assert cf.OWN_BASELINE_PHRASE not in caption
    assert "1234" not in caption and "5 seeds" not in caption
    _assert_clean_wording(caption, *result["labels"])


def test_diagnostic_caption_for_a_four_beat_corpus(tmp_path):
    write_repo(tmp_path, coarse=CorpusSpec(n_beats=4), fine=_fine(n_beats=4))
    result, _ = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    assert "wingbeats 2–4 of 4-beat runs" in result["caption"]
    assert cf.REGENERATION_PHRASE not in result["caption"]


def test_cycle_mean_r2_diagnostic_end_to_end(tmp_path):
    write_repo(tmp_path)
    before = plt.get_fignums()
    result, out = _build(cf.build_cycle_mean_r2_diagnostic, tmp_path)
    assert sorted(p.name for p in out.iterdir()) == [
        "cycle_mean_r2_diagnostic.png",
        "cycle_mean_r2_diagnostic_metrics.json",
        "cycle_mean_r2_diagnostic_run_metadata.json",
    ]
    assert plt.get_fignums() == before
    written = json.loads(
        (out / "cycle_mean_r2_diagnostic_metrics.json").read_text(encoding="utf-8")
    )
    recomputed = cf.compute_cycle_mean_r2_diagnostic_metrics(
        root=tmp_path, coarse_dir=COARSE_DIR, fine_dir=FINE_DIR
    )
    assert written == json.loads(cf._dumps(recomputed)) == json.loads(cf._dumps(result))
