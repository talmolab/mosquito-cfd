"""Committed surrogates and evidence figures are tied to their inputs and to a real commit.

fix-moment-reference-hinge PR3 retrains ``examples/prelim_sweep/surrogate/`` and regenerates the
evidence figure; add-fine-corpus-surrogate (#110) adds the same artifacts for
``examples/prelim_sweep_fine/``. These tests reconcile each corpus's committed artifacts against
the files they were produced from, unconditionally -- no state passes with a mismatch:

- every ``<target>_true`` in the holdout predictions equals ``dataset.parquet``, for all six
  targets;
- the surrogate's ``run_metadata.json`` names the dataset by sha256 and the corpus's image;
- the figure's ``run_metadata.json`` names the holdout predictions and ``metrics.json`` by sha256;
- every regenerated record carries a real git commit from a clean tree, not the
  ``git.error`` the pre-#78 surrogate record holds;
- the committed seed-variation record agrees with the committed coarse surrogate, and the coarse
  README's 5-seed table is that record's min/max (coarse only: the record exists only there);
- the fine README's tables and disclosures agree with the committed JSON and cited sources.

Fine parametrizations are strict-xfailed (``raises=FileNotFoundError/AssertionError``) until their
artifacts land: surrogate-only checks in C4, figure and README checks in C5 (design D6). The
README checks live in ``_readme_guards`` and are exercised on synthetic inputs below.

The recorded commits do not survive the squash-merge as ancestors of ``main``; they stay
resolvable via ``refs/pull/<n>/head``. Branch names are deliberately not pinned, so a later
regeneration (#114, #125) does not have to edit this file.
"""

import copy
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from _readme_guards import (
    COMPARISON_HEADER,
    COMPARISON_HEADING,
    CYCLE_MEAN_HEADER,
    R2_NEAR_TARGET,
    SKILL_HEADER,
    check_comparison_table,
    check_cycle_mean_table,
    check_fine_denominator,
    check_fine_disclosures,
    check_fine_qs_disclosure,
    check_quoted_in_source,
    check_skill_table,
    overlap_cell,
    parse_table,
)

from mosquito_cfd.force_surrogate.cfd_cost import median_cfd_seconds_per_wingbeat
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
FINE = REPO / "examples" / "prelim_sweep_fine"
SURROGATE = COARSE / "surrogate"
FIGURES = COARSE / "figures"
RESULTS_MD = REPO / "examples" / "flapping_wing" / "RESULTS.md"
_HEX40 = re.compile(r"[0-9a-f]{40}")

# The fine artifacts do not exist until C4 (surrogate) / C5 (figure + README).
_FINE_SURROGATE_PENDING = pytest.mark.xfail(
    strict=True,
    raises=(FileNotFoundError, AssertionError),
    reason="#110: fine surrogate artifacts land in C4",
)
_FINE_FIGURE_PENDING = pytest.mark.xfail(
    strict=True,
    raises=(FileNotFoundError, AssertionError),
    reason="#110: fine figure and README land in C5",
)


