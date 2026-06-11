"""Forces -> tidy dataset extractor for the force surrogate (Track B, PR4).

Turns per-config IAMReX IB-particle force CSVs into one tidy dataframe (one row per
``(config, timestep)``) of kinematics + phase + normalized force/moment coefficients +
raw forces/moments, joined to the sweep manifest's kinematics, Reynolds number, and
train/holdout split. Forces come from the IB-particle CSV **only** — no plotfiles or
velocity/pressure fields (roadmap CC-6). Pure and cluster-free: no RunAI, GPU, or plotfiles.

Normalization is delegated to the single-source helpers in :mod:`.normalization` (CC-3):
each config's ``F_ref``/``M_ref`` is computed from *its own* kinematics, so the coefficients
are the physically correct per-config non-dimensionalization across a kinematic sweep.

Design decisions are documented in the OpenSpec change ``add-force-surrogate-dataset``
(``design.md``). Key points:

- **All three moment coefficients** (``CF_mx/CF_my/CF_mz``) are carried; the single "pitch
  moment" axis is deliberately deferred to PR6 (D2).
- **All timesteps are kept**, each tagged ``phase = (time*f*) mod 1`` and integer
  ``wingbeat = floor(time*f*)``; the consumer filters to the converged beat (D3).
- **Missing CSV** (path absent) hard-fails by default; ``allow_missing=True`` skips it and
  returns the dropped name. A present-but-empty (header-only) CSV contributes zero rows and
  is **not** a drop (D6).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.constants import CHORD, R_TIP, RHO, SPAN
from mosquito_cfd.force_surrogate.normalization import (
    compute_force_coefficients,
    compute_force_reference,
    compute_moment_coefficient,
    compute_moment_reference,
)
from mosquito_cfd.force_surrogate.sidecar import (
    capture_surrogate_run_metadata,
    write_units_sidecar,
)

logger = logging.getLogger(__name__)

# The real IAMReX IB-particle CSV schema (29 columns, exact order). Read name-based.
IB_PARTICLE_COLUMNS = [
    "iStep", "time", "X", "Y", "Z", "Vx", "Vy", "Vz", "Rx", "Ry", "Rz",
    "Fx", "Fy", "Fz", "Mx", "My", "Mz",
    "Fcpx", "Fcpy", "Fcpz", "Tcpx", "Tcpy", "Tcpz",
    "SumUx", "SumUy", "SumUz", "SumTx", "SumTy", "SumTz",
]  # fmt: skip

# Output schema (one row per config x timestep). The normative copy is the
# force-surrogate spec scenario "Columns are the documented schema".
DATASET_COLUMNS = [
    "config_name",
    "index",
    "time",
    "phase",
    "wingbeat",
    "stroke_amp_deg",
    "frequency_fstar",
    "pitch_amp_deg",
    "reynolds",
    "split",
    "Fx",
    "Fy",
    "Fz",
    "Mx",
    "My",
    "Mz",
    "CF_x",
    "CF_y",
    "CF_z",
    "CF_mx",
    "CF_my",
    "CF_mz",
]

# Units of the *measured* dataset columns (CC-5; validated against UNITS_VOCABULARY).
# String columns (config_name, split) and bookkeeping counts (index, wingbeat) are omitted,
# mirroring the sweep-manifest units convention. No new vocabulary entry is needed.
_DATASET_UNITS = {
    "time": "dimensionless",
    "phase": "dimensionless",
    "stroke_amp_deg": "deg",
    "frequency_fstar": "dimensionless (f*)",
    "pitch_amp_deg": "deg",
    "reynolds": "dimensionless",
    "Fx": "dimensionless",
    "Fy": "dimensionless",
    "Fz": "dimensionless",
    "Mx": "dimensionless",
    "My": "dimensionless",
    "Mz": "dimensionless",
    "CF_x": "dimensionless",
    "CF_y": "dimensionless",
    "CF_z": "dimensionless",
    "CF_mx": "dimensionless",
    "CF_my": "dimensionless",
    "CF_mz": "dimensionless",
}


def _extract_config(config: Mapping, csv_path: Path) -> pd.DataFrame:
    """Build the per-config rows from one IB-particle CSV (name-based, normalized)."""
    raw = pd.read_csv(csv_path)
    f_star = float(config["frequency_fstar"])
    stroke = float(config["stroke_amp_deg"])

    time = raw["time"].to_numpy(dtype=float)
    fx = raw["Fx"].to_numpy(dtype=float)
    fy = raw["Fy"].to_numpy(dtype=float)
    fz = raw["Fz"].to_numpy(dtype=float)
    mx = raw["Mx"].to_numpy(dtype=float)
    my = raw["My"].to_numpy(dtype=float)
    mz = raw["Mz"].to_numpy(dtype=float)

    f_ref = compute_force_reference(f_star, stroke, R_TIP, SPAN, CHORD, RHO).f_ref
    m_ref = compute_moment_reference(f_star, stroke, R_TIP, SPAN, CHORD, RHO).m_ref
    fc = compute_force_coefficients(fx, fy, fz, f_ref)
    mc = compute_moment_coefficient(mx, my, mz, m_ref)

    cycles = time * f_star
    phase = np.mod(cycles, 1.0)
    wingbeat = np.floor(cycles).astype(np.int64)

    n = time.shape[0]
    return pd.DataFrame(
        {
            "config_name": [str(config["name"])] * n,
            "index": np.full(n, int(config["index"]), dtype=np.int64),
            "time": time,
            "phase": phase,
            "wingbeat": wingbeat,
            "stroke_amp_deg": np.full(n, stroke, dtype=float),
            "frequency_fstar": np.full(n, f_star, dtype=float),
            "pitch_amp_deg": np.full(n, float(config["pitch_amp_deg"]), dtype=float),
            "reynolds": np.full(n, float(config["reynolds"]), dtype=float),
            "split": [str(config["split"])] * n,
            "Fx": fx,
            "Fy": fy,
            "Fz": fz,
            "Mx": mx,
            "My": my,
            "Mz": mz,
            "CF_x": np.asarray(fc.cf_x, dtype=float),
            "CF_y": np.asarray(fc.cf_y, dtype=float),
            "CF_z": np.asarray(fc.cf_z, dtype=float),
            "CF_mx": np.asarray(mc.cf_mx, dtype=float),
            "CF_my": np.asarray(mc.cf_my, dtype=float),
            "CF_mz": np.asarray(mc.cf_mz, dtype=float),
        }
    )


def build_dataset(
    manifest_path: Path | str,
    csv_paths: Mapping[str, Path | str],
    *,
    allow_missing: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """Extract the tidy force-coefficient dataset from per-config IB-particle CSVs.

    For each config in ``sweep_manifest.json`` this reads its IB-particle CSV name-based,
    computes the per-config ``F_ref``/``M_ref`` via the single-source normalization helpers
    (CC-3), and emits one row per ``(config, timestep)`` with kinematics, ``phase``,
    ``wingbeat``, the six coefficients, and the raw forces/moments.

    Args:
        manifest_path: Path to the sweep manifest (its ``configs[]`` drives the join).
        csv_paths: Mapping of config ``name`` to its IB-particle CSV path. A config whose
            name is absent from the mapping, or whose path does not exist on disk, is
            "missing"; a present header-only CSV (zero data rows) is **not** missing and
            simply contributes zero rows.
        allow_missing: If ``False`` (default) a missing CSV raises ``ValueError`` naming the
            config. If ``True`` the config is skipped with a logged warning and its name is
            returned in the second element.

    Returns:
        ``(frame, dropped)`` — the tidy dataframe (columns :data:`DATASET_COLUMNS`) and the
        list of config names dropped under ``allow_missing`` (``[]`` for a complete build).

    Raises:
        ValueError: If a config's CSV is missing and ``allow_missing`` is ``False``.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    configs = manifest["configs"]

    frames: list[pd.DataFrame] = []
    dropped: list[str] = []
    for config in configs:
        name = str(config["name"])
        raw_path = csv_paths.get(name)
        path = Path(raw_path) if raw_path is not None else None
        if path is None or not path.exists():
            if allow_missing:
                logger.warning(
                    "config %r has no IB-particle CSV at %r; skipping (allow_missing=True)",
                    name,
                    str(path) if path is not None else None,
                )
                dropped.append(name)
                continue
            raise ValueError(
                f"IB-particle CSV missing for config {name!r} "
                f"(path={str(path) if path is not None else None!r}); pass allow_missing=True "
                "to skip missing configs and record them in run metadata."
            )
        frames.append(_extract_config(config, path))

    if frames:
        df = pd.concat(frames, ignore_index=True)
        df = df[DATASET_COLUMNS]
    else:
        df = pd.DataFrame({col: [] for col in DATASET_COLUMNS})
    return df, dropped


