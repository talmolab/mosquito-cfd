"""Real-data coarse-vs-fine force-surrogate figures (OpenSpec change add-real-comparison-figures).

Three figures, one job each, rendered from the committed coarse and fine force surrogates
(``examples/prelim_sweep`` and ``examples/prelim_sweep_fine``):

- ``skill_ranges``: the only cross-grid comparison. Per target, both grids' per-seed skill over
  their own phase-only baseline and its min-max, under the fine README's pre-registered overlap
  rule (a disjoint pair gets a generic note; no direction is ever stated).
- ``error_histograms``: what skill means within each grid. The committed seed's error beside the
  phase-only baseline's, in units of the grid's rebuilt baseline RMSE.
- ``cycle_mean_r2_diagnostic``: why cycle-mean R^2 is ill-conditioned on six configurations, for
  every seed (each seed's cycle-mean error is exact from its committed R^2).

Every builder reads the same eight inputs through :func:`_load_corpus`, whose guards run in a fixed
order before anything is written; every plotted number that ``metrics.json`` also records is read
verbatim or recomputed and required to equal it. Each figure writes ``<figure>.png``,
``<figure>_metrics.json`` (every plotted value, the drawn state and the caption) and
``<figure>_run_metadata.json`` (every input's repo-relative path and sha256, both CFD digests,
library versions and the renderer's hashes). These replace the retired seed-1234 scatter and
"config-mean collapse" builders (``add-visualization-tooling``), whose collapse finding came from
data before the wing-vertex and hinge fixes (#62, #71).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: figures are written, never shown

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

from mosquito_cfd.force_surrogate.evidence_figure import format_metric  # noqa: E402
from mosquito_cfd.force_surrogate.sidecar import (  # noqa: E402
    capture_surrogate_run_metadata,
    validate_image_digest,
)
from mosquito_cfd.force_surrogate.train import (  # noqa: E402
    CONVERGED_MIN_WINGBEAT,
    SEED_SWEEP_STATISTICS,
    TARGET_COLUMNS,
    _json_safe,
    build_phase_only_baseline,
    compute_baseline_skill,
    compute_config_resolved,
)

FIGURES: tuple[str, ...] = (
    "skill_ranges",
    "error_histograms",
    "cycle_mean_r2_diagnostic",
)

ROLE_FILES: dict[str, str] = {
    "dataset": "dataset.parquet",
    "predictions": "surrogate/holdout_predictions.parquet",
    "metrics": "surrogate/metrics.json",
    "surrogate_run_metadata": "surrogate/run_metadata.json",
}

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The renderer whose bytes each committed figure records (``renderer_sources``), keyed by fixed
# names and read from the files' own locations, never from the caller's ``root``.
RENDERER_FILES: dict[str, Path] = {
    "comparison_figure.py": Path(__file__).resolve(),
    "scripts/make_coarse_vs_fine_figures.py": _REPO_ROOT
    / "scripts"
    / "make_coarse_vs_fine_figures.py",
}

_LIBRARIES: tuple[str, ...] = ("numpy", "pandas", "pyarrow", "matplotlib")
_PREDICTION_ID_COLUMNS: tuple[str, ...] = ("config_name", "time", "phase", "wingbeat")
_DATASET_COLUMNS: tuple[str, ...] = (
    "config_name",
    "time",
    "phase",
    "wingbeat",
    "split",
)
_KEY = ["config_name", "time"]


@dataclass(frozen=True)
class Corpus:
    """One corpus's validated inputs (the shared loader's output)."""

    name: str
    paths: dict[str, Path]
    sha: dict[str, str]
    dataset: pd.DataFrame
    predictions: pd.DataFrame
    metrics: dict[str, Any]
    surrogate_run_metadata: dict[str, Any]
    n_beats: int


def _reject_constant(token: str) -> float:
    raise ValueError(f"non-finite JSON literal {token!r}")


def _get(node: Any, label: str, *keys: Any) -> Any:
    """``node[k0][k1]...`` or a ``ValueError`` naming ``label`` and the missing path."""
    for depth, key in enumerate(keys):
        ok = (isinstance(node, dict) and key in node) or (
            isinstance(node, list)
            and isinstance(key, int)
            and -len(node) <= key < len(node)
        )
        if not ok:
            path = ".".join(str(k) for k in keys[: depth + 1])
            raise ValueError(f"{label} lacks {path}")
        node = node[key]
    return node


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


_FLOAT_MAX = float(np.finfo(np.float64).max)


def _is_number(value: Any) -> bool:
    """A JSON number: ``int`` or ``float``, never ``bool``."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _first_non_finite(node: Any, path: str = "") -> str | None:
    """The path of the first number a float cannot hold in a parsed JSON tree.

    ``1e999`` loads as ``inf``; an integer literal such as ``10**400`` loads as a Python int
    that would overflow when converted to a float.
    """
    if isinstance(node, float) and not math.isfinite(node):
        return path or "<root>"
    if isinstance(node, int) and not isinstance(node, bool) and abs(node) > _FLOAT_MAX:
        return path or "<root>"
    if isinstance(node, dict):
        items = node.items()
    elif isinstance(node, list):
        items = enumerate(node)
    else:
        return None
    for key, value in items:
        found = _first_non_finite(value, f"{path}.{key}" if path else str(key))
        if found:
            return found
    return None


