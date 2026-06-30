"""CC-3 guard: the flapping-wing figure script sources F_ref from the shared helper.

A manual run cannot detect a reintroduced inline formula (same formula -> same printed
value), so this asserts the script actually *calls* compute_force_reference.
"""

import importlib.util
from pathlib import Path

import mosquito_cfd.force_surrogate as fsurr

REPO = Path(__file__).resolve().parents[1]
GAF_PATH = REPO / "examples" / "flapping_wing" / "generate_all_figures.py"
FORCES_CSV = REPO / "examples" / "flapping_wing" / "forces.csv"


def _load_generate_all_figures():
    spec = importlib.util.spec_from_file_location("gaf_under_test", GAF_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_all_figures_uses_shared_reference(tmp_path, monkeypatch):
    gaf = _load_generate_all_figures()
    captured = {"n": 0}
    real = fsurr.compute_force_reference

    def spy(*args, **kwargs):
        ref = real(*args, **kwargs)
        captured["ref"] = ref
        captured["n"] += 1
        return ref

    monkeypatch.setattr(gaf, "compute_force_reference", spy)
    gaf.plot_f1_forces(tmp_path, FORCES_CSV)

    assert captured["n"] >= 1, "plot_f1_forces did not call compute_force_reference"
    expected = real(
        gaf.F_STAR, gaf.PHI_AMP_DEG, gaf.R_GYRATION, gaf.SPAN, gaf.CHORD, rho=1.0
    )
    assert captured["ref"].f_ref == expected.f_ref
