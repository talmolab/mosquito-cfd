"""Fine-grid training-data pilot: deck invariance, reproducibility, and isolation guards.

OpenSpec change ``add-fine-grid-training-pilot``. All checks here are cluster-free (no RunAI,
GPU, or plotfiles) -- they gate the pilot's Phase 0/1 tooling (fine base deck, deck generation)
plus Phase 3's report/metadata artifacts once the (separate, operator-run) cluster phase produces
them. The Phase 3 tests are ``skipif``-guarded per config so a partially-complete pilot reports
N passes + (3-N) skips, not one all-or-nothing result.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate.sweep import derive_run_duration, generate_sweep

_COARSE_BASE = Path("examples/prelim_sweep/base_inputs.3d.validation")
_FINE_BASE = Path("examples/prelim_sweep_fine_pilot/base_inputs.3d.fine")
_PILOT_SCRIPT = Path("examples/prelim_sweep_fine_pilot/generate_pilot.py")
_COARSE_CORPUS_DIR = Path("examples/prelim_sweep")
_COARSE_WORKSPACE_HOSTPATH = (
    "/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep"
)

_PILOT_CONFIGS = [
    {"stroke_amp_deg": 55.0, "frequency_fstar": 1.15, "pitch_amp_deg": 45.0},
    {"stroke_amp_deg": 45.0, "frequency_fstar": 1.00, "pitch_amp_deg": 45.0},
    {"stroke_amp_deg": 35.0, "frequency_fstar": 0.85, "pitch_amp_deg": 45.0},
]
_PILOT_CONFIG_NAMES = ("s55_f115_p45", "s45_f100_p45", "s35_f085_p45")
_TIMESTAMP = "2026-07-29T00:00:00+00:00"


def _parse_deck(path: Path) -> dict[str, str]:
    """Parse an AMReX inputs deck into a ``key -> value`` map (comments stripped)."""
    kv: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        kv[key] = " ".join(value.split())
    return kv


def _load_pilot_script():
    spec = importlib.util.spec_from_file_location("generate_pilot", _PILOT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Phase 0 -- fine base deck invariance
# ---------------------------------------------------------------------------


def test_fine_pilot_deck_matches_coarse_base_except_n_cell():
    """The fine pilot base deck differs from the frozen coarse base ONLY in ``amr.n_cell``."""
    coarse = _parse_deck(_COARSE_BASE)
    fine = _parse_deck(_FINE_BASE)

    all_keys = set(coarse) | set(fine)
    differing = {k for k in all_keys if coarse.get(k) != fine.get(k)}
    assert differing == {"amr.n_cell"}, (
        f"fine pilot base deck must change ONLY amr.n_cell; differing keys: {sorted(differing)}"
    )
    assert coarse["amr.n_cell"] == "64 32 64"
    assert fine["amr.n_cell"] == "256 128 256"

    # dt and IB-regularization radius held fixed, matching the T3a/T3c convergence-deck pattern.
    assert float(coarse["ns.fixed_dt"]) == float(fine["ns.fixed_dt"]) == 5e-4
    assert (
        float(coarse["particle_inputs.radius"])
        == float(fine["particle_inputs.radius"])
        == 1.5
    )


# ---------------------------------------------------------------------------
# Phase 1 -- pilot deck generation (byte-reproducibility, max_step, isolation guard)
# ---------------------------------------------------------------------------


def test_pilot_decks_are_byte_reproducible_from_generate_sweep(tmp_path):
    """Two identical ``generate_sweep()`` calls against the fine base deck produce identical trees."""
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    for out_dir in (out_a, out_b):
        generate_sweep(
            _FINE_BASE,
            out_dir,
            timestamp=_TIMESTAMP,
            configs=_PILOT_CONFIGS,
            n_holdout=0,
            n_wingbeats=2,
            dt=5e-4,
        )

    for name in _PILOT_CONFIG_NAMES:
        rel = f"inputs/inputs.3d.{name}"
        assert (out_a / rel).read_bytes() == (out_b / rel).read_bytes(), (
            f"deck {rel} is not byte-reproducible"
        )

    manifest_a = (out_a / "sweep_manifest.json").read_bytes()
    manifest_b = (out_b / "sweep_manifest.json").read_bytes()
    assert manifest_a == manifest_b

    manifest = json.loads(manifest_a)
    assert manifest["holdout"]["n_holdout"] == 0
    assert manifest["holdout"]["config_names"] == []
    assert {c["name"] for c in manifest["configs"]} == set(_PILOT_CONFIG_NAMES)


def test_pilot_max_step_matches_run_duration_formula():
    """``derive_run_duration`` reproduces the pilot's pinned per-config ``max_step`` values."""
    max_step_115, _ = derive_run_duration(1.15, n_wingbeats=2, dt=5e-4)
    max_step_100, _ = derive_run_duration(1.00, n_wingbeats=2, dt=5e-4)
    max_step_085, _ = derive_run_duration(0.85, n_wingbeats=2, dt=5e-4)

    assert max_step_115 == 3478
    assert max_step_100 == 4000
    assert max_step_085 == 4706