def write_dataset(
    df: pd.DataFrame,
    parquet_path: Path | str,
    units_path: Path | str,
) -> None:
    """Write the dataset to parquet and emit its ``dataset.units.json`` sidecar.

    The units sidecar (CC-5) declares the unit of every *measured* column from the static
    :data:`_DATASET_UNITS` map via :func:`write_units_sidecar`; string/bookkeeping columns
    are omitted. The parquet is written with the default engine (pyarrow); it is **not**
    byte-reproducible (pyarrow embeds writer metadata), so reproducibility is asserted at the
    schema+value level, not bytewise.

    Args:
        df: The tidy dataset from :func:`build_dataset`.
        parquet_path: Output path for the parquet file.
        units_path: Output path for the ``dataset.units.json`` sidecar.
    """
    parquet_path = Path(parquet_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    write_units_sidecar(Path(units_path), _DATASET_UNITS)


def build_run_metadata(
    *,
    docker_image_digest: str,
    timestamp: str,
    dropped_configs: list[str],
    inputs_file: Path | str | None = None,
) -> dict:
    """Capture provenance for a dataset build (CC-1), recording any dropped configs.

    Wraps :func:`capture_surrogate_run_metadata` (which requires a pinned ``sha256:``
    container digest — the dataset is downstream of the PR3 container run — and accepts a
    caller-supplied timestamp). The dropped-config names are passed via ``extra``; because
    the base capture merges ``extra`` with ``dict.update``, they land at the **top level**
    of the returned metadata under ``dropped_configs`` (not nested under ``extra``), so a
    truncated corpus is auditable.

    Args:
        docker_image_digest: Pinned ``sha256:`` image reference (a mutable tag is rejected).
        timestamp: Caller-supplied ISO-8601 timestamp.
        dropped_configs: Config names skipped under ``allow_missing`` (``[]`` if none).
        inputs_file: Optional inputs file whose SHA256 is recorded.

    Returns:
        The provenance metadata dict, with ``dropped_configs`` at the top level.
    """
    return capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        inputs_file=Path(inputs_file) if inputs_file is not None else None,
        timestamp=timestamp,
        extra={"dropped_configs": list(dropped_configs)},
    )
