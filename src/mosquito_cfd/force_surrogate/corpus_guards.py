"""Cluster-free reconciliation guards for committed force-surrogate corpora (issue #20).

Every prior check on a committed corpus was an **internal-consistency** check: no NaN, ranges
sane, N configs present, coefficients consistent with forces. All of those passed on the
defective fine-grid corpus that motivated this module (issues #92/#94) — they ask "does the data
agree with itself?", which cannot detect a wrong artifact. These guards instead reconcile each
corpus against its own **manifest** (an external reference) and against a **physical invariant**
(settled-wingbeat cycle symmetry), which is what actually catches truncation and duplicate rows.

Runs fully offline: no cluster, GPU, Argo, or subprocess access. Every function here reads only
committed files under the repository root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.sidecar import (
    load_json_clear_error,
    read_units_sidecar,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# Settled-beat (wingbeat >= 1) |mean CF_x| / max|CF_x|: non-truncated configs across both
# committed corpora measure [-0.0091, +0.0001]; the fine corpus's 9 materially-truncated configs
# measure [+0.0150, +0.1648]. 0.012 sits with ~1.3x margin on the healthy side and ~1.25x margin
# on the truncated side (see add-fine-corpus-run-verification design.md D6).
SYMMETRY_RATIO_TOLERANCE = 0.012

# Confirmed against the regenerated (real, non-CFL-truncated) fine corpus (task 8.7): the measured
# max |CF_x| for wingbeat > 0 across both committed corpora is 4.015 (prelim_sweep's
# s35_f085_p60), unchanged from when this tripwire was first set -- prelim_sweep_fine's own true
# max is 2.880 (also s35_f085_p60), comfortably lower now that its data isn't corrupted by
# truncation. 5.0 sits at the same ~1.25x margin convention as SYMMETRY_RATIO_TOLERANCE, so the
# margin does not support tightening further; this tripwire is a coarse guard against a
# materially different physical regime, not a tight bound.
CONVERGED_BEAT_CF_X_TRIPWIRE = 5.0


@dataclass(frozen=True)
class CorpusEntry:
    """One committed corpus's registry entry -- see the module docstring for why this is an explicit list, not a directory glob."""

    name: str
    path: Path
    has_parquet: bool
    has_per_config_metadata: bool


# Explicit list, not a glob over `examples/prelim_sweep*`: that pattern also matches
# `prelim_sweep_fine_pilot` (3 configs, no parquet) -- a glob-driven guard would silently skip
# exactly the corpus it exists to protect.
CORPUS_REGISTRY: tuple[CorpusEntry, ...] = (
    CorpusEntry(
        name="prelim_sweep",
        path=REPO_ROOT / "examples" / "prelim_sweep",
        has_parquet=True,
        has_per_config_metadata=False,
    ),
    CorpusEntry(
        name="prelim_sweep_fine",
        path=REPO_ROOT / "examples" / "prelim_sweep_fine",
        has_parquet=True,
        has_per_config_metadata=True,
    ),
)


def _load_manifest(entry: CorpusEntry) -> dict:
    return load_json_clear_error(
        entry.path / "sweep_manifest.json", label="sweep manifest"
    )


def _parse_deck_max_step(deck_path: Path) -> int:
    text = deck_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        key, _, value = line.partition("#")[0].partition("=")
        if key.strip() == "max_step":
            return int(value.strip())
    raise ValueError(f"deck {deck_path} has no max_step key")


def check_deck_matches_manifest_max_step(entry: CorpusEntry) -> list[str]:
    """Each config's generated deck `max_step` equals its manifest `max_step` -- two currently unchecked sources of truth."""
    manifest = _load_manifest(entry)
    failures = []
    for config in manifest["configs"]:
        deck_path = entry.path / config["input_file"]
        deck_max_step = _parse_deck_max_step(deck_path)
        if deck_max_step != config["max_step"]:
            failures.append(
                f"{entry.name}/{config['name']}: deck max_step={deck_max_step} != "
                f"manifest max_step={config['max_step']}"
            )
    return failures