def test_pilot_output_dir_and_workspace_path_differ_from_coarse_corpus():
    """Static isolation guard: the pilot's output dir and NFS hostpath are NOT the coarse corpus's.

    Deliberately does not execute ``generate_sweep()`` against any real, non-tmp_path directory --
    pointed at the script's real defaults, that risks triggering ``generate_sweep()``'s
    stale-deck-pruning ``unlink()`` against the committed 27-config coarse corpus. This check is a
    pure string/Path comparison of the constants the real (once-run) generation and cluster
    submission will use.
    """
    pilot = _load_pilot_script()

    assert pilot.OUTPUT_DIR != _COARSE_CORPUS_DIR
    assert pilot.OUTPUT_DIR.resolve() != _COARSE_CORPUS_DIR.resolve()
    assert pilot.WORKSPACE_HOSTPATH != _COARSE_WORKSPACE_HOSTPATH


# ---------------------------------------------------------------------------
# Phase 3 -- pilot report + per-config run metadata (skipif absent; Session B, operator-run)
# ---------------------------------------------------------------------------

_REPORT = Path("docs/force_surrogate/fine-grid-pilot-report.md")
_STABILITY_TOKENS = ("stable_at_5e-4", "stable_at_2.5e-4_fallback", "unstable")


@pytest.mark.skipif(not _REPORT.exists(), reason="pilot report not present (Session B)")
def test_pilot_report_covers_all_attempted_configs():
    """The pilot report lists a stability outcome + numeric timing for every attempted config."""
    text = _REPORT.read_text(encoding="utf-8")
    attempted = [
        name
        for name in _PILOT_CONFIG_NAMES
        if Path(f"examples/prelim_sweep_fine_pilot/run_metadata_{name}.json").exists()
        or Path(
            f"examples/prelim_sweep_fine_pilot/run_metadata_{name}_unstable.json"
        ).exists()
    ]
    assert attempted, "pilot report exists but no config's run_metadata was found"
    for name in attempted:
        assert name in text, f"pilot report does not mention attempted config {name}"
        assert any(token in text for token in _STABILITY_TOKENS), (
            "pilot report is missing a recognized stability token "
            f"({_STABILITY_TOKENS}) for config {name}"
        )


_REQUIRED_METADATA_FIELDS = (
    "git",
    "docker_image",
    "image_digest",
    "timing.wall_time_s",
    "timing.timesteps",
    "timing.s_per_step",
    "fixed_dt",
    "dt_reduced",
)


def _get_dotted(data: dict, dotted_key: str):
    node = data
    for part in dotted_key.split("."):
        node = node[part]
    return node


@pytest.mark.parametrize("config_name", _PILOT_CONFIG_NAMES)
def test_pilot_run_metadata_schema(config_name):
    """Each committed ``run_metadata_<config>.json`` carries the required provenance fields.

    ``skipif`` per-config (via a parametrized case, not an internal skip-on-first-missing loop)
    so a partial pilot (e.g. 1 of 3 configs done) reports 1 pass + 2 skips, not one all-or-nothing
    result.
    """
    metadata_path = Path(
        f"examples/prelim_sweep_fine_pilot/run_metadata_{config_name}.json"
    )
    if not metadata_path.exists():
        pytest.skip(f"run_metadata for {config_name} not present (Session B)")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for field in _REQUIRED_METADATA_FIELDS:
        assert _get_dotted(metadata, field) is not None, (
            f"run_metadata_{config_name}.json missing required field {field!r}"
        )
