"""Post-run acceptance gate for a force-surrogate corpus (design.md D6).

Runs **after** ``generate_run_metadata.py`` and **before** ``extract_forces.py``, so a
defective run (#92's CFL truncation, #94's duplicate rows) can never reach a committed
``dataset.parquet``. Recomputes its row-count and physical-invariant checks directly from the raw
force CSVs via :func:`mosquito_cfd.force_surrogate.dataset.build_dataset` -- the same code path
that will build the real dataset -- rather than trusting every value the metadata it is gating
already claims (a metadata-generation bug cannot certify its own corpus).

The only value taken on trust from ``run_metadata_<config>.json`` is
``interior_dt_below_nominal``, which cannot be recomputed offline without the run's ``run.log``
(not committed); everything else here is independently derived from the manifest and the raw
CSVs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from mosquito_cfd.force_surrogate.corpus_guards import SYMMETRY_RATIO_TOLERANCE
from mosquito_cfd.force_surrogate.dataset import build_dataset


@dataclass(frozen=True)
class GateResult:
    """The acceptance gate's verdict."""

    passed: bool
    failures: tuple[str, ...] = field(default_factory=tuple)


def _settled_beat_symmetry_ratios(df) -> dict[str, float]:
    settled = df[(df["wingbeat"] >= 1) & (df["time"] > 0)]
    ratios: dict[str, float] = {}
    for name, group in settled.groupby("config_name"):
        peak = group["CF_x"].abs().max()
        if peak == 0:
            continue
        ratios[str(name)] = abs(group["CF_x"].mean()) / peak
    return ratios


def run_acceptance_gate(
    *,
    manifest_path: Path | str,
    csv_paths: dict[str, Path],
    run_metadata_paths: dict[str, Path],
    provenance_path: Path | str,
) -> GateResult:
    """Gate a corpus before its `dataset.parquet` is built.

    Args:
        manifest_path: Path to the corpus's `sweep_manifest.json`.
        csv_paths: Mapping of config name to its raw force CSV (mirrors `build_dataset`'s own
            interface -- the gate reuses the real extractor, not a reimplementation).
        run_metadata_paths: Mapping of config name to its `run_metadata_<config>.json`.
        provenance_path: Path to the corpus's `sweep_provenance.json`.

    Returns:
        A :class:`GateResult`. `passed` is `False` if any configuration is CFL-limited, has a
        row count disagreeing with the manifest, has non-monotonic time, fails the normalized
        symmetry check, or if no completed (non-partial) CC-F1 result is recorded when the
        corpus is field-capture-enabled.
    """
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    df, dropped = build_dataset(manifest_path, csv_paths, allow_missing=True)
    for name in dropped:
        failures.append(f"{name}: no force CSV found (dropped from the corpus)")

    counts = df["config_name"].value_counts()
    for config in manifest["configs"]:
        name = config["name"]
        if name in dropped:
            continue
        actual_rows = int(counts.get(name, 0))
        if actual_rows != config["max_step"]:
            failures.append(
                f"{name}: recomputed row count {actual_rows} != manifest max_step "
                f"{config['max_step']}"
            )

        metadata_path = run_metadata_paths.get(name)
        if metadata_path is None or not Path(metadata_path).exists():
            failures.append(f"{name}: no run_metadata file found")
            continue
        run_metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        if run_metadata.get("interior_dt_below_nominal"):
            realized = run_metadata.get("realized_dt", {})
            failures.append(
                f"{name}: interior_dt_below_nominal=True (CFL-limited; observed min dt "
                f"{realized.get('min', 'unknown')})"
            )

    for name, group in df.groupby("config_name"):
        times = group.sort_index()["time"].to_numpy()
        if len(times) > 1 and not (times[1:] > times[:-1]).all():
            failures.append(f"{name}: time is not strictly increasing")

    for name, ratio in _settled_beat_symmetry_ratios(df).items():
        if ratio > SYMMETRY_RATIO_TOLERANCE:
            failures.append(
                f"{name}: normalized symmetry ratio {ratio:.4f} exceeds tolerance "
                f"{SYMMETRY_RATIO_TOLERANCE} (likely truncated)"
            )

    provenance_path = Path(provenance_path)
    provenance = (
        json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance_path.exists()
        else {}
    )
    cluster_run = provenance.get("cluster_run", {})
    is_field_capture = bool(provenance.get("field_capture"))
    if is_field_capture:
        cc_f1 = cluster_run.get("cc_f1")
        if cc_f1 is None:
            failures.append(
                "field-capture corpus has no recorded CC-F1 result in "
                "sweep_provenance.cluster_run.cc_f1 (required check has no recorded outcome)"
            )
        elif cc_f1.get("partial"):
            failures.append(
                "sweep_provenance.cluster_run.cc_f1 is a partial mid-sweep result; it does not "
                "satisfy the post-run acceptance gate"
            )
        elif cc_f1.get("verdict") != "pass":
            failures.append(
                f"sweep_provenance.cluster_run.cc_f1 did not pass (verdict={cc_f1.get('verdict')!r})"
            )

    return GateResult(passed=not failures, failures=tuple(failures))


def record_check_result(
    provenance_path: Path | str, check_name: str, **fields: object
) -> None:
    """Persist a mandatory pre-flight/mid-sweep check's outcome into `sweep_provenance.json`'s `cluster_run` block.

    An unrecorded check is indistinguishable from one that was never run (design D6); this is
    the single write path every such check should use.

    Args:
        provenance_path: Path to the corpus's `sweep_provenance.json`.
        check_name: The check's name (e.g. `"cc_f1"`), used as the key under `cluster_run`.
        **fields: The check's result fields (e.g. `plotfile`, `x_velocity_min`,
            `x_velocity_max`, `verdict`, `partial`).
    """
    provenance_path = Path(provenance_path)
    provenance = (
        json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance_path.exists()
        else {}
    )
    cluster_run = provenance.setdefault("cluster_run", {})
    cluster_run[check_name] = fields
    with open(provenance_path, "w", encoding="utf-8", newline="") as handle:
        json.dump(provenance, handle, sort_keys=True, indent=2, ensure_ascii=False)
        handle.write("\n")