def check_holdout_matches_manifest(entry: CorpusEntry) -> list[str]:
    """The parquet's `split == "holdout"` configuration names equal the manifest's recorded holdout names exactly."""
    if not entry.has_parquet:
        return []
    manifest = _load_manifest(entry)
    expected = set(manifest["holdout"]["config_names"])
    df = pd.read_parquet(entry.path / "dataset.parquet")
    actual = set(df[df["split"] == "holdout"]["config_name"].unique())
    if actual != expected:
        return [
            f"{entry.name}: parquet holdout set {sorted(actual)} != manifest holdout set "
            f"{sorted(expected)}"
        ]
    return []


def check_parquet_row_counts(entry: CorpusEntry) -> list[str]:
    """Each configuration's parquet row count equals its manifest `max_step`, reconciled against the manifest -- not against the data's own row count (which is what let #94's duplicate rows through undetected)."""
    if not entry.has_parquet:
        return []
    manifest = _load_manifest(entry)
    df = pd.read_parquet(entry.path / "dataset.parquet")
    counts = df["config_name"].value_counts()
    failures = []
    for config in manifest["configs"]:
        actual = int(counts.get(config["name"], 0))
        if actual != config["max_step"]:
            failures.append(
                f"{entry.name}/{config['name']}: parquet rows={actual} != "
                f"manifest max_step={config['max_step']}"
            )
    return failures


def check_time_strictly_increasing(entry: CorpusEntry) -> list[str]:
    """`time` is strictly increasing within each configuration (the #94 duplicate-row symptom)."""
    if not entry.has_parquet:
        return []
    df = pd.read_parquet(entry.path / "dataset.parquet")
    failures = []
    for name, group in df.groupby("config_name"):
        times = group.sort_index()["time"].to_numpy()
        if not np.all(np.diff(times) > 0):
            failures.append(f"{entry.name}/{name}: time is not strictly increasing")
    return failures


def check_no_nan_or_inf(entry: CorpusEntry) -> list[str]:
    """No NaN or Inf in any numeric column."""
    if not entry.has_parquet:
        return []
    df = pd.read_parquet(entry.path / "dataset.parquet")
    numeric = df.select_dtypes(include=[np.number])
    if numeric.isna().to_numpy().any() or np.isinf(numeric.to_numpy()).any():
        return [f"{entry.name}: NaN or Inf present in a numeric column"]
    return []


def check_units_match_parquet(entry: CorpusEntry) -> list[str]:
    """The units sidecar's key set equals the parquet's measured (non-categorical) column set."""
    if not entry.has_parquet:
        return []
    non_measured = {"config_name", "split", "index", "wingbeat"}
    df = pd.read_parquet(entry.path / "dataset.parquet")
    measured = {c for c in df.columns if c not in non_measured}
    units = read_units_sidecar(entry.path / "dataset.units.json")
    if set(units) != measured:
        return [
            f"{entry.name}: units sidecar keys {sorted(units)} != measured columns "
            f"{sorted(measured)}"
        ]
    return []


def check_per_config_metadata_present(entry: CorpusEntry) -> list[str]:
    """Every parquet configuration has a corresponding `run_metadata_<config>.json` -- scoped to corpora that declare per-config metadata (the coarse corpus has none; only a dataset-build `run_metadata.json`)."""
    if not entry.has_per_config_metadata or not entry.has_parquet:
        return []
    manifest = _load_manifest(entry)
    failures = []
    for config in manifest["configs"]:
        metadata_path = entry.path / f"run_metadata_{config['name']}.json"
        if not metadata_path.exists():
            failures.append(f"{entry.name}/{config['name']}: no run_metadata file")
    return failures


