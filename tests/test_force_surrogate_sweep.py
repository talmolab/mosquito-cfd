"""Tests for force_surrogate.sweep.

Cluster-free (roadmap CC-2): every test runs against the committed validated base inputs
(``examples/flapping_wing/inputs.3d.validation``), ``tests/fixtures/micro_sweep.json``, and the
committed ``examples/prelim_sweep/`` corpus — no RunAI, GPU, or plotfiles. The unit tests use the
base inputs + micro-sweep fixture; the artifact tests at the end of this module additionally read
the committed ``examples/prelim_sweep/`` sweep corpus.
"""

import itertools
import json
from pathlib import Path

import pytest

from mosquito_cfd.benchmarks.metadata import hash_file
from mosquito_cfd.force_surrogate import (
    build_kinematic_grid,
    compute_reynolds,
    derive_run_duration,
    generate_sweep,
    read_units_sidecar,
    render_inputs,
    select_holdout,
)
from mosquito_cfd.force_surrogate.constants import (
    AEDES_FREQUENCY_FSTAR,
    AEDES_PITCH_AMP_DEG,
    AEDES_STROKE_AMP_DEG,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_INPUTS = REPO_ROOT / "examples" / "flapping_wing" / "inputs.3d.validation"
MICRO_SWEEP = REPO_ROOT / "tests" / "fixtures" / "micro_sweep.json"
TS = "2020-01-01T00:00:00+00:00"

TARGET_KEYS = {
    "particle_inputs.kinematics_stroke_amp",
    "particle_inputs.kinematics_frequency",
    "particle_inputs.kinematics_pitch_amp",
    "max_step",
    "stop_time",
    "amr.plot_int",
}


def _parse_inputs(text: str) -> dict[str, str]:
    """Parse an IAMReX inputs deck into a key->value map (inline comments stripped)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _is_corner(config: dict, configs: list[dict]) -> bool:
    """A config is a corner if every parameter is at an extreme level of the grid."""
    for key in ("stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"):
        values = sorted({c[key] for c in configs})
        if config[key] not in {values[0], values[-1]}:
            return False
    return True


def _render_default(base: str, **overrides) -> str:
    """Render with sensible defaults, overriding selected kwargs."""
    kwargs = dict(
        stroke_amp_deg=35.0,
        frequency_fstar=0.85,
        pitch_amp_deg=30.0,
        max_step=4706,
        stop_time=2.3529411764705883,
        plot_int=-1,
    )
    kwargs.update(overrides)
    return render_inputs(base, **kwargs)


# --- 1.1 / 1.1b / 1.2: grid ------------------------------------------------------------


def test_build_kinematic_grid_default():
    """27 configs over the Aedes levels, canonical product order, exact schema keys."""
    grid = build_kinematic_grid()
    assert len(grid) == 27
    assert {c["stroke_amp_deg"] for c in grid} == {35.0, 45.0, 55.0}
    assert {c["frequency_fstar"] for c in grid} == {0.85, 1.0, 1.15}
    assert {c["pitch_amp_deg"] for c in grid} == {30.0, 45.0, 60.0}
    combos = {
        (c["stroke_amp_deg"], c["frequency_fstar"], c["pitch_amp_deg"]) for c in grid
    }
    assert len(combos) == 27
    assert set(grid[0]) == {"stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"}

    expected = list(
        itertools.product(
            AEDES_STROKE_AMP_DEG, AEDES_FREQUENCY_FSTAR, AEDES_PITCH_AMP_DEG
        )
    )
    for i in (0, 13, 26):
        assert (
            grid[i]["stroke_amp_deg"],
            grid[i]["frequency_fstar"],
            grid[i]["pitch_amp_deg"],
        ) == expected[i]


def test_build_kinematic_grid_custom_levels():
    """A pure function of its level inputs: 2x2x2 -> 8 configs, each combination once."""
    grid = build_kinematic_grid([10.0, 20.0], [1.0, 2.0], [5.0, 6.0])
    assert len(grid) == 8
    combos = {
        (c["stroke_amp_deg"], c["frequency_fstar"], c["pitch_amp_deg"]) for c in grid
    }
    assert len(combos) == 8


def test_manifest_config_order_canonical(tmp_path):
    """configs[].index == position; manifest order == grid order == filename sort."""
    manifest = generate_sweep(BASE_INPUTS, tmp_path, timestamp=TS)
    configs = manifest["configs"]
    assert [c["index"] for c in configs] == list(range(27))
    grid = build_kinematic_grid()
    assert [
        (c["stroke_amp_deg"], c["frequency_fstar"], c["pitch_amp_deg"]) for c in configs
    ] == [(g["stroke_amp_deg"], g["frequency_fstar"], g["pitch_amp_deg"]) for g in grid]
    names = [c["name"] for c in configs]
    assert names == sorted(names)


# --- 1.3 / 1.4: caller-supplied configs ------------------------------------------------


def test_generator_consumes_micro_sweep_fixture(tmp_path):
    """The 2-config micro-sweep fixture drives the generator cluster-free (CC-2)."""
    configs = json.loads(MICRO_SWEEP.read_text(encoding="utf-8"))
    manifest = generate_sweep(
        BASE_INPUTS, tmp_path, configs=configs, n_holdout=0, timestamp=TS
    )
    files = sorted((tmp_path / "inputs").glob("inputs.3d.*"))
    assert len(files) == 2
    assert manifest["holdout"]["n_holdout"] == 0
    assert manifest["holdout"]["config_names"] == []
    assert all(c["split"] == "train" for c in manifest["configs"])


def test_generate_sweep_rejects_malformed_config(tmp_path):
    """Empty / missing-key / unknown-key configs raise; nothing is written (atomicity)."""
    with pytest.raises(ValueError):
        generate_sweep(BASE_INPUTS, tmp_path / "empty", configs=[], timestamp=TS)

    with pytest.raises(ValueError) as exc:
        generate_sweep(
            BASE_INPUTS,
            tmp_path / "missing",
            configs=[{"stroke_amp_deg": 35.0, "frequency_fstar": 1.0}],
            timestamp=TS,
        )
    assert "pitch_amp_deg" in str(exc.value)

    with pytest.raises(ValueError):
        generate_sweep(
            BASE_INPUTS,
            tmp_path / "unknown",
            configs=[
                {
                    "stroke_amp_deg": 35.0,
                    "frequency_fstar": 1.0,
                    "pitch_amp_deg": 45.0,
                    "bogus": 1,
                }
            ],
            timestamp=TS,
        )

    with pytest.raises(ValueError):
        generate_sweep(
            BASE_INPUTS, tmp_path / "notdict", configs=["nope"], timestamp=TS
        )

    atomic = tmp_path / "atomic"
    with pytest.raises(ValueError):
        generate_sweep(
            BASE_INPUTS, atomic, configs=[{"stroke_amp_deg": 35.0}], timestamp=TS
        )
    assert not atomic.exists()


# --- 1.5 / 1.6 / 1.7: Reynolds ---------------------------------------------------------


def test_compute_reynolds_validated_point():
    """Re ~ 100 at the validated phi=70, f*=1.0, nu*=0.115 point."""
    assert compute_reynolds(70.0, 1.0, 0.115) == pytest.approx(100.0, rel=1e-2)


def test_compute_reynolds_uses_midspan_arm():
    """r_mid=1.5 (default) vs r_mid=3.0 differ by exactly R_TIP/r_mid = 2."""
    midspan = compute_reynolds(45.0, 1.0, 0.115)
    tip = compute_reynolds(45.0, 1.0, 0.115, r_mid=3.0)
    assert tip == pytest.approx(2.0 * midspan, rel=1e-12)


def test_compute_reynolds_rejects_nonpositive_viscosity():
    """nu_star <= 0 raises (parity with PR1 compute_force_coefficients guard)."""
    with pytest.raises(ValueError):
        compute_reynolds(45.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        compute_reynolds(45.0, 1.0, -0.1)


# --- 1.8: run duration -----------------------------------------------------------------


def test_derive_run_duration():
    """stop_time = n/f*, max_step = round(stop_time/dt)."""
    max_step, stop_time = derive_run_duration(0.85, n_wingbeats=2, dt=5e-4)
    assert stop_time == pytest.approx(2.3529411764705883, rel=1e-6)
    assert max_step == 4706
    max_step1, stop_time1 = derive_run_duration(1.0, n_wingbeats=2, dt=5e-4)
    assert (max_step1, stop_time1) == (4000, 2.0)
    with pytest.raises(ValueError):
        derive_run_duration(0.0)


# --- 1.9 / 1.10: holdout ---------------------------------------------------------------


def test_select_holdout_seeded_noncorner():
    """6 non-corner holdout indices, deterministic; 19 eligible, 8 corners."""
    grid = build_kinematic_grid()
    eligible = sorted(i for i, c in enumerate(grid) if not _is_corner(c, grid))
    assert len(eligible) == 19  # 27 - 8 corners

    holdout = select_holdout(grid)
    assert len(set(holdout)) == 6
    assert set(holdout).issubset(set(eligible))
    assert all(not _is_corner(grid[i], grid) for i in holdout)
    assert select_holdout(grid) == holdout  # deterministic by seed
    # regression lock for HOLDOUT_SEED (run-once-and-lock, layered on the properties above)
    assert sorted(holdout) == [1, 11, 14, 17, 19, 25]


def test_select_holdout_rejects_too_many():
    """n_holdout greater than the eligible set raises (no replacement / no loop)."""
    micro = json.loads(MICRO_SWEEP.read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        select_holdout(micro, n_holdout=6)
    with pytest.raises(ValueError):
        select_holdout(build_kinematic_grid(), n_holdout=20)


def test_select_holdout_empty_configs():
    """Empty configs: n_holdout=0 -> []; n_holdout>0 -> clean ValueError (not a min() error)."""
    assert select_holdout([], n_holdout=0) == []
    with pytest.raises(ValueError):
        select_holdout([], n_holdout=1)


def test_generate_sweep_rejects_name_collision(tmp_path):
    """Distinct configs that round to the same file name raise before any file is written."""
    colliding = [
        {"stroke_amp_deg": 35.2, "frequency_fstar": 1.0, "pitch_amp_deg": 45.0},
        {"stroke_amp_deg": 35.8, "frequency_fstar": 1.0, "pitch_amp_deg": 45.0},
    ]
    out = tmp_path / "collide"
    with pytest.raises(ValueError) as exc:
        generate_sweep(BASE_INPUTS, out, configs=colliding, n_holdout=0, timestamp=TS)
    assert "s35_f100_p45" in str(exc.value)
    assert not out.exists()


# --- 1.11 / 1.12 / 1.13 / 1.14 / 1.15 / 1.15b: render_inputs ---------------------------


def test_render_inputs_minimal_diff():
    """Only the swept/derived keys change; comments, blanks, and unrelated keys persist."""
    base = BASE_INPUTS.read_text(encoding="utf-8")
    out = _render_default(base)
    base_map, out_map = _parse_inputs(base), _parse_inputs(out)
    differing = {
        k for k in set(base_map) | set(out_map) if base_map.get(k) != out_map.get(k)
    }
    assert differing == TARGET_KEYS
    for key in (
        "particle_inputs.geometry_type",
        "particle_inputs.geometry_file",
        "particle_inputs.hinge_x",
        "ns.vel_visc_coef",
        "nodal_proj.proj_tol",
    ):
        assert base_map[key] == out_map[key]
    assert len(base.splitlines()) == len(out.splitlines())
    assert "# Simulation control" in out


def test_render_inputs_no_prefix_collision():
    """kinematics_deviation_amp (prefix sibling) is byte-unchanged: exact-key match."""
    out = _render_default(BASE_INPUTS.read_text(encoding="utf-8"))
    assert "particle_inputs.kinematics_deviation_amp = 0.0" in out


def test_render_inputs_preserves_inline_comment():
    """A trailing inline comment on a rewritten key keeps its spacing + text (D6)."""
    base = (
        "max_step        = 2000  # the step cap\n"
        "stop_time = 1.0\n"
        "amr.plot_int = 100\n"
        "particle_inputs.kinematics_stroke_amp = 70.0\n"
        "particle_inputs.kinematics_frequency = 1.0\n"
        "particle_inputs.kinematics_pitch_amp = 45.0\n"
    )
    out = _render_default(base)
    assert "max_step        = 4706  # the step cap\n" in out


def test_render_inputs_rejects_duplicate_key():
    """A targeted key appearing twice in the base raises rather than silently rewriting both."""
    base = "max_step = 2000\nstop_time = 1.0\namr.plot_int = 100\nmax_step = 3000\n"
    with pytest.raises(ValueError) as exc:
        render_inputs(
            base,
            stroke_amp_deg=35.0,
            frequency_fstar=0.85,
            pitch_amp_deg=30.0,
            max_step=4706,
            stop_time=2.35,
            plot_int=-1,
        )
    assert "duplicate" in str(exc.value) and "max_step" in str(exc.value)


def test_render_inputs_forces_plot_int_minus_one():
    """plot_int is forced to -1 even though the base has 100 (force-only)."""
    out = _render_default(BASE_INPUTS.read_text(encoding="utf-8"))
    assert _parse_inputs(out)["amr.plot_int"] == "-1"


@pytest.mark.parametrize("key", sorted(TARGET_KEYS))
def test_render_inputs_missing_key_raises(key):
    """A targeted key absent from the base raises ValueError naming it."""
    base = BASE_INPUTS.read_text(encoding="utf-8")
    kept = [
        line
        for line in base.splitlines()
        if line.split("#", 1)[0].split("=", 1)[0].strip() != key
    ]
    with pytest.raises(ValueError) as exc:
        _render_default("\n".join(kept) + "\n")
    assert key in str(exc.value)


def test_render_inputs_formatting():
    """Deterministic float formatting (shortest repr) for the rewritten values."""
    out = _render_default(BASE_INPUTS.read_text(encoding="utf-8"))
    out_map = _parse_inputs(out)
    assert out_map["particle_inputs.kinematics_frequency"] == "0.85"
    assert out_map["particle_inputs.kinematics_stroke_amp"] == "35.0"
    assert out_map["stop_time"] == "2.3529411764705883"
    assert out_map["max_step"] == "4706"


def test_generated_files_are_lf_on_disk(tmp_path):
    """The WRITE step (newline="") yields LF on disk regardless of platform."""
    generate_sweep(BASE_INPUTS, tmp_path, timestamp=TS)
    a_file = sorted((tmp_path / "inputs").glob("inputs.3d.*"))[0]
    assert b"\r" not in a_file.read_bytes()
    for sidecar in (
        "sweep_manifest.json",
        "sweep_manifest.units.json",
        "sweep_provenance.json",
    ):
        assert b"\r" not in (tmp_path / sidecar).read_bytes(), sidecar


# --- 1.16 / 1.17 / 1.18: generate_sweep manifest --------------------------------------


def test_generate_sweep_all_configs_and_split(tmp_path):
    """27 files; 6 holdout / 21 train; holdout block consistent with per-config split."""
    manifest = generate_sweep(BASE_INPUTS, tmp_path, timestamp=TS)
    files = sorted((tmp_path / "inputs").glob("inputs.3d.*"))
    assert len(files) == 27
    holdout = [c for c in manifest["configs"] if c["split"] == "holdout"]
    train = [c for c in manifest["configs"] if c["split"] == "train"]
    assert len(holdout) == 6
    assert len(train) == 21
    assert set(manifest["holdout"]["config_names"]) == {c["name"] for c in holdout}


def test_generate_sweep_nu_fixed_and_reynolds_recorded(tmp_path):
    """nu* held at 0.115 in every file; per-config Re recorded with canonical format."""
    manifest = generate_sweep(BASE_INPUTS, tmp_path, timestamp=TS)
    for f in (tmp_path / "inputs").glob("inputs.3d.*"):
        assert (
            _parse_inputs(f.read_text(encoding="utf-8"))["ns.vel_visc_coef"] == "0.115"
        )
    assert manifest["reynolds_policy"] == "nu_star_fixed"
    assert manifest["nu_star"] == 0.115
    for c in manifest["configs"]:
        assert c["reynolds"] == compute_reynolds(
            c["stroke_amp_deg"], c["frequency_fstar"], 0.115
        )
    text = (tmp_path / "sweep_manifest.json").read_text(encoding="utf-8")
    assert '"reynolds": 42.5537291206389' in text  # s35_f085 config
    assert '"reynolds": 90.47137367665243' in text  # s55_f115 config (distinct value)
    assert '"nu_star": 0.115' in text


def test_generate_sweep_duration_per_config(tmp_path):
    """Every config covers >= n_wingbeats whole beats; dt unchanged from the base."""
    manifest = generate_sweep(BASE_INPUTS, tmp_path, timestamp=TS)
    for c in manifest["configs"]:
        assert c["stop_time"] * c["frequency_fstar"] >= 2 - 1e-9
        assert (c["max_step"], c["stop_time"]) == derive_run_duration(
            c["frequency_fstar"]
        )
    for f in (tmp_path / "inputs").glob("inputs.3d.*"):
        assert _parse_inputs(f.read_text(encoding="utf-8"))["ns.fixed_dt"] == "0.0005"


# --- 1.19 / 1.20: provenance + units ---------------------------------------------------


def test_provenance_sidecar_no_digest(tmp_path):
    """Provenance records git + base hash + caller timestamp; no digest; not in manifest."""
    generate_sweep(BASE_INPUTS, tmp_path, timestamp=TS)
    prov_text = (tmp_path / "sweep_provenance.json").read_text(encoding="utf-8")
    prov = json.loads(prov_text)
    assert (
        "git_commit" in prov
    )  # may be a SHA, None, or {"error": ...} on odd checkouts
    assert prov["base_inputs"]["sha256"] == hash_file(BASE_INPUTS)
    assert prov["generated_at"] == TS
    assert "sha256:" not in prov_text  # no content-addressable image digest
    assert "docker_image" not in prov_text
    manifest = (tmp_path / "sweep_manifest.json").read_text(encoding="utf-8")
    assert "git_commit" not in manifest  # kept out so the manifest is byte-reproducible


def test_units_sidecar_roundtrips_via_pr1_helper(tmp_path):
    """The emitted units sidecar parses via the PR1 helper and maps the right units."""
    generate_sweep(BASE_INPUTS, tmp_path, timestamp=TS)
    units = read_units_sidecar(tmp_path / "sweep_manifest.units.json")
    assert units["stroke_amp_deg"] == "deg"
    assert units["pitch_amp_deg"] == "deg"
    assert units["frequency_fstar"] == "dimensionless (f*)"
    for key in ("nu_star", "reynolds", "stop_time"):
        assert units[key] == "dimensionless"


# --- 1.21: byte-identical regeneration -------------------------------------------------


def test_regeneration_byte_identical(tmp_path):
    """Same seed + timestamp -> byte-identical inputs and manifest + units sidecar."""
    run_a, run_b = tmp_path / "a", tmp_path / "b"
    generate_sweep(BASE_INPUTS, run_a, timestamp=TS)
    generate_sweep(BASE_INPUTS, run_b, timestamp=TS)
    for fa in sorted((run_a / "inputs").glob("inputs.3d.*")):
        assert fa.read_bytes() == (run_b / "inputs" / fa.name).read_bytes()
    for name in ("sweep_manifest.json", "sweep_manifest.units.json"):
        assert (run_a / name).read_bytes() == (run_b / name).read_bytes()


# --- 4. Artifact tests (depend on the committed examples/prelim_sweep/ corpus) ---------

PRELIM_SWEEP = REPO_ROOT / "examples" / "prelim_sweep"


def test_committed_sweep_matches_regeneration(tmp_path):
    """The committed corpus is byte-identical to a fresh regen with its recorded seed/ts."""
    manifest = json.loads(
        (PRELIM_SWEEP / "sweep_manifest.json").read_text(encoding="utf-8")
    )
    provenance = json.loads(
        (PRELIM_SWEEP / "sweep_provenance.json").read_text(encoding="utf-8")
    )
    generate_sweep(
        BASE_INPUTS,
        tmp_path,
        seed=manifest["holdout"]["seed"],
        n_holdout=manifest["holdout"]["n_holdout"],
        timestamp=provenance["generated_at"],
    )
    committed = sorted((PRELIM_SWEEP / "inputs").glob("inputs.3d.*"))
    assert len(committed) == 27
    for deck in committed:
        assert deck.read_bytes() == (tmp_path / "inputs" / deck.name).read_bytes()
    for name in ("sweep_manifest.json", "sweep_manifest.units.json"):
        assert (PRELIM_SWEEP / name).read_bytes() == (tmp_path / name).read_bytes()


def test_committed_manifest_shape():
    """The committed manifest has 27 configs, 6 holdout / 21 train, nu* fixed; units valid."""
    manifest = json.loads(
        (PRELIM_SWEEP / "sweep_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["configs"]) == 27
    assert manifest["reynolds_policy"] == "nu_star_fixed"
    splits = [c["split"] for c in manifest["configs"]]
    assert splits.count("holdout") == 6
    assert splits.count("train") == 21
    units = read_units_sidecar(PRELIM_SWEEP / "sweep_manifest.units.json")
    assert units["reynolds"] == "dimensionless"


def test_driver_smoke(tmp_path):
    """The driver's main() runs end-to-end into tmp_path: exit 0, 27 decks + sidecars."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "prelim_sweep_driver", PRELIM_SWEEP / "generate_sweep.py"
    )
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)

    rc = driver.main(["--output", str(tmp_path), "--timestamp", TS])
    assert rc == 0
    assert len(list((tmp_path / "inputs").glob("inputs.3d.*"))) == 27
    for name in (
        "sweep_manifest.json",
        "sweep_manifest.units.json",
        "sweep_provenance.json",
    ):
        assert (tmp_path / name).exists()