def _load_corpus(root: str | Path, corpus_dir: str | Path, name: str) -> Corpus:
    """Load and validate one corpus: shared guards 2-10, in order (guard 1 is the digest).

    Raises:
        ValueError: On the first guard that fails, naming the corpus, the role and the defect.
    """
    base = Path(root) / corpus_dir
    paths = {role: base / rel for role, rel in ROLE_FILES.items()}
    # Guard 2: each file exists.
    for role, path in paths.items():
        if not path.is_file():
            raise ValueError(f"{name}_{role} input is missing: {path}")
    raw = {role: path.read_bytes() for role, path in paths.items()}
    sha = {role: hashlib.sha256(data).hexdigest() for role, data in raw.items()}

    # Guard 3: each JSON input is an object without a NaN/Infinity literal.
    def load_json(role: str) -> dict[str, Any]:
        try:
            data = json.loads(
                raw[role].decode("utf-8"), parse_constant=_reject_constant
            )
        except ValueError as exc:
            raise ValueError(f"{name}_{role} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(
                f"{name}_{role} must be a JSON object, got {type(data).__name__}"
            )
        bad = _first_non_finite(data)
        if bad:
            raise ValueError(f"{name}_{role} has a non-finite number at {bad}")
        return data

    def load_parquet(role: str) -> pd.DataFrame:
        try:
            return pd.read_parquet(io.BytesIO(raw[role]))
        except Exception as exc:  # pyarrow raises several types for unreadable bytes
            raise ValueError(f"{name}_{role} is not readable parquet: {exc}") from exc

    metrics = load_json("metrics")
    run_metadata = load_json("surrogate_run_metadata")
    dataset = load_parquet("dataset")
    predictions = load_parquet("predictions")

    # Guard 4: required columns.
    required = {
        "predictions": [
            *_PREDICTION_ID_COLUMNS,
            *(f"{c}_{kind}" for c in TARGET_COLUMNS for kind in ("true", "pred")),
        ],
        "dataset": [*_DATASET_COLUMNS, *TARGET_COLUMNS],
    }
    for role, frame in (("predictions", predictions), ("dataset", dataset)):
        missing = [c for c in required[role] if c not in frame.columns]
        if missing:
            raise ValueError(f"{name}_{role} is missing required column(s) {missing}")
        string_cols = ["config_name", "split"] if role == "dataset" else ["config_name"]
        for col in string_cols:
            if not pd.api.types.is_string_dtype(frame[col]) or frame[col].isna().any():
                raise ValueError(
                    f"{name}_{role} column {col} must be non-null strings, got "
                    f"{frame[col].dtype}"
                )
        wingbeat = frame["wingbeat"]
        if not pd.api.types.is_integer_dtype(wingbeat) or pd.api.types.is_bool_dtype(
            wingbeat
        ):
            raise ValueError(
                f"{name}_{role} column wingbeat must be integers, got {wingbeat.dtype}"
            )
        for col in required[role]:
            if col in ("config_name", "wingbeat", "split"):
                continue
            series = frame[col]
            if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(
                series
            ):
                raise ValueError(
                    f"{name}_{role} column {col} must be numeric, got {series.dtype}"
                )

    # Guard 5: the dataset is the surrogate's training data.
    inputs = run_metadata.get("inputs")
    recorded = inputs.get("hash") if isinstance(inputs, dict) else None
    if recorded != sha["dataset"]:
        raise ValueError(
            f"{name}_dataset sha256 {sha['dataset']} differs from the {name} surrogate's "
            f"recorded inputs.hash {recorded}; the surrogate was not trained on this dataset"
        )

    # Guard 6: non-empty, at least two configurations, no repeated (config_name, time) key.
    if len(predictions) == 0:
        raise ValueError(f"{name}_predictions is empty")
    if len(dataset) == 0:
        raise ValueError(f"{name}_dataset is empty")
    if predictions["config_name"].nunique() < 2:
        raise ValueError(f"{name}_predictions has fewer than two configurations")
    for role, frame in (("predictions", predictions), ("dataset", dataset)):
        dup = frame.duplicated(_KEY)
        if dup.any():
            first = frame.loc[dup, _KEY].iloc[0].tolist()
            raise ValueError(
                f"{name}_{role} has duplicate (config_name, time) keys, first {first}"
            )

    # Guard 7: every coefficient is finite.
    finite_cols = {
        "predictions": [
            "time",
            "phase",
            *(c for c in required["predictions"] if c.startswith("CF_")),
        ],
        "dataset": ["time", "phase", *TARGET_COLUMNS],
    }
    for role, frame in (("predictions", predictions), ("dataset", dataset)):
        for col in finite_cols[role]:
            if not np.isfinite(frame[col].to_numpy(dtype=float)).all():
                raise ValueError(f"{name}_{role} has non-finite values in column {col}")

    # Guard 8: beat structure.
    beats = dataset.groupby("config_name")["wingbeat"].agg(
        lambda s: frozenset(s.tolist())
    )
    n_beats = int(dataset["wingbeat"].max()) + 1
    expected = frozenset(range(n_beats))
    bad = [str(cfg) for cfg, got in beats.items() if got != expected]
    if bad:
        raise ValueError(
            f"{name}_dataset: configuration(s) {bad} do not have wingbeats exactly "
            f"0..{n_beats - 1}; every configuration must have the same contiguous wingbeats"
        )
    recorded_min = _get(
        metrics,
        f"{name}_metrics",
        "phase_baseline_skill",
        "phase_baseline",
        "converged_min_wingbeat",
    )
    if (
        not _is_number(recorded_min)
        or isinstance(recorded_min, float)
        or recorded_min != CONVERGED_MIN_WINGBEAT
    ):
        raise ValueError(
            f"{name}_metrics phase_baseline.converged_min_wingbeat {recorded_min} != "
            f"train.CONVERGED_MIN_WINGBEAT {CONVERGED_MIN_WINGBEAT}"
        )
    got = set(predictions["wingbeat"].tolist())
    want = set(range(CONVERGED_MIN_WINGBEAT, n_beats))
    if got != want:
        raise ValueError(
            f"{name}_predictions has wingbeats {sorted(got)}; expected exactly {sorted(want)}"
        )

    # Guard 9: the predictions are the dataset's scored holdout rows.
    holdout = dataset[
        (dataset["split"] == "holdout")
        & (dataset["wingbeat"] >= CONVERGED_MIN_WINGBEAT)
    ]
    merged = predictions[
        [*_KEY, "phase", "wingbeat", *(f"{c}_true" for c in TARGET_COLUMNS)]
    ].merge(
        holdout[[*_KEY, "phase", "wingbeat", *TARGET_COLUMNS]],
        on=_KEY,
        how="outer",
        indicator=True,
        suffixes=("_pred_file", "_dataset"),
    )
    if not (merged["_merge"] == "both").all():
        raise ValueError(
            f"{name}_predictions rows are not exactly the {name} dataset's holdout rows "
            f"with wingbeat >= {CONVERGED_MIN_WINGBEAT}"
        )
    for col in ("phase", "wingbeat"):
        if not np.array_equal(
            merged[f"{col}_pred_file"].to_numpy(), merged[f"{col}_dataset"].to_numpy()
        ):
            raise ValueError(
                f"{name}_predictions column {col} differs from the {name} dataset's "
                "holdout rows"
            )
    for c in TARGET_COLUMNS:
        if not np.array_equal(merged[f"{c}_true"].to_numpy(), merged[c].to_numpy()):
            raise ValueError(
                f"{name}_predictions column {c}_true differs from the {name} dataset's "
                "holdout rows"
            )

    # Guard 10: the seed sweep is self-consistent.
    label = f"{name}_metrics"
    sweep = _get(metrics, label, "seed_sweep")
    runs = _get(sweep, label, "runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError(f"{label} seed_sweep.runs is empty")
    for i, r in enumerate(runs):
        seed = _get(r, label, "seed")
        if not _is_number(seed) or isinstance(seed, float):
            raise ValueError(
                f"{label} seed_sweep.runs[{i}].seed {seed!r} is not an integer"
            )
        for c in TARGET_COLUMNS:
            for stat in SEED_SWEEP_STATISTICS:
                value = _get(r, label, "per_target", c, stat)
                if value is not None and not _is_number(value):
                    raise ValueError(
                        f"{label} seed_sweep.runs[{i}] {c} {stat} {value!r} is not a number"
                    )
    primary = _get(sweep, label, "primary_seed")
    if not _is_number(primary) or isinstance(primary, float):
        raise ValueError(
            f"{label} seed_sweep.primary_seed {primary!r} is not an integer"
        )
    listed = _get(sweep, label, "seeds")
    if not isinstance(listed, list) or any(
        not _is_number(s) or isinstance(s, float) for s in listed
    ):
        raise ValueError(
            f"{label} seed_sweep.seeds {listed!r} is not a list of integers"
        )
    if listed != [r["seed"] for r in runs]:
        raise ValueError(
            f"{label} seed_sweep.seeds {listed} != the runs' seeds {[r['seed'] for r in runs]}"
        )
    for c in TARGET_COLUMNS:
        for keys in (
            ("phase_baseline_skill", "per_target", c, "skill"),
            ("phase_baseline_skill", "per_target", c, "phase_baseline_rmse"),
            ("config_resolved", c, "config_mean_r2"),
        ):
            value = _get(metrics, label, *keys)
            if value is not None and not _is_number(value):
                raise ValueError(f"{label} {'.'.join(keys)} {value!r} is not a number")
    for c in TARGET_COLUMNS:
        for stat in SEED_SWEEP_STATISTICS:
            values = [_get(r, label, "per_target", c, stat) for r in runs]
            finite = [float(v) for v in values if not _is_null(v) and math.isfinite(v)]
            want_range = {"min": min(finite), "max": max(finite)} if finite else None
            have_range = _get(sweep, label, "range", c, stat)
            if have_range != want_range:
                raise ValueError(
                    f"{label} seed_sweep.range.{c}.{stat} {have_range} != the NaN-aware "
                    f"min/max of its runs {want_range}"
                )
    if _get(runs[0], label, "seed") != primary:
        raise ValueError(
            f"{label} seed_sweep.runs[0].seed {runs[0]['seed']} is not primary_seed {primary}"
        )
    for c in TARGET_COLUMNS:
        first = _get(runs[0], label, "per_target", c, "skill")
        block = _get(metrics, label, "phase_baseline_skill", "per_target", c, "skill")
        same = (_is_null(first) and _is_null(block)) or (
            not _is_null(first) and not _is_null(block) and first == block
        )
        if not same:
            raise ValueError(
                f"{label} seed_sweep.runs[0] {c} skill {first} != "
                f"phase_baseline_skill.per_target.{c}.skill {block}"
            )
    for c in TARGET_COLUMNS:
        for stat in ("skill", "config_mean_r2"):
            nulls = [r["seed"] for r in runs if _is_null(r["per_target"][c][stat])]
            if nulls and len(nulls) != len(runs):
                raise ValueError(
                    f"{label} {c} {stat} is null for seed(s) {nulls} but not for the others; "
                    "a null is all-or-none per corpus and target"
                )
        for r in runs:
            value = r["per_target"][c]["config_mean_r2"]
            if not _is_null(value) and value > 1:
                raise ValueError(
                    f"{label} {c} config_mean_r2 {value} at seed {r['seed']} exceeds 1"
                )

    return Corpus(
        name=name,
        paths=paths,
        sha=sha,
        dataset=dataset,
        predictions=predictions,
        metrics=metrics,
        surrogate_run_metadata=run_metadata,
        n_beats=n_beats,
    )


def _check_pair(coarse: Corpus, fine: Corpus) -> int:
    """Guard 11: the two corpora are paired. Returns the shared beat count N."""
    for kind, frame in (("dataset", "dataset"), ("holdout", "predictions")):
        sets = [set(getattr(c, frame)["config_name"].unique()) for c in (coarse, fine)]
        if sets[0] != sets[1]:
            raise ValueError(
                f"coarse and fine {kind} configuration sets differ: "
                f"{sorted(sets[0] ^ sets[1])} are in only one"
            )
    seeds = [
        [r["seed"] for r in c.metrics["seed_sweep"]["runs"]] for c in (coarse, fine)
    ]
    if seeds[0] != seeds[1]:
        raise ValueError(f"coarse and fine seed lists differ: {seeds[0]} vs {seeds[1]}")
    for rc, rf in zip(
        coarse.metrics["seed_sweep"]["runs"],
        fine.metrics["seed_sweep"]["runs"],
        strict=True,
    ):
        val_c = _get(rc, "coarse_metrics", "val_configs")
        val_f = _get(rf, "fine_metrics", "val_configs")
        if val_c != val_f:
            raise ValueError(
                f"coarse and fine val_configs differ at seed {rc['seed']}: "
                f"{val_c} vs {val_f}"
            )
    if coarse.n_beats != fine.n_beats:
        raise ValueError(
            f"coarse and fine beat counts differ: {coarse.n_beats} vs {fine.n_beats}"
        )
    return coarse.n_beats


def _portable_path(path: str | PurePath, root: str | PurePath) -> str:
    """``path`` relative to ``root``, with forward slashes; refuses anything outside ``root``.

    A relative ``path`` is taken relative to ``root``. Pure path flavours are preserved, so a
    ``PureWindowsPath`` is handled the same on every OS.
    """
    concrete = not isinstance(root, PurePath) or isinstance(root, Path)
    root_p = Path(root).absolute() if concrete else root
    path_p = path if isinstance(path, PurePath) else Path(path)
    if not path_p.is_absolute():
        path_p = root_p / path_p
    elif concrete:
        path_p = Path(path_p).absolute()
    if ".." in path_p.parts:
        raise ValueError(f"path {path} is outside the root {root} (it contains '..')")
    try:
        rel = path_p.relative_to(root_p)
    except ValueError as exc:
        raise ValueError(f"path {path} is outside the root {root}") from exc
    return PurePosixPath(*rel.parts).as_posix()


def _renderer_sources(files: dict[str, Path] | None = None) -> dict[str, str | None]:
    """sha256 of each renderer file's LF-normalised bytes (``None`` if the file is absent)."""
    files = RENDERER_FILES if files is None else files
    out: dict[str, str | None] = {}
    for key, path in files.items():
        path = Path(path)
        out[key] = (
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            if path.is_file()
            else None
        )
    return out


def _library_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for dist in _LIBRARIES:
        try:
            versions[dist] = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            versions[dist] = None
    return versions


def _provenance(
    *,
    root: str | Path,
    coarse: Corpus,
    fine: Corpus,
    docker_image_digest: str,
    timestamp: str,
    figure: str,
    renderer_files: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """The figure's ``run_metadata.json`` payload (CC-1 triple plus every input's hash)."""
    input_files = {
        f"{corpus.name}_{role}": {
            "path": _portable_path(corpus.paths[role], root),
            "sha256": corpus.sha[role],
        }
        for corpus in (coarse, fine)
        for role in ROLE_FILES
    }
    images = {}
    for corpus in (coarse, fine):
        image = corpus.surrogate_run_metadata.get("docker_image")
        if not isinstance(image, str):
            raise ValueError(f"{corpus.name}_surrogate_run_metadata lacks docker_image")
        images[corpus.name] = image
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        extra={
            "input_files": input_files,
            "corpus_docker_images": images,
            "library_versions": _library_versions(),
            "renderer_sources": _renderer_sources(renderer_files),
            "figure": figure,
        },
    )
    metadata["inputs"] = {
        "file": input_files["coarse_metrics"]["path"],
        "hash": input_files["coarse_metrics"]["sha256"],
    }
    return metadata


def _plain(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays to built-ins (NaN/inf become None later)."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_plain(v) for v in obj.tolist()]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def _dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(_json_safe(_plain(payload)), indent=2, ensure_ascii=False).encode(
        "utf-8"
    )


_DPI = 200  # PNG resolution of every comparison figure


def _render_and_write(
    out_dir: str | Path,
    figure: str,
    draw: Callable[[dict[str, Any]], Any],
    metrics: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Draw ``figure`` under matplotlib's default style, then write its three files.

    The style context isolates the PNG from a caller's rcParams or a local ``matplotlibrc``,
    which ``git.dirty`` cannot see.
    """
    with plt.style.context("default"):
        _write_outputs(out_dir, figure, draw(metrics), metrics, metadata)


def _write_outputs(
    out_dir: str | Path,
    figure: str,
    fig: Any,
    metrics: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Write ``<figure>.png``, ``_metrics.json``, ``_run_metadata.json`` (in that order).

    The PNG is rendered into memory and the figure closed before anything touches the disk; its
    sha256 is added to the run metadata as ``png_sha256``. Each file is written to a temporary
    name and moved into place with ``os.replace``. A failure while staging leaves no file; a
    failure between two moves leaves exactly the files already moved. Neither leaves a temporary
    file.
    """
    try:
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=_DPI, bbox_inches="tight")
    finally:
        plt.close(fig)
    out_dir = Path(out_dir)
    png = buffer.getvalue()
    metadata = {**metadata, "png_sha256": hashlib.sha256(png).hexdigest()}
    payloads = [
        (f"{figure}.png", png),
        (f"{figure}_metrics.json", _dumps(metrics)),
        (f"{figure}_run_metadata.json", _dumps(metadata)),
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for name, data in payloads:
            tmp = out_dir / f".{name}.tmp"
            # Staged before writing, so a write that fails part-way is still cleaned up.
            staged.append((tmp, out_dir / name))
            tmp.write_bytes(data)
        for tmp, dst in staged:
            os.replace(tmp, dst)
    finally:
        for tmp, _ in staged:
            if tmp.exists():
                tmp.unlink()


def _prepare(
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    docker_image_digest: str,
) -> tuple[Path, Corpus, Corpus, int]:
    """Guard 1 (the digest, before any file), then the shared loader and the pairing guard."""
    validate_image_digest(docker_image_digest)
    return _load_pair(root, coarse_dir, fine_dir)


def _load_pair(
    root: str | Path, coarse_dir: str | Path, fine_dir: str | Path
) -> tuple[Path, Corpus, Corpus, int]:
    """Load both corpora under an absolute ``root`` and apply the pairing guard.

    ``root`` is made absolute first, so every input path is absolute and recorded relative to
    it exactly once (a relative root other than ``.`` would otherwise be joined twice).
    """
    root = Path(root).absolute()
    coarse = _load_corpus(root, coarse_dir, "coarse")
    fine = _load_corpus(root, fine_dir, "fine")
    return root, coarse, fine, _check_pair(coarse, fine)


# Shared wording (spec: "Comparison-figure captions and labels state the scope and never compare
# the grids"). RULE_SENTENCE and OWN_BASELINE_PHRASE also appear in the fine README's "Coarse vs
# fine" section; a test keeps the two in step.
TARGET_LABELS: dict[str, str] = {
    "CF_x": "CF_x (lab x force)",
    "CF_y": "CF_y (lab y force)",
    "CF_z": "CF_z (lab vertical force)",
    "CF_mx": "CF_mx (lab M_x about the hinge)",
    "CF_my": "CF_my (lab M_y about the hinge)",
    "CF_mz": "CF_mz (lab M_z about the hinge)",
}
SHIPPED_PHRASE = "shipped surrogate (surrogate/)"
LAB_FRAME_PHRASE = "lab-frame components of the IB force and moment on the wing; moments about the hinge"
OWN_BASELINE_PHRASE = "each grid is scored against its own corpus's phase-only baseline"
RULE_SENTENCE = (
    "a target counts as moved only if its two {n}-seed ranges are disjoint (computed on the "
    "unrounded values; touching ranges count as overlapping)"
)
REGENERATION_PHRASE = "the corpus is to be regenerated with longer runs"
DISJOINT_NOTE = (
    "ranges disjoint at {n} seeds each; see README before reading this as a grid effect"
)
# Wing-frame or biomechanical framings these lab-frame figures must never use.
FORBIDDEN_WORDS = re.compile(r"(?i)\b(?:(?:chord|span|drag|pitch|roll)\w*|normal)\b")
_COLORS = {"coarse": "#0072B2", "fine": "#D55E00"}
_CAPTION_WIDTH = 150


def beat_sentence(n_beats: int) -> str:
    """The caption's beat label, read from the data (plus the regeneration note at N = 2)."""
    first = CONVERGED_MIN_WINGBEAT + 1  # 1-based number of the first scored beat
    if n_beats == 2 and first == 2:
        label = "second wingbeat of 2-beat runs"
    else:
        label = f"wingbeats {first}–{n_beats} of {n_beats}-beat runs"
    text = f"Holdout rows are the {label}"
    if n_beats == 2:
        text += f"; {REGENERATION_PHRASE}"
    return text + "."


def _shared_caption(n_beats: int) -> str:
    return f"Shows the {SHIPPED_PHRASE}. Targets are {LAB_FRAME_PHRASE}. {beat_sentence(n_beats)}"


def ranges_overlap(coarse: dict[str, Any] | None, fine: dict[str, Any] | None) -> str:
    """``yes`` when the two ranges overlap (touching counts), ``no`` if disjoint, ``n/a`` if null.

    The fine README's pre-registered rule, computed on the raw values; it agrees with
    ``tests/_readme_guards.overlap_cell`` by test.
    """
    ends = [r.get(k) if r else None for r in (coarse, fine) for k in ("min", "max")]
    if any(e is None for e in ends):
        return "n/a"
    lo_c, hi_c, lo_f, hi_f = ends
    return "yes" if max(lo_c, lo_f) <= min(hi_c, hi_f) else "no"


def build_skill_ranges_caption(*, n_seeds: int, primary_seed: int, n_beats: int) -> str:
    """The ``skill_ranges`` caption (pure)."""
    return (
        f"Skill (1 − MSE/MSE₀) over the phase-only baseline, {n_seeds} seeds per grid "
        f"(markers; the diamond is seed {primary_seed}); bars show the observed spread, not a "
        f"confidence interval. Rule: {RULE_SENTENCE.format(n=n_seeds)}. Note that "
        f"{OWN_BASELINE_PHRASE}, so this is not a measurement of the effect of grid resolution "
        f"on its own. {_shared_caption(n_beats)}"
    )


def _skill_ranges_metrics(coarse: Corpus, fine: Corpus, n_beats: int) -> dict[str, Any]:
    runs = {c.name: c.metrics["seed_sweep"]["runs"] for c in (coarse, fine)}
    seeds = [r["seed"] for r in runs["coarse"]]
    primary = coarse.metrics["seed_sweep"]["primary_seed"]
    targets: dict[str, Any] = {}
    notes: dict[str, str] = {}
    for c in TARGET_COLUMNS:
        entry: dict[str, Any] = {}
        for corpus in (coarse, fine):
            values = [r["per_target"][c]["skill"] for r in runs[corpus.name]]
            values = [None if _is_null(v) else v for v in values]
            rng = corpus.metrics["seed_sweep"]["range"][c]["skill"]
            entry[corpus.name] = {
                "seeds": seeds,
                "values": values,
                "range": rng,
                "markers": sum(v is not None for v in values),
                "bar": [rng["min"], rng["max"]] if rng else None,
                "na": rng is None,
            }
        entry["overlap"] = ranges_overlap(
            entry["coarse"]["range"], entry["fine"]["range"]
        )
        if entry["overlap"] == "no":
            notes[c] = DISJOINT_NOTE.format(n=len(seeds))
        targets[c] = entry
    return {
        "figure": "skill_ranges",
        "seeds": seeds,
        "primary_seed": primary,
        "n_beats": n_beats,
        "labels": [TARGET_LABELS[c] for c in TARGET_COLUMNS],
        "targets": targets,
        "notes": notes,
        "caption": build_skill_ranges_caption(
            n_seeds=len(seeds), primary_seed=primary, n_beats=n_beats
        ),
    }


def compute_skill_ranges_metrics(
    *, root: str | Path, coarse_dir: str | Path, fine_dir: str | Path
) -> dict[str, Any]:
    """The ``skill_ranges`` sidecar recomputed from the inputs (pure; no rendering)."""
    _, coarse, fine, n_beats = _load_pair(root, coarse_dir, fine_dir)
    return _skill_ranges_metrics(coarse, fine, n_beats)


def _draw_skill_ranges(m: dict[str, Any]) -> Any:
    fig, ax = plt.subplots(figsize=(10.0, 6.6))
    try:
        n_t = len(TARGET_COLUMNS)
        side = blended_transform_factory(ax.transAxes, ax.transData)
        for i, c in enumerate(TARGET_COLUMNS):
            y0 = n_t - 1 - i
            for corpus, dy in (("coarse", 0.17), ("fine", -0.17)):
                e = m["targets"][c][corpus]
                y = y0 + dy
                color = _COLORS[corpus]
                if e["bar"] is None:
                    ax.text(0.01, y, "n/a", transform=side, va="center", fontsize=8)
                else:
                    ax.plot(
                        e["bar"],
                        [y, y],
                        color=color,
                        lw=7,
                        alpha=0.3,
                        solid_capstyle="butt",
                    )
                for k, v in enumerate(e["values"]):
                    if v is None:
                        continue
                    ax.plot(
                        [v],
                        [y],
                        ls="none",
                        color=color,
                        marker="D" if k == 0 else "o",
                        ms=7 if k == 0 else 4.5,
                        mec="black" if k == 0 else color,
                        mew=0.8,
                    )
            if c in m["notes"]:
                ax.text(
                    1.02,
                    y0,
                    textwrap.fill(m["notes"][c], 30),
                    transform=side,
                    va="center",
                    fontsize=7,
                    color="0.25",
                )
        ax.set_yticks([n_t - 1 - i for i in range(n_t)], m["labels"], fontsize=9)
        ax.set_ylim(-0.6, n_t - 0.4)
        ax.grid(axis="x", color="0.9")
        ax.set_xlabel("skill over the phase-only baseline (1 − MSE/MSE₀)", fontsize=9)
        n = len(m["seeds"])
        ax.set_title(
            f"Coarse vs fine: skill over each corpus's own baseline, {n} seeds per grid",
            fontsize=10,
        )
        handles = [
            Line2D(
                [], [], color=_COLORS["coarse"], lw=6, alpha=0.4, label="coarse grid"
            ),
            Line2D([], [], color=_COLORS["fine"], lw=6, alpha=0.4, label="fine grid"),
            Line2D(
                [],
                [],
                ls="none",
                marker="D",
                color="0.4",
                mec="black",
                label=f"seed {m['primary_seed']}",
            ),
            Line2D([], [], ls="none", marker="o", color="0.4", label="other seeds"),
        ]
        ax.legend(
            handles=handles,
            loc="lower left",
            fontsize=8,
            frameon=False,
            bbox_to_anchor=(0.0, 1.06),
            ncol=4,
        )
        fig.text(
            0.01,
            0.01,
            textwrap.fill(m["caption"], _CAPTION_WIDTH),
            fontsize=7,
            va="bottom",
            ha="left",
        )
        fig.subplots_adjust(left=0.26, right=0.76, bottom=0.21, top=0.86)
    except BaseException:
        plt.close(fig)
        raise
    return fig


def build_skill_ranges(
    *,
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
) -> dict[str, Any]:
    """Render ``skill_ranges``: per target, both grids' per-seed skill and their min–max.

    The only coarse-vs-fine comparison figure. Values are read verbatim from each corpus's
    ``seed_sweep``; a disjoint pair (the pre-registered rule) gets a generic in-axes note and no
    direction is stated anywhere.

    Returns:
        The ``skill_ranges_metrics.json`` payload.

    Raises:
        ValueError: If the digest is mutable or any shared input guard fails (nothing written).
    """
    root, coarse, fine, n_beats = _prepare(
        root, coarse_dir, fine_dir, docker_image_digest
    )
    metrics = _skill_ranges_metrics(coarse, fine, n_beats)
    metadata = _provenance(
        root=root,
        coarse=coarse,
        fine=fine,
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        figure="skill_ranges",
    )
    _render_and_write(out_dir, "skill_ranges", _draw_skill_ranges, metrics, metadata)
    return metrics


# Fixed edges in units of a grid's baseline RMSE (width 0.01). On the committed data the closest
# normalised error to an edge is 7.5e-9, so the counts are exact across platforms.
EDGES = np.linspace(-3.0, 3.0, 601)
_BASELINE_TOLERANCE = 1e-9


def _bin_counts(z: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Histogram counts on ``edges`` plus the out-of-range counts.

    Returns ``(counts, below, above)``: ``numpy.histogram`` counts (a value at either end edge
    falls in the end bin) and the numbers strictly below the first and above the last edge.
    """
    z = np.asarray(z, dtype=float)
    below = int((z < edges[0]).sum())
    above = int((z > edges[-1]).sum())
    inside = z[(z >= edges[0]) & (z <= edges[-1])]
    counts, _ = np.histogram(inside, bins=edges)
    return counts, below, above


def _density(counts: np.ndarray, n_rows: int, edges: np.ndarray) -> np.ndarray:
    """Density over every row, out-of-range rows included (never renormalised away)."""
    return np.asarray(counts, dtype=float) / (n_rows * np.diff(edges))


def build_error_histograms_caption(
    *, primary_seed: int, n_seeds: int, n_configs: int, n_beats: int
) -> str:
    """The ``error_histograms`` caption (pure)."""
    return (
        f"Error of seed {primary_seed} of the {SHIPPED_PHRASE} (colour) and of the phase-only "
        "baseline (grey) on the same holdout rows, divided by that grid's baseline RMSE "
        "(RMSE₀), as a density on a log axis; skill = 1 − (RMSE / RMSE₀)². Note that "
        f"{OWN_BASELINE_PHRASE}; widths are not compared across the two rows (one seed; each "
        f"panel gives its {n_seeds}-seed skill range). Rows are consecutive timesteps of "
        f"{n_configs} configurations, not independent samples. Targets are {LAB_FRAME_PHRASE}. "
        f"{beat_sentence(n_beats)}"
    )


def _histogram_grid(corpus: Corpus) -> tuple[dict[str, Any], dict[str, str]]:
    label = f"{corpus.name}_metrics"
    pred = corpus.predictions
    baseline, definition = build_phase_only_baseline(
        corpus.dataset, pred["phase"].to_numpy(dtype=float), list(TARGET_COLUMNS)
    )
    recorded_def = _get(corpus.metrics, label, "phase_baseline_skill", "phase_baseline")
    if dict(definition) != recorded_def:
        differing = sorted(
            k
            for k in set(definition) | set(recorded_def)
            if definition.get(k) != recorded_def.get(k)
        )
        raise ValueError(
            f"{label} phase-only baseline definition differs from the rebuilt one in "
            f"{differing}"
        )
    y_true = pred[[f"{c}_true" for c in TARGET_COLUMNS]].to_numpy(dtype=float)
    y_pred = pred[[f"{c}_pred" for c in TARGET_COLUMNS]].to_numpy(dtype=float)
    rebuilt = compute_baseline_skill(y_true, y_pred, baseline, list(TARGET_COLUMNS))
    sweep = corpus.metrics["seed_sweep"]
    n_rows = len(pred)
    grid: dict[str, Any] = {}
    annotations: dict[str, str] = {}
    for j, c in enumerate(TARGET_COLUMNS):
        recorded = _get(corpus.metrics, label, "phase_baseline_skill", "per_target", c)
        if _is_null(recorded.get("skill")):
            raise ValueError(
                f"{label} {c} skill is null (the phase-only baseline already matches the "
                "truth); an error histogram in units of its RMSE has no meaning"
            )
        rmse0 = rebuilt[c]["phase_baseline_rmse"]
        if not math.isclose(
            rmse0,
            recorded["phase_baseline_rmse"],
            rel_tol=_BASELINE_TOLERANCE,
            abs_tol=0,
        ):
            raise ValueError(
                f"{label} {c} phase-only baseline RMSE {rmse0!r} (rebuilt) != recorded "
                f"{recorded['phase_baseline_rmse']!r}"
            )
        skill = rebuilt[c]["skill"]
        if not math.isclose(
            1 - skill, 1 - recorded["skill"], rel_tol=_BASELINE_TOLERANCE, abs_tol=0
        ):
            raise ValueError(
                f"{label} {c} skill {skill!r} (rebuilt) != recorded {recorded['skill']!r}"
            )
        t = y_true[:, j]
        err_s = y_pred[:, j] - t
        rmse_s = math.sqrt(float(np.sum(err_s**2)) / n_rows)
        entry: dict[str, Any] = {
            "rmse0": rmse0,
            "rmse_surrogate": rmse_s,
            "skill": skill,
            "skill_recorded": sweep["runs"][0]["per_target"][c]["skill"],
            "skill_range": sweep["range"][c]["skill"],
            "n_rows": n_rows,
        }
        for kind, err in (("surrogate", err_s), ("baseline", baseline[:, j] - t)):
            counts, below, above = _bin_counts(err / rmse0, EDGES)
            entry[f"counts_{kind}"] = counts.tolist()
            entry[f"below_{kind}"] = below
            entry[f"above_{kind}"] = above
        grid[c] = entry
        rng = entry["skill_range"] or {}
        annotations[c] = (
            f"seed {sweep['primary_seed']} skill {format_metric(entry['skill_recorded'])} "
            f"({len(sweep['runs'])} seeds: {format_metric(rng.get('min'))} to "
            f"{format_metric(rng.get('max'))})"
        )
    return grid, annotations


def _error_histograms_metrics(
    coarse: Corpus, fine: Corpus, n_beats: int
) -> dict[str, Any]:
    grids, annotations = {}, {}
    for corpus in (coarse, fine):
        grids[corpus.name], annotations[corpus.name] = _histogram_grid(corpus)
    sweep = coarse.metrics["seed_sweep"]
    return {
        "figure": "error_histograms",
        "primary_seed": sweep["primary_seed"],
        "n_seeds": len(sweep["runs"]),
        "n_beats": n_beats,
        "labels": [TARGET_LABELS[c] for c in TARGET_COLUMNS],
        "edges": EDGES.tolist(),
        "grids": grids,
        "annotations": annotations,
        "caption": build_error_histograms_caption(
            primary_seed=sweep["primary_seed"],
            n_seeds=len(sweep["runs"]),
            n_configs=int(coarse.predictions["config_name"].nunique()),
            n_beats=n_beats,
        ),
    }


def compute_error_histograms_metrics(
    *, root: str | Path, coarse_dir: str | Path, fine_dir: str | Path
) -> dict[str, Any]:
    """The ``error_histograms`` sidecar recomputed from the inputs (pure; no rendering)."""
    _, coarse, fine, n_beats = _load_pair(root, coarse_dir, fine_dir)
    return _error_histograms_metrics(coarse, fine, n_beats)


def _draw_error_histograms(m: dict[str, Any]) -> Any:
    edges = np.asarray(m["edges"])
    fig, axes = plt.subplots(2, len(TARGET_COLUMNS), figsize=(17.0, 6.8), sharex=True)
    try:
        for row, corpus in enumerate(("coarse", "fine")):
            for col, c in enumerate(TARGET_COLUMNS):
                ax = axes[row, col]
                e = m["grids"][corpus][c]
                dens_b = _density(np.asarray(e["counts_baseline"]), e["n_rows"], edges)
                dens_s = _density(np.asarray(e["counts_surrogate"]), e["n_rows"], edges)
                ax.stairs(dens_b, edges, fill=True, color="0.6", alpha=0.6, lw=0)
                ax.stairs(dens_s, edges, color=_COLORS[corpus], lw=1.2)
                ax.set_yscale("log")
                positive = np.concatenate([dens_b[dens_b > 0], dens_s[dens_s > 0]])
                ax.set_ylim(positive.min() * 0.5, positive.max() * 3.0)
                ax.set_xlim(edges[0], edges[-1])
                ax.text(
                    0.02,
                    0.97,
                    m["annotations"][corpus][c].replace(" (", "\n(", 1),
                    transform=ax.transAxes,
                    va="top",
                    fontsize=6.5,
                )
                for kind, y in (("surrogate", 0.80), ("baseline", 0.72)):
                    below, above = e[f"below_{kind}"], e[f"above_{kind}"]
                    if below or above:
                        ax.text(
                            0.02,
                            y,
                            f"{kind} outside ±3: {below} / {above}",
                            transform=ax.transAxes,
                            fontsize=6,
                        )
                ax.tick_params(labelsize=7)
                if row == 0:
                    ax.set_title(m["labels"][col], fontsize=8)
                else:
                    ax.set_xlabel("error / baseline RMSE (RMSE₀)", fontsize=8)
                if col == 0:
                    ax.set_ylabel(f"{corpus} grid\ndensity", fontsize=8)
        handles = [
            Line2D(
                [],
                [],
                color=_COLORS["coarse"],
                lw=1.5,
                label=f"surrogate, seed {m['primary_seed']} (coarse)",
            ),
            Line2D(
                [],
                [],
                color=_COLORS["fine"],
                lw=1.5,
                label=f"surrogate, seed {m['primary_seed']} (fine)",
            ),
            Line2D([], [], color="0.6", lw=6, alpha=0.6, label="phase-only baseline"),
        ]
        fig.legend(
            handles=handles,
            loc="upper center",
            ncol=3,
            fontsize=8,
            frameon=False,
            bbox_to_anchor=(0.5, 1.0),
        )
        fig.text(
            0.01,
            0.01,
            textwrap.fill(m["caption"], 270),
            fontsize=7,
            va="bottom",
            ha="left",
        )
        fig.subplots_adjust(
            left=0.05, right=0.99, bottom=0.2, top=0.88, wspace=0.28, hspace=0.12
        )
    except BaseException:
        plt.close(fig)
        raise
    return fig


def build_error_histograms(
    *,
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
) -> dict[str, Any]:
    """Render ``error_histograms``: within each grid, surrogate vs phase-only baseline error.

    The baseline is rebuilt with ``train.build_phase_only_baseline`` and must reproduce the
    recorded baseline RMSE and skill (``rel=1e-9``) before anything is drawn. Errors are divided
    by the grid's own rebuilt baseline RMSE and binned on :data:`EDGES`.

    Returns:
        The ``error_histograms_metrics.json`` payload.

    Raises:
        ValueError: If the digest is mutable, a shared input guard fails, the rebuilt baseline
            does not reproduce ``metrics.json``, or a recorded skill is null (nothing written).
    """
    root, coarse, fine, n_beats = _prepare(
        root, coarse_dir, fine_dir, docker_image_digest
    )
    metrics = _error_histograms_metrics(coarse, fine, n_beats)
    metadata = _provenance(
        root=root,
        coarse=coarse,
        fine=fine,
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        figure="error_histograms",
    )
    _render_and_write(
        out_dir, "error_histograms", _draw_error_histograms, metrics, metadata
    )
    return metrics


def _form_t(recomputed: float, recorded: float) -> bool:
    """Tolerance form T: ``|a − b| ≤ 1e-12·max(1, |b|)`` (absolute below 1, relative above)."""
    return abs(recomputed - recorded) <= 1e-12 * max(1.0, abs(recorded))


def _cycle_means(values: np.ndarray, names: np.ndarray) -> np.ndarray:
    """Per-configuration means exactly as ``train.compute_config_resolved`` takes them."""
    return np.array([values[names == u].mean() for u in np.unique(names)])


def build_cycle_mean_r2_diagnostic_caption(
    *, n_seeds: int, n_configs: int, n_beats: int
) -> str:
    """The ``cycle_mean_r2_diagnostic`` caption (pure)."""
    return (
        "This figure is a diagnostic of the metric, not a comparison of the grids: cycle-mean "
        f"R² is computed on each grid's own {n_configs} holdout configurations as 1 − ε²/σ², "
        "where σ is the population standard deviation of the true cycle means and ε the RMS "
        "error of the predicted ones. Left: the waveform RMS (the scale pointwise R² sees), σ, "
        f"and ε for each of the {n_seeds} seeds, ε = σ·√(1 − R²); where ε ≥ σ, R² ≤ 0. Right: "
        f"the {n_seeds} per-seed R² values; {n_seeds} seeds give the observed spread, not a "
        f"confidence interval. {_shared_caption(n_beats)}"
    )


def _diagnostic_grid(corpus: Corpus) -> dict[str, Any]:
    label = f"{corpus.name}_metrics"
    pred = corpus.predictions
    names = pred["config_name"].to_numpy()
    y_true = pred[[f"{c}_true" for c in TARGET_COLUMNS]].to_numpy(dtype=float)
    y_pred = pred[[f"{c}_pred" for c in TARGET_COLUMNS]].to_numpy(dtype=float)
    recomputed = compute_config_resolved(y_true, y_pred, names, list(TARGET_COLUMNS))
    runs = corpus.metrics["seed_sweep"]["runs"]
    seeds = [r["seed"] for r in runs]
    grid: dict[str, Any] = {}
    for j, c in enumerate(TARGET_COLUMNS):
        t, p = y_true[:, j], y_pred[:, j]
        cm_t, cm_p = _cycle_means(t, names), _cycle_means(p, names)
        sigma = float(np.std(cm_t))
        eps_measured = float(np.sqrt(np.mean((cm_p - cm_t) ** 2)))
        per_seed = [r["per_target"][c]["config_mean_r2"] for r in runs]
        per_seed = [None if _is_null(v) else v for v in per_seed]
        recorded_cr = _get(
            corpus.metrics, label, "config_resolved", c, "config_mean_r2"
        )
        r2 = recomputed[c]["config_mean_r2"]
        if _is_null(r2):
            if not _is_null(recorded_cr) or any(v is not None for v in per_seed):
                raise ValueError(
                    f"{label} {c} config_mean_r2 is recorded but the recomputation gives the "
                    "null sentinel (the true cycle means do not vary)"
                )
            eps: list[float | None] = [None] * len(runs)
        else:
            for where, recorded in (
                ("config_resolved", recorded_cr),
                ("runs[0]", per_seed[0]),
            ):
                if _is_null(recorded) or not _form_t(1 - r2, 1 - recorded):
                    raise ValueError(
                        f"{label} {c} config_mean_r2 {recorded!r} ({where}) does not match the "
                        f"recomputed {r2!r}"
                    )
            if not _form_t(eps_measured**2 / sigma**2, 1 - per_seed[0]):
                raise ValueError(
                    f"{label} {c} measured cycle-mean error does not reproduce config_mean_r2: "
                    f"eps²/sigma² = {eps_measured**2 / sigma**2!r} vs 1 − R² = "
                    f"{1 - per_seed[0]!r}"
                )
            eps = [sigma * math.sqrt(1.0 - v) for v in per_seed]
        waveform_rms = float(np.sqrt(np.mean((t - t.mean()) ** 2)))
        grid[c] = {
            "waveform_rms": waveform_rms,
            "sigma": sigma,
            "eps_primary_measured": eps_measured,
            "seeds": seeds,
            "config_mean_r2": per_seed,
            "eps": eps,
            "floor_seeds": [s for s, e in zip(seeds, eps, strict=True) if e == 0.0],
            "floor_scales": [
                key
                for key, value in (
                    ("waveform_rms", waveform_rms),
                    ("sigma", sigma),
                )
                if value == 0.0
            ],
            "na": all(v is None for v in per_seed),
        }
    return grid


def _cycle_mean_r2_diagnostic_metrics(
    coarse: Corpus, fine: Corpus, n_beats: int
) -> dict[str, Any]:
    sweep = coarse.metrics["seed_sweep"]
    return {
        "figure": "cycle_mean_r2_diagnostic",
        "seeds": [r["seed"] for r in sweep["runs"]],
        "primary_seed": sweep["primary_seed"],
        "n_beats": n_beats,
        "labels": [TARGET_LABELS[c] for c in TARGET_COLUMNS],
        "grids": {corpus.name: _diagnostic_grid(corpus) for corpus in (coarse, fine)},
        "caption": build_cycle_mean_r2_diagnostic_caption(
            n_seeds=len(sweep["runs"]),
            n_configs=int(coarse.predictions["config_name"].nunique()),
            n_beats=n_beats,
        ),
    }


def compute_cycle_mean_r2_diagnostic_metrics(
    *, root: str | Path, coarse_dir: str | Path, fine_dir: str | Path
) -> dict[str, Any]:
    """The ``cycle_mean_r2_diagnostic`` sidecar recomputed from the inputs (pure; no rendering)."""
    _, coarse, fine, n_beats = _load_pair(root, coarse_dir, fine_dir)
    return _cycle_mean_r2_diagnostic_metrics(coarse, fine, n_beats)


def _draw_cycle_mean_r2_diagnostic(m: dict[str, Any]) -> Any:
    fig, axes = plt.subplots(
        2, 2, figsize=(15.0, 8.6), gridspec_kw={"width_ratios": [1.15, 1]}
    )
    try:
        n_t = len(TARGET_COLUMNS)
        x = np.arange(n_t)
        n_s = len(m["seeds"])
        offsets = np.linspace(-0.22, 0.22, n_s) if n_s > 1 else np.zeros(1)
        for row, corpus in enumerate(("coarse", "fine")):
            grid = m["grids"][corpus]
            color = _COLORS[corpus]
            positive = [
                v
                for c in TARGET_COLUMNS
                for v in (grid[c]["waveform_rms"], grid[c]["sigma"], *grid[c]["eps"])
                if v is not None and v > 0
            ]
            floor = min(positive) / 4.0
            ax = axes[row, 0]
            ax.set_yscale("log")
            for i, c in enumerate(TARGET_COLUMNS):
                e = grid[c]
                ax.plot(
                    [i - 0.32],
                    [e["waveform_rms"]] if e["waveform_rms"] > 0 else [floor],
                    ls="none",
                    marker="s",
                    color="black",
                    ms=6,
                )
                if "waveform_rms" in e["floor_scales"]:
                    ax.text(i - 0.45, floor * 1.4, "0", ha="center", fontsize=6.5)
                if e["sigma"] > 0:
                    ax.plot(
                        [i - 0.32],
                        [e["sigma"]],
                        ls="none",
                        marker="o",
                        mfc="none",
                        mec="0.3",
                        ms=11,
                        mew=1.4,
                    )
                else:
                    ax.plot(
                        [i - 0.32], [floor], ls="none", marker="v", color="0.3", ms=7
                    )
                    ax.text(i - 0.2, floor * 1.4, "0", ha="center", fontsize=6.5)
                if e["na"]:
                    ax.text(i, floor * 3, "R²: n/a", ha="center", fontsize=7)
                    continue
                for k, eps in enumerate(e["eps"]):
                    xi = i + offsets[k]
                    if eps is None:
                        continue
                    if eps == 0.0:
                        ax.plot([xi], [floor], ls="none", marker="v", color=color, ms=6)
                        ax.text(xi, floor * 1.4, "0", ha="center", fontsize=6.5)
                    else:
                        ax.plot(
                            [xi],
                            [eps],
                            ls="none",
                            color=color,
                            marker="D" if k == 0 else "o",
                            ms=6 if k == 0 else 4,
                            mec="black" if k == 0 else color,
                            mew=0.7,
                        )
            ax.set_ylim(floor / 1.5, max(positive) * 3.0)
            ax.set_xticks(
                x, [] if row == 0 else m["labels"], rotation=25, ha="right", fontsize=8
            )
            ax.set_ylabel(f"{corpus} grid\nscale (coefficient units, log)", fontsize=8)
            ax.tick_params(axis="y", labelsize=7)
            ax.grid(axis="y", color="0.92", which="major")
            if row == 0:
                ax.set_title(
                    "Scales: waveform RMS, σ (spread of true cycle means), ε per seed",
                    fontsize=9,
                )

            ax = axes[row, 1]
            ax.set_yscale("symlog", linthresh=1.0)
            ax.axhline(0.0, color="0.5", lw=0.8)
            ax.axhline(1.0, color="0.5", lw=0.8, ls="--")
            for i, c in enumerate(TARGET_COLUMNS):
                e = grid[c]
                if e["na"]:
                    ax.text(i, 0.5, "n/a", ha="center", fontsize=7)
                    continue
                for k, value in enumerate(e["config_mean_r2"]):
                    ax.plot(
                        [i + offsets[k]],
                        [value],
                        ls="none",
                        color=color,
                        marker="D" if k == 0 else "o",
                        ms=6 if k == 0 else 4,
                        mec="black" if k == 0 else color,
                        mew=0.7,
                    )
            values = [
                v
                for c in TARGET_COLUMNS
                for v in grid[c]["config_mean_r2"]
                if v is not None
            ]
            low = min([*values, 0.0])
            bottom = low - 0.5 * abs(low) - 0.5
            ax.set_ylim(bottom, 1.6)
            # Plain tick labels: symlog's default "−10⁰" for −1 is easy to misread.
            ticks = [-1e6, -1e4, -1e2, -10, -5, -2, -1, -0.5, 0, 0.5, 1]
            ax.set_yticks(
                [t for t in ticks if t >= bottom],
                [f"{t:g}".replace("-", "−") for t in ticks if t >= bottom],
            )
            ax.set_xticks(
                x, [] if row == 0 else m["labels"], rotation=25, ha="right", fontsize=8
            )
            ax.set_ylabel("cycle-mean R² (symlog; linear in ±1)", fontsize=8)
            ax.tick_params(axis="y", labelsize=7)
            if row == 0:
                ax.set_title("Per-seed cycle-mean R² (dashed: 1; solid: 0)", fontsize=9)
        handles = [
            Line2D([], [], ls="none", marker="s", color="black", label="waveform RMS"),
            Line2D(
                [], [], ls="none", marker="o", mfc="none", mec="0.3", ms=10, label="σ"
            ),
            Line2D(
                [],
                [],
                ls="none",
                marker="D",
                color="0.4",
                mec="black",
                label=f"seed {m['primary_seed']}",
            ),
            Line2D([], [], ls="none", marker="o", color="0.4", label="other seeds"),
            Line2D([], [], color=_COLORS["coarse"], lw=4, label="coarse grid"),
            Line2D([], [], color=_COLORS["fine"], lw=4, label="fine grid"),
        ]
        fig.legend(
            handles=handles,
            loc="upper center",
            ncol=6,
            fontsize=8,
            frameon=False,
            bbox_to_anchor=(0.5, 1.0),
        )
        fig.text(
            0.01,
            0.01,
            textwrap.fill(m["caption"], 230),
            fontsize=7,
            va="bottom",
            ha="left",
        )
        fig.subplots_adjust(
            left=0.07, right=0.99, bottom=0.2, top=0.91, wspace=0.18, hspace=0.08
        )
    except BaseException:
        plt.close(fig)
        raise
    return fig


def build_cycle_mean_r2_diagnostic(
    *,
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
) -> dict[str, Any]:
    """Render ``cycle_mean_r2_diagnostic``: why cycle-mean R² is ill-conditioned, all seeds.

    Per corpus and target: the waveform RMS, the spread σ of the true cycle means, and each
    seed's cycle-mean error ``ε_s = σ·sqrt(1 − R²_s)`` (exact, since σ does not depend on the
    seed), beside the per-seed R². The primary seed's R² is recomputed and must match
    ``config_resolved`` and ``seed_sweep.runs[0]`` in tolerance form T.

    Returns:
        The ``cycle_mean_r2_diagnostic_metrics.json`` payload.

    Raises:
        ValueError: If the digest is mutable, a shared input guard fails, or a recorded R² does
            not reproduce (nothing written).
    """
    root, coarse, fine, n_beats = _prepare(
        root, coarse_dir, fine_dir, docker_image_digest
    )
    metrics = _cycle_mean_r2_diagnostic_metrics(coarse, fine, n_beats)
    metadata = _provenance(
        root=root,
        coarse=coarse,
        fine=fine,
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        figure="cycle_mean_r2_diagnostic",
    )
    _render_and_write(
        out_dir,
        "cycle_mean_r2_diagnostic",
        _draw_cycle_mean_r2_diagnostic,
        metrics,
        metadata,
    )
    return metrics