def settled_beat_symmetry_ratios(df: pd.DataFrame) -> dict[str, float]:
    """Per-config |mean CF_x| / max|CF_x| over the settled beat (wingbeat >= 1, time > 0).

    A config with zero settled-beat rows (a run so short it never reaches ``wingbeat >= 1`` --
    the single worst truncation case) is simply absent from the returned dict; the caller must
    check for a manifest config missing from the result rather than treating absence as "no
    issue" (see :func:`check_symmetry_invariant` and
    ``acceptance_gate.run_acceptance_gate``, which both do). Shared by both modules rather than
    duplicated, so the ratio definition cannot silently drift between them (review round 1 on
    PR #97).
    """
    settled = df[(df["wingbeat"] >= 1) & (df["time"] > 0)]
    ratios: dict[str, float] = {}
    for name, group in settled.groupby("config_name"):
        peak = group["CF_x"].abs().max()
        if peak == 0:
            continue
        ratios[str(name)] = abs(group["CF_x"].mean()) / peak
    return ratios


def check_symmetry_invariant(entry: CorpusEntry) -> list[str]:
    """Settled-wingbeat normalized cycle-symmetry ratio is within tolerance -- the physical invariant that catches truncation, which no internal-consistency check can (design D6)."""
    if not entry.has_parquet:
        return []
    manifest = _load_manifest(entry)
    df = pd.read_parquet(entry.path / "dataset.parquet")
    ratios = settled_beat_symmetry_ratios(df)
    failures = []
    for config in manifest["configs"]:
        name = config["name"]
        if name not in ratios:
            failures.append(
                f"{entry.name}/{name}: no settled-beat (wingbeat >= 1) rows found; cannot "
                "evaluate the symmetry invariant -- likely severely truncated"
            )
            continue
        ratio = ratios[name]
        if ratio > SYMMETRY_RATIO_TOLERANCE:
            failures.append(
                f"{entry.name}/{name}: normalized symmetry ratio {ratio:.4f} exceeds tolerance "
                f"{SYMMETRY_RATIO_TOLERANCE} (likely truncated -- settled beat is incomplete)"
            )
    return failures


def check_converged_beat_tripwire(entry: CorpusEntry) -> list[str]:
    """`|CF_x| < 5` for the settled beat (`wingbeat > 0`) -- provisional, see the module docstring."""
    if not entry.has_parquet:
        return []
    df = pd.read_parquet(entry.path / "dataset.parquet")
    settled = df[df["wingbeat"] > 0]
    peak = settled["CF_x"].abs().max()
    if peak >= CONVERGED_BEAT_CF_X_TRIPWIRE:
        return [
            f"{entry.name}: settled-beat |CF_x| peak {peak:.3f} >= tripwire "
            f"{CONVERGED_BEAT_CF_X_TRIPWIRE}"
        ]
    return []


def check_parquet_exists_if_registered(entry: CorpusEntry) -> list[str]:
    """A corpus registered `has_parquet=True` but missing one on disk fails loudly, rather than every parquet-tier check above silently returning `[]` for a "no parquet" reason that is actually a registry/build mismatch, not "not yet applicable"."""
    if entry.has_parquet and not (entry.path / "dataset.parquet").exists():
        return [
            f"{entry.name}: registered has_parquet=True but no dataset.parquet found"
        ]
    return []


#: Every guard, in the order the module docstring's scenarios list them.
ALL_CHECKS = (
    check_parquet_exists_if_registered,
    check_deck_matches_manifest_max_step,
    check_holdout_matches_manifest,
    check_parquet_row_counts,
    check_time_strictly_increasing,
    check_no_nan_or_inf,
    check_units_match_parquet,
    check_per_config_metadata_present,
    check_symmetry_invariant,
    check_converged_beat_tripwire,
)


def run_all_guards(entry: CorpusEntry) -> list[str]:
    """Run every guard against ``entry``, returning the combined list of failure messages (empty if the corpus passes all of them)."""
    failures: list[str] = []
    for check in ALL_CHECKS:
        failures.extend(check(entry))
    return failures
