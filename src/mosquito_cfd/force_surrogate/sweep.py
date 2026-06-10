"""Kinematic sweep generator for the force surrogate (Track B, PR2).

Produces a reproducible corpus of IAMReX input decks over the Aedes-anchored 3-parameter
kinematic grid (stroke amplitude x dimensionless frequency x pitch amplitude), reusing the
validated ``examples/flapping_wing/inputs.3d.validation`` as the base. Pure and cluster-free:
no RunAI, GPU, or plotfiles (roadmap CC-2, CC-6).

Design decisions are documented in the OpenSpec change ``add-force-surrogate-sweep-config``
(``design.md`` D1-D9). Key points:

- **CC-7 (D1):** viscosity ``nu_star`` is held FIXED at the validated 0.115; Reynolds number
  therefore varies across the sweep as a deterministic function of stroke and frequency, and
  is recorded per config.
- **Reynolds arm (D2):** :func:`compute_reynolds` uses the midspan arm ``R_MID = 1.5``, NOT the
  force-normalization tip arm ``R_TIP = 3.0``.
- **Run duration (D3):** each config is scaled to cover ``N_WINGBEATS`` whole wingbeats.
- **Force-only (D6):** ``amr.plot_int`` is forced to -1; only the swept/derived keys change.
- **Reproducibility (D5-D7):** ``generate_sweep`` writes a deterministic ``sweep_manifest.json``
  (byte-reproducible), a ``sweep_manifest.units.json``, and a separate ``sweep_provenance.json``
  (git/timestamp/base-hash, kept out of the manifest so the git SHA cannot defeat byte-identity).
"""

from __future__ import annotations

import itertools
import json
import math
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from mosquito_cfd.benchmarks.metadata import get_git_info, hash_file
from mosquito_cfd.force_surrogate.constants import (
    AEDES_FREQUENCY_FSTAR,
    AEDES_PITCH_AMP_DEG,
    AEDES_STROKE_AMP_DEG,
    DT,
    HOLDOUT_SEED,
    N_HOLDOUT,
    N_WINGBEATS,
    R_MID,
    VALIDATED_NU_STAR,
)
from mosquito_cfd.force_surrogate.sidecar import write_units_sidecar

# The exact schema of a sweep config (matches tests/fixtures/micro_sweep.json).
_CONFIG_KEYS = frozenset({"stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"})

# Units of the measured manifest columns (validated against UNITS_VOCABULARY on write).
_MANIFEST_UNITS = {
    "stroke_amp_deg": "deg",
    "pitch_amp_deg": "deg",
    "frequency_fstar": "dimensionless (f*)",
    "nu_star": "dimensionless",
    "reynolds": "dimensionless",
    "stop_time": "dimensionless",
}


def build_kinematic_grid(
    stroke_amp_deg: Sequence[float] = AEDES_STROKE_AMP_DEG,
    frequency_fstar: Sequence[float] = AEDES_FREQUENCY_FSTAR,
    pitch_amp_deg: Sequence[float] = AEDES_PITCH_AMP_DEG,
) -> list[dict[str, float]]:
    """Build the kinematic sweep grid as a pure function of its level inputs.

    Configs are emitted in ``itertools.product(stroke, freq, pitch)`` C-order (stroke
    outermost, pitch innermost) so the order is canonical and reproducible.

    Args:
        stroke_amp_deg: Stroke amplitude levels [deg]. Defaults to the Aedes levels.
        frequency_fstar: Dimensionless frequency levels (f*). Defaults to the Aedes levels.
        pitch_amp_deg: Pitch amplitude levels [deg]. Defaults to the Aedes levels.

    Returns:
        One dict per grid point with keys ``stroke_amp_deg``, ``frequency_fstar``,
        ``pitch_amp_deg`` (the schema of ``tests/fixtures/micro_sweep.json``).
    """
    return [
        {
            "stroke_amp_deg": float(stroke),
            "frequency_fstar": float(freq),
            "pitch_amp_deg": float(pitch),
        }
        for stroke, freq, pitch in itertools.product(
            stroke_amp_deg, frequency_fstar, pitch_amp_deg
        )
    ]