def _corpora(fine_mark):
    """Parametrize over both corpora, the fine one carrying ``fine_mark``."""
    return pytest.mark.parametrize(
        "corpus",
        [
            pytest.param(COARSE, id="coarse"),
            pytest.param(FINE, id="fine", marks=fine_mark),
        ],
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _readme(corpus: Path) -> str:
    return (corpus / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "record",
    [
        pytest.param(SURROGATE / "run_metadata.json", id="surrogate"),
        pytest.param(FIGURES / "run_metadata.json", id="figure"),
        pytest.param(COARSE / "run_metadata.json", id="coarse-corpus"),
        pytest.param(FINE / "run_metadata.json", id="fine-corpus"),
        pytest.param(
            FINE / "surrogate" / "run_metadata.json",
            id="fine-surrogate",
            marks=_FINE_SURROGATE_PENDING,
        ),
        pytest.param(
            FINE / "figures" / "run_metadata.json",
            id="fine-figure",
            marks=_FINE_FIGURE_PENDING,
        ),
    ],
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


@_corpora(_FINE_SURROGATE_PENDING)
def test_surrogate_holdout_targets_equal_the_committed_dataset(corpus):
    """Every holdout ``<target>_true``, for all six targets, is the committed dataset's value.

    A surrogate trained on any other corpus -- including the pre-#108 parquet, which differs only
    in CF_mx/CF_mz -- fails, naming the target.
    """
    holdout = pd.read_parquet(corpus / "surrogate" / "holdout_predictions.parquet")
    dataset = pd.read_parquet(
        corpus / "dataset.parquet", columns=["config_name", "time", *TARGET_COLUMNS]
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


@_corpora(_FINE_SURROGATE_PENDING)
def test_surrogate_metadata_names_the_committed_dataset(corpus):
    """The surrogate's provenance hashes the exact committed dataset it was trained on."""
    inputs = _meta(corpus / "surrogate" / "run_metadata.json").get("inputs")
    assert inputs, "surrogate run_metadata.json records no training dataset"
    assert Path(inputs["file"].replace("\\", "/")).name == "dataset.parquet", inputs
    assert inputs["hash"] == _sha256(corpus / "dataset.parquet")


@_corpora(_FINE_SURROGATE_PENDING)
def test_surrogate_trained_with_the_coarse_settings(corpus):
    """Both surrogates use the coarse run's settings and their own corpus's image (#110).

    Seeds 1234 then 1235-1238, 2000 epochs, 3 validation configs per run, the data-producing
    image of the corpus, and no GPU-bitwise claim (``bitwise`` stays ``cpu_only``).
    """
    metrics = _meta(corpus / "surrogate" / "metrics.json")
    sweep = metrics["seed_sweep"]
    assert sweep["seeds"] == [1234, 1235, 1236, 1237, 1238]
    reproducibility = metrics["reproducibility"]
    assert reproducibility["epochs"] == 2000
    assert reproducibility["bitwise"] == "cpu_only"
    for run in sweep["runs"]:
        assert len(run["val_configs"]) == 3, run["seed"]
    surrogate_image = _meta(corpus / "surrogate" / "run_metadata.json")["docker_image"]
    assert surrogate_image == _meta(corpus / "run_metadata.json")["docker_image"]


@_corpora(_FINE_FIGURE_PENDING)
def test_figure_metadata_names_the_committed_surrogate_outputs(corpus):
    """The figure's provenance hashes the committed predictions and metrics it was drawn from,
    and names the grid and CFD cost the sidecar used (absent on the pre-#110 coarse record,
    which reads as coarse / 144 s)."""
    meta = _meta(corpus / "figures" / "run_metadata.json")
    surrogate = corpus / "surrogate"
    assert meta["inputs"]["hash"] == _sha256(surrogate / "holdout_predictions.parquet")
    assert meta["metrics_json_sha256"] == _sha256(surrogate / "metrics.json")
    sidecar = _meta(corpus / "figures" / "evidence_figure_metrics.json")
    expected_grid = "fine" if corpus == FINE else "coarse"
    assert meta.get("grid", "coarse") == expected_grid
    assert (
        meta.get("cfd_seconds_per_wingbeat", 144.0)
        == sidecar["speedup"]["cfd_seconds_per_wingbeat"]
    )


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


def _dataset(corpus: Path) -> pd.DataFrame:
    return filter_converged_beat(pd.read_parquet(corpus / "dataset.parquet"))


@_corpora(_FINE_SURROGATE_PENDING)
def test_committed_seed_sweep_is_internally_consistent(corpus):
    """The committed sweep agrees with itself, the run record and the dataset.

    ``seed_sweep.seeds`` is the primary seed then run_metadata's sweep seeds; the primary run
    entry's statistics equal the top-level blocks; each run's ``val_configs`` is the split
    recomputed from the dataset for that seed. Not a GPU-bitwise pin (design D5): nothing here
    asserts a sweep seed's metrics against a hand record.
    """
    metrics = _meta(corpus / "surrogate" / "metrics.json")
    seeds = _meta(corpus / "surrogate" / "run_metadata.json")["seeds"]
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

    dataset = _dataset(corpus)
    for run in sweep["runs"]:
        split = make_config_splits(dataset, seed=run["seed"])
        assert run["val_configs"] == split.val_configs, run["seed"]


@_corpora(_FINE_SURROGATE_PENDING)
def test_committed_phase_baseline_skill_recomputes(corpus):
    """phase_baseline_skill recomputed from the committed dataset and predictions matches.

    Catches a row misalignment inside run_training: the baseline is rebuilt at the committed
    predictions' phases and scored against their true and predicted columns.
    """
    metrics = _meta(corpus / "surrogate" / "metrics.json")["phase_baseline_skill"]
    holdout = pd.read_parquet(corpus / "surrogate" / "holdout_predictions.parquet")
    dataset = _dataset(corpus)
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
_SKILL_HEADER = SKILL_HEADER


def test_skill_and_config_r2_table_patterns_cannot_cross_match():
    """Each README table guard reads only its own table, and neither reads the header.

    The two coarse regexes cannot match each other's rows; the header-scoped tables
    (``_readme_guards.parse_table``) have four distinct headers, and in a README holding all four
    tables each header yields only its own rows.
    """
    skill_row = "| `CF_x` | 0.988 | 0.988 to 0.992 | 0.955 |"
    config_row = "| `CF_x` | -4.17 to 0.09 | -0.01 to 0.09 |"
    assert _SKILL_ROW.search(skill_row) and not _TABLE_ROW.search(skill_row)
    assert _TABLE_ROW.search(config_row) and not _SKILL_ROW.search(config_row)
    for pattern in (_SKILL_ROW, _TABLE_ROW):
        assert not pattern.search(_SKILL_HEADER)
    seed_header = "| target | hinge-referenced, 5 seeds | pre-#108, 5 seeds |"
    headers = (SKILL_HEADER, CYCLE_MEAN_HEADER, COMPARISON_HEADER, seed_header)
    assert len(set(headers)) == 4
    widths = {
        SKILL_HEADER: 3,
        CYCLE_MEAN_HEADER: 1,
        COMPARISON_HEADER: 3,
        seed_header: 2,
    }
    marker = {h: f"table{i}" for i, h in enumerate(headers)}
    text = "\n\n".join(
        "\n".join(
            [h, "|---|"]
            + [
                f"| `{c}` | " + " | ".join([marker[h]] * widths[h]) + " |"
                for c in TARGET_COLUMNS
            ]
        )
        for h in headers
    )
    for h in headers:
        rows = parse_table(text, h)
        assert {tuple(cells) for cells in rows.values()} == {(marker[h],) * widths[h]}


@_corpora(_FINE_FIGURE_PENDING)
def test_readme_skill_table_is_metrics_json(corpus):
    """The README's skill table is metrics.json, for all six targets, as the figure prints it."""
    readme = _readme(corpus)
    assert _SKILL_HEADER in readme
    check_skill_table(readme, _meta(corpus / "surrogate" / "metrics.json"))
    if corpus == COARSE:
        # the coarse table also still matches the original row regex (format unchanged)
        assert len(_SKILL_ROW.findall(readme)) == len(TARGET_COLUMNS)


# --- Fine-only guards (add-fine-corpus-surrogate, design D5/D6) ----------------------------


@_FINE_FIGURE_PENDING
def test_fine_cfd_cost_is_the_recomputed_median():
    """Scenario: The committed fine denominator is the recomputed median."""
    sidecar = _meta(FINE / "figures" / "evidence_figure_metrics.json")
    result = median_cfd_seconds_per_wingbeat(sorted(FINE.glob("run_metadata_*.json")))
    assert result["n_configs"] == 27
    assert (
        sidecar["speedup"]["cfd_seconds_per_wingbeat"] == result["seconds_per_wingbeat"]
    )


@_FINE_FIGURE_PENDING
def test_fine_readme_cycle_mean_table_and_no_config_r2_prose():
    """Scenario: The cycle-mean and skill tables are the fine metrics file; and no `CF_c ≈v`
    prose (checked after the positive table check, so it cannot pass vacuously early)."""
    readme = _readme(FINE)
    check_cycle_mean_table(readme, _meta(FINE / "surrogate" / "metrics.json"))
    normalized = re.sub(r"([≈=])\s+", r"\1", readme.replace("−", "-"))
    assert R2_NEAR_TARGET.findall(normalized) == []


@_FINE_FIGURE_PENDING
def test_fine_readme_comparison_table_follows_the_overlap_rule():
    """Scenarios: The comparison table is the two metrics files; Only disjoint ranges are
    described as a difference."""
    check_comparison_table(
        _readme(FINE),
        _meta(SURROGATE / "metrics.json"),
        _meta(FINE / "surrogate" / "metrics.json"),
    )


@_FINE_FIGURE_PENDING
def test_fine_readme_discloses_validation_status_qs_reference_and_cost():
    """Scenarios: The fine README states what "not validated" means; The fine README discloses
    the quasi-steady reference. Fixed numbers are checked verbatim in their cited source."""
    readme = _readme(FINE)
    sidecar = _meta(FINE / "figures" / "evidence_figure_metrics.json")
    check_fine_disclosures(readme)
    check_quoted_in_source(
        readme, RESULTS_MD.read_text(encoding="utf-8"), ("3.7 %", "27.6 %")
    )
    check_fine_qs_disclosure(readme, sidecar)
    check_fine_denominator(readme, sidecar)


# --- Synthetic tests of the guard helpers (run now, before any fine artifact) --------------


def _synthetic_metrics() -> tuple[dict, dict]:
    """Coarse committed metrics and a 'fine' copy with CF_x shifted so its range is disjoint."""
    coarse = _meta(SURROGATE / "metrics.json")
    fine = copy.deepcopy(coarse)
    rng = fine["seed_sweep"]["range"]["CF_x"]["skill"]
    rng["min"], rng["max"] = 0.5, 0.6
    return coarse, fine


def _synthetic_readme(coarse: dict, fine: dict, **overrides: str) -> str:
    """A README that every fine guard accepts; ``overrides`` replace one named part."""

    def skill_rows() -> str:
        out = [SKILL_HEADER, "|---|---|---|---|"]
        for c in TARGET_COLUMNS:
            s = fine["phase_baseline_skill"]["per_target"][c]
            r = fine["seed_sweep"]["range"][c]["skill"]
            out.append(
                f"| `{c}` | {format_metric(s['skill'])} | {format_metric(r['min'])} to "
                f"{format_metric(r['max'])} | {format_metric(s['phase_baseline_r2'])} |"
            )
        return "\n".join(out)

    def cycle_rows() -> str:
        out = [CYCLE_MEAN_HEADER, "|---|---|"]
        for c in TARGET_COLUMNS:
            r = fine["seed_sweep"]["range"][c]["config_mean_r2"]
            lo, hi = (f"{v:.2f}".replace("-", "−") for v in (r["min"], r["max"]))
            out.append(f"| `{c}` | {lo} to {hi} |")
        return "\n".join(out)

    def comparison_rows() -> str:
        out = [COMPARISON_HEADER, "|---|---|---|---|"]
        for c in TARGET_COLUMNS:
            rc = coarse["seed_sweep"]["range"][c]["skill"]
            rf = fine["seed_sweep"]["range"][c]["skill"]
            out.append(
                f"| `{c}` | {format_metric(rc['min'])} to {format_metric(rc['max'])} | "
                f"{format_metric(rf['min'])} to {format_metric(rf['max'])} | "
                f"{overlap_cell(rc, rf)} |"
            )
        return "\n".join(out)

    parts = {
        "skill": skill_rows(),
        "cycle": cycle_rows(),
        "comparison": comparison_rows(),
        "prose": (
            "`CF_x` skill is lower on fine across 5 seeds. For every other target: no shift "
            "detected. Each grid is scored against its own corpus's phase-only baseline."
        ),
        "disclosures": (
            "Skill = 1 − MSE/MSE₀ over the phase-only baseline. The figure shows agreement "
            "with CFD, not with experiment; grid convergence was checked only at one wing "
            "motion outside this sweep (GCI_fine 3.7 % and 27.6 %, "
            "examples/flapping_wing/RESULTS.md). Moments are **lab-frame** components about "
            "the hinge; the wing-frame conversion is not currently tracked. The CFD cost is "
            "the median of 4,375 s per wingbeat and includes plotfile output; the force-only "
            "rate is in docs/force_surrogate/fine-grid-pilot-report.md."
        ),
        "qs": (
            "The uncalibrated, translational-only quasi-steady model (symmetric-rotation AoA, "
            "stroke-plane-normal lift vs lab-z CFD) is ~0.7× the CFD lift and is not overlaid."
        ),
    }
    parts.update(overrides)
    return (
        f"# Fine\n\n{parts['disclosures']}\n\n{parts['qs']}\n\n{parts['skill']}\n\n"
        f"{parts['cycle']}\n\n## {COMPARISON_HEADING}\n\n{parts['comparison']}\n\n"
        f"{parts['prose']}\n\n## Regenerating\n\ncommands\n"
    )


_SYNTHETIC_SIDECAR = {
    "quasi_steady_reference": {"overshoot_factor": 0.71},
    "speedup": {"cfd_seconds_per_wingbeat": 4375.093773443361},
}
_SYNTHETIC_SOURCE = "| GCI_fine | 3.7 % |\n| GCI_fine | 27.6 % |"


def _all_guards(readme: str, coarse: dict, fine: dict) -> None:
    check_skill_table(readme, fine)
    check_cycle_mean_table(readme, fine)
    check_comparison_table(readme, coarse, fine)
    check_fine_disclosures(readme)
    check_quoted_in_source(readme, _SYNTHETIC_SOURCE, ("3.7 %", "27.6 %"))
    check_fine_qs_disclosure(readme, _SYNTHETIC_SIDECAR)
    check_fine_denominator(readme, _SYNTHETIC_SIDECAR)


def test_guards_accept_a_correct_synthetic_readme():
    coarse, fine = _synthetic_metrics()
    _all_guards(_synthetic_readme(coarse, fine), coarse, fine)


def _replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _defects(coarse: dict, fine: dict) -> dict[str, str]:
    good = _synthetic_readme(coarse, fine)
    cmp_y = next(
        line
        for line in good.splitlines()
        if line.startswith("| `CF_y` |") and line.endswith("| yes |")
    )
    skill_y = next(
        line
        for line in good.splitlines()
        if line.startswith("| `CF_y` |") and line.count("|") == 5 and "yes" not in line
    )
    cycle_z = next(
        line
        for line in good.splitlines()
        if line.startswith("| `CF_z` |") and line.count("|") == 3
    )
    lo_y = fine["seed_sweep"]["range"]["CF_y"]["skill"]["min"]
    off_by_0001 = cmp_y.replace(
        f"| {format_metric(lo_y)} to", f"| {format_metric(lo_y + 0.001)} to", 1
    )
    assert off_by_0001 != cmp_y
    return {
        "flipped overlap cell": _replace_once(
            good, cmp_y, cmp_y[: -len("yes |")] + "no |"
        ),
        "comparison range off by 0.001": _replace_once(good, cmp_y, off_by_0001),
        "missing comparison row": _replace_once(good, cmp_y + "\n", ""),
        "missing skill row": _replace_once(good, skill_y + "\n", ""),
        "perturbed skill cell": _replace_once(
            good, skill_y, skill_y.replace("0.9", "0.8", 1)
        ),
        "cycle-mean range off by 0.01": _replace_once(
            good, cycle_z, cycle_z.replace(" to ", " to 9", 1)
        ),
        "missing cycle-mean row": _replace_once(good, cycle_z + "\n", ""),
        "disjoint target not named": _replace_once(
            good, "`CF_x` skill is lower on fine across 5 seeds. ", ""
        ),
        "overlapping target called higher": _replace_once(
            good,
            "For every other",
            "`CF_y` is higher on fine across 5 seeds. For every other",
        ),
        "free-form comparative": _replace_once(
            good, "lower on fine across 5 seeds", "lower on fine"
        ),
        "banned word improves": _replace_once(
            good, "For every other", "Skill improves. Every other"
        ),
        "banned word drop": _replace_once(
            good, "For every other", "A drop. Every other"
        ),
        "shift used loosely": _replace_once(
            good, "For every other", "A small shift. Every other"
        ),
        "missing 3.7 %": _replace_once(good, "3.7 % and ", ""),
        "missing pilot report": _replace_once(
            good, "docs/force_surrogate/fine-grid-pilot-report.md", "the pilot report"
        ),
        "2.4x claim": _replace_once(good, "# Fine", "# Fine ~2.4× low"),
        "pitch moment": _replace_once(
            good, "Moments are", "The pitch moment and moments are"
        ),
        "QS ratio differs": _replace_once(good, "~0.7×", "~0.8×"),
        "QS nature missing": _replace_once(good, "symmetric-rotation AoA, ", ""),
        "denominator differs": _replace_once(good, "4,375 s", "4,376 s"),
        "denominator ratio stated": _replace_once(
            good, "per wingbeat and", "per wingbeat (30× the coarse) and"
        ),
    }


@pytest.mark.parametrize(
    "defect",
    [
        "flipped overlap cell",
        "comparison range off by 0.001",
        "missing comparison row",
        "missing skill row",
        "perturbed skill cell",
        "cycle-mean range off by 0.01",
        "missing cycle-mean row",
        "disjoint target not named",
        "overlapping target called higher",
        "free-form comparative",
        "banned word improves",
        "banned word drop",
        "shift used loosely",
        "missing 3.7 %",
        "missing pilot report",
        "2.4x claim",
        "pitch moment",
        "QS ratio differs",
        "QS nature missing",
        "denominator differs",
        "denominator ratio stated",
    ],
)
def test_guards_reject_each_defect_with_assertion_error(defect):
    coarse, fine = _synthetic_metrics()
    readme = _defects(coarse, fine)[defect]
    with pytest.raises(AssertionError):
        _all_guards(readme, coarse, fine)


def test_guards_reject_a_null_range_not_shown_as_na():
    coarse, fine = _synthetic_metrics()
    good = _synthetic_readme(coarse, fine)
    fine_null = copy.deepcopy(fine)
    fine_null["seed_sweep"]["range"]["CF_y"]["skill"] = None
    with pytest.raises(AssertionError):
        check_comparison_table(good, coarse, fine_null)
    assert overlap_cell(coarse["seed_sweep"]["range"]["CF_y"]["skill"], None) == "n/a"


def test_touching_ranges_count_as_overlapping():
    assert overlap_cell({"min": 0.1, "max": 0.5}, {"min": 0.5, "max": 0.9}) == "yes"
    assert overlap_cell({"min": 0.1, "max": 0.5}, {"min": 0.50001, "max": 0.9}) == "no"


@pytest.mark.parametrize(
    "guard",
    [
        lambda r: check_skill_table(r, _meta(SURROGATE / "metrics.json")),
        lambda r: check_cycle_mean_table(r, _meta(SURROGATE / "metrics.json")),
        lambda r: check_comparison_table(
            r, _meta(SURROGATE / "metrics.json"), _meta(SURROGATE / "metrics.json")
        ),
        check_fine_disclosures,
        lambda r: check_fine_qs_disclosure(r, _SYNTHETIC_SIDECAR),
        lambda r: check_fine_denominator(r, _SYNTHETIC_SIDECAR),
    ],
    ids=["skill", "cycle-mean", "comparison", "disclosures", "qs", "denominator"],
)
def test_guards_raise_assertion_error_on_a_readme_without_tables(guard):
    """On a README with no tables (like today's fine one) every guard raises AssertionError,
    never AttributeError/KeyError/IndexError, so the fine xfail markers stay meaningful."""
    with pytest.raises(AssertionError):
        guard("# Fine\n\nNot yet built.\n")
