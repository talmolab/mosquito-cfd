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
- **Moment reference point** (OpenSpec change ``fix-moment-reference-hinge``): IAMReX takes
  its moments about the IB particle's own origin, which it writes to the CSV's ``X,Y,Z``
  columns. The derived ``CF_m*`` are shifted to the deck's declared pivot
  (``particle_inputs.hinge_*``, read from the deck the manifest's ``input_file`` names) with
  :func:`.normalization.shift_moment_reference`; the raw ``M*`` columns keep the solver's
  values. The canonical definition is ``docs/coordinate-convention.md`` ``## Moments``.
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN
from mosquito_cfd.force_surrogate.geometry_guard import read_deck_value
from mosquito_cfd.force_surrogate.normalization import (
    compute_force_coefficients,
    compute_force_reference,
    compute_moment_coefficient,
    compute_moment_reference,
    shift_moment_reference,
)
from mosquito_cfd.force_surrogate.sidecar import (
    capture_surrogate_run_metadata,
    load_json_clear_error,
    write_units_sidecar,
)

logger = logging.getLogger(__name__)

# The real IAMReX IB-particle CSV schema (29 columns, exact order). The extractor reads
# name-based (so it does not depend on this list), but it is exported as the single source of
# truth for consumers/tests (e.g. building header-only fixtures, asserting the schema).
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

# Manifest config keys build_dataset reads, and the CSV columns _extract_config reads.
_REQUIRED_CONFIG_KEYS = frozenset(
    {
        "name",
        "index",
        "stroke_amp_deg",
        "frequency_fstar",
        "pitch_amp_deg",
        "reynolds",
        "split",
    }
)
# X,Y,Z are the moment origin IAMReX wrote (kernel.location); the shift needs them.
# fmt: skip keeps the tuple on one line, in the CSV header's own column order.
_REQUIRED_CSV_COLUMNS = (
    "iStep", "time", "X", "Y", "Z", "Fx", "Fy", "Fz", "Mx", "My", "Mz",
)  # fmt: skip

# String / integer-count output columns; everything else in DATASET_COLUMNS is float64.
# Used to give the empty (all-dropped) frame the SAME dtypes as a populated frame so the
# parquet schema is stable across builds. ``"str"`` is the pandas-3.0 default string dtype
# (StringDtype), which is what a populated frame's string columns resolve to.
_STR_COLUMNS = frozenset({"config_name", "split"})
_INT_COLUMNS = frozenset({"index", "wingbeat"})

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


def _empty_dataset() -> pd.DataFrame:
    """An empty dataset frame with the populated-frame dtypes (stable parquet schema)."""
    columns = {}
    for col in DATASET_COLUMNS:
        if col in _STR_COLUMNS:
            dtype = "str"
        elif col in _INT_COLUMNS:
            dtype = "int64"
        else:
            dtype = "float64"
        columns[col] = pd.Series([], dtype=dtype)
    return pd.DataFrame(columns)


class ConfigExtractionError(ValueError):
    """A configuration's own inputs are unusable for extraction.

    Raised for no locatable deck, no finite declared hinge, a deck changed since its run, or a
    CSV missing required columns or with a non-finite / non-constant moment origin. A
    ``ValueError`` subclass, so callers that catch ``ValueError`` are unaffected; the
    acceptance gate catches this narrower type to report the config as a failure while
    letting malformed-file errors (bad JSON) propagate as before.
    """


class DatasetBuild(NamedTuple):
    """What :func:`build_dataset` returns.

    Attributes:
        frame: The tidy dataframe (columns :data:`DATASET_COLUMNS`).
        dropped: Config names skipped under ``allow_missing`` (``[]`` for a complete build).
        provenance: Per-config record of what extraction consumed and applied, keyed by config
            name (dropped configs have none): ``origin``/``hinge``/``offset`` (the moment
            origin from the CSV, the deck's pivot, and ``origin - hinge``, each a 3-list;
            ``origin``/``offset`` are ``None`` for a header-only CSV), ``deck`` (the
            manifest's ``input_file``), ``deck_sha256``, ``deck_sha256_verified_against``
            (the per-config run-metadata file whose recorded ``deck_sha256`` matched, or
            ``None`` when the run recorded none), and ``csv_sha256`` (of the exact bytes
            parsed). Returned rather than re-derived by the caller, so what is recorded is
            what was applied.
    """

    frame: pd.DataFrame
    dropped: list[str]
    provenance: dict[str, dict[str, Any]]


def _resolve_deck(config: Mapping, manifest_dir: Path) -> tuple[str, Path]:
    """Locate a config's deck via its manifest ``input_file``, relative to the manifest."""
    name = str(config["name"])
    input_file = config.get("input_file")
    if not isinstance(input_file, str) or not input_file:
        raise ConfigExtractionError(
            f"config {name!r} has no usable 'input_file' entry in the manifest "
            f"(got {input_file!r}); its deck is needed for the moment reference point "
            "(particle_inputs.hinge_*)"
        )
    deck_path = manifest_dir / input_file
    if not deck_path.is_file():
        raise ConfigExtractionError(
            f"deck for config {name!r} not found at {deck_path} (manifest input_file "
            f"{input_file!r}, resolved against the manifest's directory)"
        )
    return input_file, deck_path


def _read_hinge(name: str, deck_path: Path, deck_bytes: bytes) -> np.ndarray:
    """Read the deck's declared pivot, naming the config and deck on any failure."""
    try:
        deck_text = deck_bytes.decode("utf-8")
        return np.array(
            [
                read_deck_value(deck_text, f"particle_inputs.hinge_{axis}")
                for axis in "xyz"
            ],
            dtype=float,
        )
    except ValueError as exc:  # UnicodeDecodeError is a ValueError subclass
        raise ConfigExtractionError(
            f"deck for config {name!r} at {deck_path} has no usable moment reference "
            f"point: {exc}. Refusing to fall back to the particle origin, which would "
            "silently reinstate particle-origin moments."
        ) from exc


def _verify_deck_sha256(
    name: str, deck_path: Path, deck_sha256: str, metadata_path: Path | None
) -> str | None:
    """Reconcile the deck against the ``deck_sha256`` its run recorded, if it recorded one.

    The deck is a mutable working-tree file while the CSV was written by the solver; a deck
    edited without re-running the CFD would shift about a hinge the run never used. Returns
    the anchoring metadata file's name, or ``None`` when there is no anchor (no per-config
    run metadata, or one without ``deck_sha256`` -- the coarse corpus's known limitation).
    """
    if metadata_path is None or not metadata_path.is_file():
        return None
    metadata = load_json_clear_error(metadata_path, label="run_metadata file")
    if not isinstance(metadata, Mapping):
        raise ConfigExtractionError(
            f"run metadata for config {name!r} at {metadata_path} is a JSON "
            f"{type(metadata).__name__}, not an object"
        )
    recorded = metadata.get("deck_sha256")
    if recorded is None:
        return None
    if not isinstance(recorded, str):
        raise ConfigExtractionError(
            f"run metadata for config {name!r} at {metadata_path} records a non-string "
            f"deck_sha256 {recorded!r}"
        )
    if recorded.lower() != deck_sha256:
        raise ConfigExtractionError(
            f"deck for config {name!r} at {deck_path} has sha256 {deck_sha256}, but its run "
            f"recorded deck_sha256 {recorded} in {metadata_path}: the deck changed after the "
            "CFD ran, so its hinge is not the one the solver's moments belong to"
        )
    return metadata_path.name


def _moment_origin(name: str, csv_path: Path, raw: pd.DataFrame) -> np.ndarray | None:
    """The run's moment origin from ``X,Y,Z``.

    It must be finite and exactly constant; ``None`` if the CSV has no rows.
    """
    if len(raw) == 0:
        return None
    origin = []
    for axis in ("X", "Y", "Z"):
        try:
            values = raw[axis].to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ConfigExtractionError(
                f"IB-particle CSV for config {name!r} at {csv_path} has a non-numeric "
                f"moment origin in column {axis!r}: {exc}"
            ) from exc
        # Explicit: pandas' max()-min() and nunique() both skip NaN, so a naive constancy
        # check would pass [4, nan, 4].
        if not np.isfinite(values).all():
            raise ConfigExtractionError(
                f"IB-particle CSV for config {name!r} at {csv_path} has a non-finite moment "
                f"origin in column {axis!r}; refusing to derive a NaN/inf shift"
            )
        if not (values == values[0]).all():
            raise ConfigExtractionError(
                f"IB-particle CSV for config {name!r} at {csv_path} has a moment origin that "
                f"is not constant in column {axis!r} (range {float(values.min())!r}.."
                f"{float(values.max())!r}): the particle moved, so no single parallel-axis shift "
                "describes the run"
            )
        origin.append(values[0])
    return np.array(origin, dtype=float)


def _extract_config(
    config: Mapping, csv_path: Path, manifest_dir: Path, metadata_path: Path | None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build the per-config rows from one IB-particle CSV (name-based, normalized).

    Also returns the record of what was consumed and applied (see :class:`DatasetBuild`).
    """
    name = str(config["name"])
    input_file, deck_path = _resolve_deck(config, manifest_dir)
    deck_bytes = deck_path.read_bytes()
    deck_sha256 = hashlib.sha256(deck_bytes).hexdigest()
    verified_against = _verify_deck_sha256(name, deck_path, deck_sha256, metadata_path)
    hinge = _read_hinge(name, deck_path, deck_bytes)

    # Hash and parse the SAME bytes, so the recorded hash is of what was consumed.
    csv_bytes = Path(csv_path).read_bytes()
    raw = pd.read_csv(io.BytesIO(csv_bytes))
    missing = [c for c in _REQUIRED_CSV_COLUMNS if c not in raw.columns]
    if missing:
        raise ConfigExtractionError(
            f"IB-particle CSV for config {name!r} at {csv_path} is missing required "
            f"column(s) {missing}; expected the IAMReX schema {list(_REQUIRED_CSV_COLUMNS)}"
        )
    f_star = float(config["frequency_fstar"])
    stroke = float(config["stroke_amp_deg"])

    # ns.init_iter=N causes IAMReX to write 1+N rows at iStep=0 (the first all-zero, the
    # rest the post_init_press iterations). Deduplicate on iStep, keeping the LAST row per
    # step -- it is the converged value; the first is a non-physical zero-force placeholder.
    # A no-op for a CSV with no duplicate iStep (init_iter=None/0, the coarse-corpus shape).
    istep = raw["iStep"].to_numpy()
    if not np.all(np.diff(istep) >= 0):
        raise ValueError(
            f"IB-particle CSV for config {name!r} at {csv_path} has a non-monotonic iStep "
            "sequence (e.g. a checkpoint restart re-emitting already-seen steps); refusing "
            "to deduplicate, since keep='last' would silently discard the earlier, correct "
            "rows rather than the restart's stale ones"
        )
    duplicated_isteps = set(raw.loc[raw["iStep"].duplicated(keep=False), "iStep"])
    if duplicated_isteps - {0}:
        raise ValueError(
            f"IB-particle CSV for config {name!r} at {csv_path} has duplicate iStep values "
            f"{sorted(duplicated_isteps - {0})} other than the expected ns.init_iter "
            "re-emission at iStep=0; refusing to deduplicate a pattern that does not match "
            "any known cause (e.g. a solver-writer bug that never advances iStep would "
            "otherwise silently collapse the whole file to a single row)"
        )
    raw = raw.drop_duplicates(subset="iStep", keep="last")
    origin = _moment_origin(name, csv_path, raw)
    offset = None if origin is None else origin - hinge

    time = raw["time"].to_numpy(dtype=float)
    fx = raw["Fx"].to_numpy(dtype=float)
    fy = raw["Fy"].to_numpy(dtype=float)
    fz = raw["Fz"].to_numpy(dtype=float)
    mx = raw["Mx"].to_numpy(dtype=float)
    my = raw["My"].to_numpy(dtype=float)
    mz = raw["Mz"].to_numpy(dtype=float)

    f_ref = compute_force_reference(f_star, stroke, R_GYRATION, SPAN, CHORD, RHO).f_ref
    m_ref = compute_moment_reference(f_star, stroke, R_GYRATION, SPAN, CHORD, RHO).m_ref
    fc = compute_force_coefficients(fx, fy, fz, f_ref)
    # Reference-frame change before normalization, into new arrays: raw M* stay as written.
    if offset is None:
        hinge_moments = (mx, my, mz)  # zero rows; nothing to shift
    else:
        hinge_moments = shift_moment_reference(mx, my, mz, fx, fy, fz, offset=offset)
    mc = compute_moment_coefficient(*hinge_moments, m_ref)

    cycles = time * f_star
    phase = np.mod(cycles, 1.0)
    wingbeat = np.floor(cycles).astype(np.int64)

    record = {
        "origin": None if origin is None else origin.tolist(),
        "hinge": hinge.tolist(),
        "offset": None if offset is None else offset.tolist(),
        "deck": input_file,
        "deck_sha256": deck_sha256,
        "deck_sha256_verified_against": verified_against,
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
    }

    n = time.shape[0]
    frame = pd.DataFrame(
        {
            # Explicit "str" dtype so a 0-row CSV yields StringDtype (not float64) — matches
            # the populated and empty-build schemas for a stable parquet across builds.
            "config_name": pd.array([str(config["name"])] * n, dtype="str"),
            "index": np.full(n, int(config["index"]), dtype=np.int64),
            "time": time,
            "phase": phase,
            "wingbeat": wingbeat,
            "stroke_amp_deg": np.full(n, stroke, dtype=float),
            "frequency_fstar": np.full(n, f_star, dtype=float),
            "pitch_amp_deg": np.full(n, float(config["pitch_amp_deg"]), dtype=float),
            "reynolds": np.full(n, float(config["reynolds"]), dtype=float),
            "split": pd.array([str(config["split"])] * n, dtype="str"),
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
    return frame, record


def _validate_configs(configs: object) -> None:
    """Validate the manifest config list before any extraction (clear errors, no KeyError)."""
    if not isinstance(configs, list):
        raise ValueError(
            f"manifest 'configs' must be a list, got {type(configs).__name__}"
        )
    seen: set[str] = set()
    for i, config in enumerate(configs):
        if not isinstance(config, Mapping):
            raise ValueError(f"manifest config {i} is not a mapping: {config!r}")
        missing = sorted(_REQUIRED_CONFIG_KEYS - set(config))
        if missing:
            raise ValueError(
                f"manifest config {i} is missing required key(s) {missing}; "
                f"expected at least {sorted(_REQUIRED_CONFIG_KEYS)}"
            )
        name = str(config["name"])
        if name in seen:
            raise ValueError(
                f"duplicate config name {name!r} in manifest (config {i}); names must be "
                "unique so each maps to one CSV and one split"
            )
        seen.add(name)


def load_manifest_configs(manifest_path: Path | str) -> list[dict]:
    """Read a sweep manifest and return its validated ``configs`` list.

    Validation (clear ``ValueError`` on a missing ``configs`` key, a non-list ``configs``, a
    non-mapping/missing-key config, or duplicate config names) happens here so **both** the
    driver (which resolves CSV paths from the config names) and :func:`build_dataset` go
    through the same guarded reader — a malformed manifest never surfaces as a bare
    ``KeyError``/``TypeError`` on either path.

    Args:
        manifest_path: Path to the sweep manifest JSON.

    Returns:
        The validated ``configs`` list.

    Raises:
        ValueError: If the manifest has no ``configs`` key, ``configs`` is not a list, or a
            config is malformed / has a duplicate name.
    """
    manifest = load_json_clear_error(Path(manifest_path), label="sweep manifest")
    if "configs" not in manifest:
        raise ValueError(
            f"manifest {Path(manifest_path)} has no 'configs' key; not a sweep manifest"
        )
    configs = manifest["configs"]
    _validate_configs(configs)
    return configs


def build_dataset(
    manifest_path: Path | str,
    csv_paths: Mapping[str, Path | str],
    *,
    allow_missing: bool = False,
    run_metadata_paths: Mapping[str, Path | str] | None = None,
) -> DatasetBuild:
    """Extract the tidy force-coefficient dataset from per-config IB-particle CSVs.

    For each config in ``sweep_manifest.json`` this reads its IB-particle CSV name-based,
    computes the per-config ``F_ref``/``M_ref`` via the single-source normalization helpers
    (CC-3), and emits one row per ``(config, timestep)`` with kinematics, ``phase``,
    ``wingbeat``, the six coefficients, and the raw forces/moments.

    Moment coefficients are taken about the deck's declared pivot: each config's deck is
    located via its manifest ``input_file`` (relative to the manifest's directory), and the
    solver's moments -- about the origin in the CSV's ``X,Y,Z`` -- are shifted by
    ``(origin - hinge) x F`` before normalization. The raw ``Mx/My/Mz`` columns are unshifted.
    See ``docs/coordinate-convention.md`` ``## Moments``.

    Args:
        manifest_path: Path to the sweep manifest (its ``configs[]`` drives the join, and
            its directory anchors each config's ``input_file``).
        csv_paths: Mapping of config ``name`` to its IB-particle CSV path. A config whose
            name is absent from the mapping, or whose path does not exist on disk, is
            "missing"; a present header-only CSV (zero data rows) is **not** missing and
            simply contributes zero rows.
        allow_missing: If ``False`` (default) a missing CSV raises ``ValueError`` naming the
            config. If ``True`` the config is skipped with a logged warning and its name is
            returned in the second element.
        run_metadata_paths: Optional mapping of config name to its per-config run
            metadata, whose recorded ``deck_sha256`` the deck is reconciled against. When
            omitted, ``run_metadata_<name>.json`` beside the manifest is used. A config
            absent from the mapping, or whose file does not exist, has no anchor and is
            recorded as unverified.

    Returns:
        A :class:`DatasetBuild` ``(frame, dropped, provenance)``.

    Raises:
        ConfigExtractionError: (a ``ValueError``) if a config's own inputs are unusable:
            its deck cannot be located or decoded, lacks a finite
            ``particle_inputs.hinge_*``, or no longer matches the ``deck_sha256`` its run
            recorded; its run metadata is not a JSON object; or its CSV lacks a required
            column or has a non-numeric, non-finite or non-constant ``X,Y,Z`` origin.
        ValueError: If a config's CSV is missing and ``allow_missing`` is ``False``, or on
            a malformed manifest, run-metadata JSON or ``iStep`` sequence.
    """
    configs = load_manifest_configs(manifest_path)
    manifest_dir = Path(manifest_path).parent

    def metadata_path_for(name: str) -> Path | None:
        if run_metadata_paths is None:
            return manifest_dir / f"run_metadata_{name}.json"
        raw_path = run_metadata_paths.get(name)
        return Path(raw_path) if raw_path is not None else None

    frames: list[pd.DataFrame] = []
    dropped: list[str] = []
    provenance: dict[str, dict[str, Any]] = {}
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
        frame, record = _extract_config(
            config, path, manifest_dir, metadata_path_for(name)
        )
        frames.append(frame)
        provenance[name] = record

    if frames:
        df = pd.concat(frames, ignore_index=True)
        df = df[DATASET_COLUMNS]
    else:
        df = _empty_dataset()
    return DatasetBuild(df, dropped, provenance)


def moment_reference_provenance(
    provenance: Mapping[str, Mapping[str, Any]],
    *,
    input_dir: Path | str,
    csv_name: str,
) -> dict[str, dict[str, Any]]:
    """The corpus ``run_metadata.json`` entries recording the moment frame and the inputs.

    Built from :attr:`DatasetBuild.provenance` -- what extraction actually applied and
    consumed -- never re-derived. Pass the result as :func:`build_run_metadata`'s ``extra``.
    Recorded here and **not** in ``dataset.units.json``, whose closed vocabulary admits only
    unit strings.

    Args:
        provenance: The per-config records from :func:`build_dataset`.
        input_dir: The runs directory the CSVs were read from. Recorded exactly as given
            (posix separators), not resolved: resolving a mapped drive yields a
            machine-specific network path. ``csv_sha256`` is the inputs' identity; the
            directory is only a locator.
        csv_name: The per-config CSV filename under ``<input_dir>/<config>/``.

    Returns:
        ``{"moment_reference": ..., "extraction_inputs": ...}``. ``moment_reference`` names the
        point (``"wing_hinge"``), its canonical definition, that the axes are lab axes, the
        offset convention, what the raw ``M*`` are about, and each config's ``origin``,
        ``hinge``, ``offset``, ``deck``, ``deck_sha256`` and ``deck_sha256_verified_against``.
        ``extraction_inputs`` records ``input_dir``, ``csv_name`` and per-config
        ``csv_sha256``.
    """
    return {
        "moment_reference": {
            "point": "wing_hinge",
            "definition": "docs/coordinate-convention.md#moments",
            "axes": "lab",
            "offset": "r_origin - r_hinge",
            "applies_to": ["CF_mx", "CF_my", "CF_mz"],
            "raw_moments_about": "particle_origin",
            "configs": {
                name: {k: v for k, v in record.items() if k != "csv_sha256"}
                for name, record in provenance.items()
            },
        },
        "extraction_inputs": {
            "input_dir": Path(input_dir).as_posix(),
            "csv_name": csv_name,
            "csv_sha256": {
                name: record["csv_sha256"] for name, record in provenance.items()
            },
        },
    }


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
    extra: Mapping[str, Any] | None = None,
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
        extra: Optional further top-level entries (e.g. the moment-reference record). A key
            colliding with ``dropped_configs`` or a base provenance key is rejected rather
            than silently overwriting it.

    Returns:
        The provenance metadata dict, with ``dropped_configs`` (and any ``extra``) at the
        top level.

    Raises:
        ValueError: On a mutable image tag, or an ``extra`` key collision.
    """
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        inputs_file=Path(inputs_file) if inputs_file is not None else None,
        timestamp=timestamp,
        extra={"dropped_configs": list(dropped_configs)},
    )
    extra = dict(extra or {})
    collisions = sorted(set(extra) & set(metadata))
    if collisions:
        raise ValueError(
            f"build_run_metadata extra key(s) {collisions} collide with existing "
            "provenance keys; refusing to overwrite them"
        )
    metadata.update(extra)
    return metadata