def compute_reynolds(
    stroke_amp_deg: float,
    frequency_fstar: float,
    nu_star: float,
    r_mid: float = R_MID,
) -> float:
    """Reynolds number from kinematics, using the midspan arm.

    ``Re = 2*pi * f* * radians(stroke_amp_deg) * r_mid / nu_star``. The midspan arm
    ``r_mid = R_MID = 1.5`` is the viscous-scaling arm — NOT the force-normalization tip arm
    ``R_TIP = 3.0`` (constants.py warns against conflating them). Reproduces Re ~ 100 at the
    validated phi=70 deg, f*=1.0, nu*=0.115 point.

    Args:
        stroke_amp_deg: Stroke amplitude [deg].
        frequency_fstar: Dimensionless flap frequency (f*).
        nu_star: Dimensionless viscosity (``ns.vel_visc_coef``). Must be positive.
        r_mid: Midspan arm [dimensionless]. Defaults to :data:`R_MID`.

    Returns:
        The dimensionless Reynolds number.

    Raises:
        ValueError: If ``nu_star <= 0`` (degenerate/non-physical viscosity).
    """
    if nu_star <= 0:
        raise ValueError(
            f"nu_star must be positive to form a Reynolds number (got {nu_star})"
        )
    u_tip_mid = 2.0 * math.pi * frequency_fstar * math.radians(stroke_amp_deg) * r_mid
    return u_tip_mid / nu_star


def derive_run_duration(
    frequency_fstar: float,
    n_wingbeats: int = N_WINGBEATS,
    dt: float = DT,
) -> tuple[int, float]:
    """Run duration scaled to cover whole wingbeats at a fixed timestep.

    ``stop_time = n_wingbeats / f*``; ``max_step = round(stop_time / dt)``. ``dt`` is held at
    the validated value, so even low-frequency configs (where a fixed ``stop_time`` would cover
    less than one beat) capture whole periodic cycles.

    Args:
        frequency_fstar: Dimensionless flap frequency (f*). Must be positive.
        n_wingbeats: Number of complete wingbeats to cover. Defaults to :data:`N_WINGBEATS`.
        dt: Fixed timestep [dimensionless time]. Defaults to :data:`DT`.

    Returns:
        ``(max_step, stop_time)``.

    Raises:
        ValueError: If ``frequency_fstar <= 0``.
    """
    if frequency_fstar <= 0:
        raise ValueError(f"frequency_fstar must be positive (got {frequency_fstar})")
    stop_time = n_wingbeats / frequency_fstar
    max_step = round(stop_time / dt)
    return max_step, stop_time


def _is_corner(config: dict[str, float], extremes: dict[str, set[float]]) -> bool:
    """True if every parameter of ``config`` sits at an extreme level of the grid."""
    return all(config[key] in extremes[key] for key in _CONFIG_KEYS)


def select_holdout(
    configs: Sequence[dict[str, float]],
    n_holdout: int = N_HOLDOUT,
    seed: int = HOLDOUT_SEED,
) -> list[int]:
    """Select held-out config indices, seeded and drawn from grid non-corners (CC-4).

    A corner has all three parameters at an extreme level; held-out points are chosen only
    from non-corners so the eventual evidence figure measures interpolation, not extrapolation.
    The eligible indices are assembled into a **sorted** list before sampling (never a
    hash-ordered set), so the result is reproducible independent of ``PYTHONHASHSEED``.

    Args:
        configs: The sweep configs.
        n_holdout: Number of configs to hold out. Defaults to :data:`N_HOLDOUT`.
        seed: Seed for ``numpy.random.default_rng``. Defaults to :data:`HOLDOUT_SEED`.

    Returns:
        A sorted list of held-out indices (empty if ``n_holdout == 0``).

    Raises:
        ValueError: If ``n_holdout`` exceeds the number of non-corner eligible configs.
    """
    if n_holdout == 0:
        return []
    if not configs:
        raise ValueError("cannot select a holdout from an empty config list")
    extremes = {
        key: {min(values), max(values)}
        for key in _CONFIG_KEYS
        for values in ({c[key] for c in configs},)
    }
    eligible = sorted(
        i for i, config in enumerate(configs) if not _is_corner(config, extremes)
    )
    if n_holdout > len(eligible):
        raise ValueError(
            f"n_holdout={n_holdout} exceeds the {len(eligible)} non-corner eligible "
            "config(s); reduce n_holdout or widen the grid"
        )
    rng = np.random.default_rng(seed)
    chosen = rng.choice(eligible, size=n_holdout, replace=False)
    return sorted(int(i) for i in chosen)


def render_inputs(
    base_text: str,
    *,
    stroke_amp_deg: float,
    frequency_fstar: float,
    pitch_amp_deg: float,
    max_step: int,
    stop_time: float,
    plot_int: int = -1,
) -> str:
    """Rewrite only the swept/derived keys of an IAMReX inputs deck, preserving the rest.

    Each targeted key is matched on its **full name** (not a prefix), so the prefix-sibling
    ``particle_inputs.kinematics_deviation_amp`` is left untouched. Comments, blank lines,
    ordering, alignment, and unrelated keys pass through unchanged. Output is LF-only with
    deterministic float formatting (shortest round-trippable ``str``) so regeneration is
    byte-identical across platforms.

    Args:
        base_text: The base inputs deck text.
        stroke_amp_deg: Stroke amplitude [deg].
        frequency_fstar: Dimensionless flap frequency (f*).
        pitch_amp_deg: Pitch amplitude [deg].
        max_step: Maximum step count.
        stop_time: Stop time [dimensionless].
        plot_int: Plotfile interval; forced to -1 (force-only) by default.

    Returns:
        The rewritten deck text (LF-terminated).

    Raises:
        ValueError: If any targeted key is absent from ``base_text``.
    """
    replacements = {
        "particle_inputs.kinematics_stroke_amp": str(float(stroke_amp_deg)),
        "particle_inputs.kinematics_frequency": str(float(frequency_fstar)),
        "particle_inputs.kinematics_pitch_amp": str(float(pitch_amp_deg)),
        "max_step": str(int(max_step)),
        "stop_time": str(float(stop_time)),
        "amr.plot_int": str(int(plot_int)),
    }
    remaining = set(replacements)
    out_lines: list[str] = []
    for line in base_text.splitlines():
        # Match the full key left of '='. Only the value token is rewritten; the leading
        # whitespace and everything after the value (trailing spaces + any inline comment)
        # are preserved exactly, so alignment and comments survive byte-for-byte. A comment
        # line like "# nu = 0.1" has a non-key before '=' and is passed through unchanged.
        if "=" in line:
            before, after = line.split("=", 1)
            key = before.strip()
            if key in replacements:
                if key not in remaining:
                    raise ValueError(
                        f"base inputs has a duplicate targeted key: {key!r}"
                    )
                leading_ws = after[: len(after) - len(after.lstrip())]
                tail = after[len(leading_ws) :]
                token_end = 0
                while token_end < len(tail) and not tail[token_end].isspace():
                    token_end += 1
                rest = tail[
                    token_end:
                ]  # trailing whitespace + inline comment, verbatim
                out_lines.append(f"{before}={leading_ws}{replacements[key]}{rest}")
                remaining.discard(key)
                continue
        out_lines.append(line)
    if remaining:
        raise ValueError(
            "base inputs is missing targeted key(s): " + ", ".join(sorted(remaining))
        )
    return "\n".join(out_lines) + "\n"


def _validate_configs(configs: Sequence[dict[str, float]]) -> None:
    """Validate a config list before any file is written (atomicity)."""
    if not configs:
        raise ValueError("config list is empty; nothing to generate")
    for i, config in enumerate(configs):
        if not isinstance(config, dict):
            raise ValueError(f"config {i} is not a mapping: {config!r}")
        keys = set(config)
        if keys != set(_CONFIG_KEYS):
            missing = sorted(_CONFIG_KEYS - keys)
            unknown = sorted(keys - _CONFIG_KEYS)
            raise ValueError(
                f"config {i} has invalid keys (missing={missing}, unknown={unknown}); "
                f"expected exactly {sorted(_CONFIG_KEYS)}"
            )


def _config_name(config: dict[str, float]) -> str:
    """Canonical, sort-stable name: ``s{phi}_f{f*x100:03d}_p{alpha}``."""
    return (
        f"s{int(config['stroke_amp_deg'])}"
        f"_f{round(config['frequency_fstar'] * 100):03d}"
        f"_p{int(config['pitch_amp_deg'])}"
    )


def _write_json(path: Path, data: Any) -> None:
    """Write JSON deterministically: sorted keys, indent=2, UTF-8, LF, trailing newline."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(data, handle, sort_keys=True, indent=2, ensure_ascii=False)
        handle.write("\n")


def _git_commit() -> str | None:
    """Return the current git commit SHA, or the error string / None if unavailable."""
    info = get_git_info()
    return info.get("commit", info.get("error"))


def generate_sweep(
    base_inputs_path: Path | str,
    output_dir: Path | str,
    *,
    timestamp: str,
    configs: Sequence[dict[str, float]] | None = None,
    n_wingbeats: int = N_WINGBEATS,
    nu_star: float = VALIDATED_NU_STAR,
    n_holdout: int = N_HOLDOUT,
    seed: int = HOLDOUT_SEED,
    dt: float = DT,
    r_mid: float = R_MID,
) -> dict[str, Any]:
    """Generate the sweep corpus: one input deck per config plus manifest sidecars.

    Writes ``inputs/inputs.3d.<name>`` per config, a deterministic ``sweep_manifest.json``,
    a ``sweep_manifest.units.json``, and a separate ``sweep_provenance.json`` (git/timestamp/
    base-hash — kept out of the manifest so the non-reproducible git SHA cannot defeat the
    byte-identity guarantee; see design D5). Configs are validated before anything is written.

    Args:
        base_inputs_path: The validated base inputs deck to template.
        output_dir: Directory to write the corpus into (``inputs/`` is created under it).
        timestamp: Caller-supplied ISO-8601 timestamp recorded in the provenance sidecar
            (so artifacts are not stamped with runtime wall-clock; reproducible).
        configs: Configs to generate. Defaults to :func:`build_kinematic_grid`.
        n_wingbeats: Whole wingbeats each config covers. Defaults to :data:`N_WINGBEATS`.
        nu_star: Fixed dimensionless viscosity (CC-7). Defaults to :data:`VALIDATED_NU_STAR`.
        n_holdout: Number of held-out configs. Defaults to :data:`N_HOLDOUT`.
        seed: Holdout selection seed. Defaults to :data:`HOLDOUT_SEED`.
        dt: Fixed timestep. Defaults to :data:`DT`.
        r_mid: Midspan arm for Reynolds. Defaults to :data:`R_MID`.

    Returns:
        The manifest dict (also written to ``sweep_manifest.json``).

    Raises:
        ValueError: If ``configs`` is empty/malformed, or if two configs map to the same
            file name (``_config_name`` is lossy — integer degrees, 0.01 frequency steps).
            All validation runs before any file is written.
    """
    base_path = Path(base_inputs_path)
    base_text = base_path.read_text(encoding="utf-8")
    if configs is None:
        configs = build_kinematic_grid()
    _validate_configs(configs)
    holdout_idx = set(select_holdout(configs, n_holdout, seed))

    # Reject lossy-name collisions before writing anything: distinct configs that round to
    # the same file name would silently overwrite each other's deck.
    names = [_config_name(config) for config in configs]
    collisions = sorted(name for name, count in Counter(names).items() if count > 1)
    if collisions:
        raise ValueError(
            f"distinct configs map to the same input-file name {collisions}; "
            "_config_name uses integer degrees and 0.01 frequency steps, so non-whole-degree "
            "or finer-than-0.01 frequency values can collide and silently overwrite decks"
        )

    output_dir = Path(output_dir)
    inputs_dir = output_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    # Prune any decks from a previous (larger) run so a shrunk config set leaves no orphans
    # that the manifest doesn't list (the manifest is rewritten fully below).
    for stale_deck in inputs_dir.glob("inputs.3d.*"):
        stale_deck.unlink()

    config_records: list[dict[str, Any]] = []
    for index, config in enumerate(configs):
        max_step, stop_time = derive_run_duration(
            config["frequency_fstar"], n_wingbeats, dt
        )
        reynolds = compute_reynolds(
            config["stroke_amp_deg"], config["frequency_fstar"], nu_star, r_mid
        )
        name = names[index]
        rel_path = f"inputs/inputs.3d.{name}"
        deck = render_inputs(
            base_text,
            stroke_amp_deg=config["stroke_amp_deg"],
            frequency_fstar=config["frequency_fstar"],
            pitch_amp_deg=config["pitch_amp_deg"],
            max_step=max_step,
            stop_time=stop_time,
            plot_int=-1,
        )
        with open(output_dir / rel_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(deck)
        config_records.append(
            {
                "index": index,
                "name": name,
                "input_file": rel_path,
                "stroke_amp_deg": config["stroke_amp_deg"],
                "frequency_fstar": config["frequency_fstar"],
                "pitch_amp_deg": config["pitch_amp_deg"],
                "nu_star": nu_star,
                "reynolds": reynolds,
                "max_step": max_step,
                "stop_time": stop_time,
                "plot_int": -1,
                "split": "holdout" if index in holdout_idx else "train",
            }
        )

    holdout_names = [r["name"] for r in config_records if r["split"] == "holdout"]
    manifest = {
        "schema_version": 1,
        "reynolds_policy": "nu_star_fixed",
        "nu_star": nu_star,
        "r_mid": r_mid,
        "dt": dt,
        "n_wingbeats": n_wingbeats,
        "grid": {
            "stroke_amp_deg": sorted({c["stroke_amp_deg"] for c in configs}),
            "frequency_fstar": sorted({c["frequency_fstar"] for c in configs}),
            "pitch_amp_deg": sorted({c["pitch_amp_deg"] for c in configs}),
        },
        "holdout": {
            "seed": seed,
            "n_holdout": n_holdout,
            "config_names": holdout_names,
        },
        "configs": config_records,
    }
    _write_json(output_dir / "sweep_manifest.json", manifest)
    write_units_sidecar(output_dir / "sweep_manifest.units.json", _MANIFEST_UNITS)

    provenance = {
        "tool": "mosquito_cfd.force_surrogate.sweep.generate_sweep",
        "generated_at": timestamp,
        "git_commit": _git_commit(),
        "base_inputs": {
            "path": base_path.as_posix(),
            "sha256": hash_file(base_path),
        },
    }
    _write_json(output_dir / "sweep_provenance.json", provenance)
    return manifest
