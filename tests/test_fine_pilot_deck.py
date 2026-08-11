"""Fine-grid training-data pilot: deck invariance, reproducibility, and isolation guards.

OpenSpec change ``add-fine-grid-training-pilot``. All checks here are cluster-free (no RunAI,
GPU, or plotfiles) -- they gate the pilot's Phase 0/1 tooling (fine base deck, deck generation)
plus Phase 3's report/metadata artifacts once the (separate, operator-run) cluster phase produces
them. The Phase 3 tests are ``skipif``-guarded per config so a partially-complete pilot reports
N passes + (3-N) skips, not one all-or-nothing result.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import re
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


def test_pilot_configs_match_generate_pilot_script():
    """This test file's config list is not a silently-drifting duplicate of the real script's.

    ``generate_pilot.PILOT_CONFIGS`` is the single source of truth for what actually gets
    submitted to the cluster; the byte-reproducibility test above exercises ``generate_sweep()``
    directly against its own ``_PILOT_CONFIGS`` copy (so it doesn't depend on successfully
    importing the script), which must be kept in lockstep with the real one -- otherwise a future
    edit to either list would silently stop matching the other with no test failure to catch it.
    """
    pilot = _load_pilot_script()
    assert pilot.PILOT_CONFIGS == _PILOT_CONFIGS


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


def test_validate_output_dir_rejects_the_frozen_coarse_corpus():
    """The runtime guard rejects an ``--output`` that resolves to the frozen coarse corpus.

    A static isolation guard on the *constants* (above) is not a runtime guard on what an
    operator actually types on the command line. A typo'd ``--output examples/prelim_sweep``
    (very plausible given the sibling ``examples/prelim_sweep/generate_sweep.py`` driver takes
    the identical flag) must be rejected before ``generate_sweep()`` ever runs, since it prunes
    stale decks in its target directory -- against the real, committed 27-config corpus, that
    would delete real CFD output.
    """
    pilot = _load_pilot_script()

    with pytest.raises(ValueError, match="frozen coarse corpus"):
        pilot._validate_output_dir(_COARSE_CORPUS_DIR)

    # The pilot's own real output directory must NOT be rejected.
    pilot._validate_output_dir(pilot.OUTPUT_DIR)


def test_generate_pilot_main_rejects_frozen_corpus_output_via_cli(
    tmp_path, monkeypatch
):
    """``main()`` refuses an ``--output`` that resolves to the configured frozen-corpus path.

    Exercises the guard through the actual CLI entry point (not just the pure helper below), so
    the real failure mode -- an operator typo on the command line -- is covered end-to-end.
    Deliberately does NOT point ``main()`` at the real ``examples/prelim_sweep`` corpus: per the
    same reasoning as the static isolation-guard test above, a *buggy* guard would then actually
    run ``generate_sweep()`` against the real corpus during a test run. Instead, monkeypatches
    the guarded-path constant to a ``tmp_path`` decoy, so the wiring (``main()`` calls the guard;
    the guard raises; ``main()`` turns that into ``parser.error()`` / ``SystemExit``) is verified
    without any real path ever being at risk.
    """
    pilot = _load_pilot_script()
    decoy_corpus = tmp_path / "decoy_prelim_sweep"
    monkeypatch.setattr(pilot, "_FROZEN_CORPUS_DIR", decoy_corpus)

    with pytest.raises(SystemExit):
        pilot.main(["--output", str(decoy_corpus)])


# ---------------------------------------------------------------------------
# Phase 3 -- pilot report + per-config run metadata (skipif absent; Session B, operator-run)
# ---------------------------------------------------------------------------

_REPORT = Path("docs/force_surrogate/fine-grid-pilot-report.md")
_STABILITY_TOKENS = ("stable_at_5e-4", "stable_at_2.5e-4_fallback", "unstable")
_NUMBER_PATTERN = re.compile(r"\d+\.\d+")


@pytest.mark.skipif(not _REPORT.exists(), reason="pilot report not present (Session B)")
def test_pilot_report_covers_all_attempted_configs():
    """Each attempted config's OWN line carries a stability token AND a numeric timing figure.

    Strengthened after ``/review-pr`` on PR #58 found the original check was a whole-document
    substring search performed inside a per-config loop: it never confirmed that a given
    config's *own* row/section carried a stability outcome (a report missing one config's
    outcome, while mentioning that config's name elsewhere, would still have passed), and it
    never asserted a numeric wall-time/``s_per_step`` figure appeared at all, despite
    ``spec.md``'s scenario and ``tasks.md`` explicitly requiring both.
    """
    text = _REPORT.read_text(encoding="utf-8")
    lines = text.splitlines()
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
        config_lines = [line for line in lines if name in line]
        assert config_lines, f"pilot report does not mention attempted config {name}"
        assert any(
            any(token in line for token in _STABILITY_TOKENS)
            and _NUMBER_PATTERN.search(line)
            for line in config_lines
        ), (
            f"no single line mentioning config {name} carries BOTH a recognized stability "
            f"token ({_STABILITY_TOKENS}) AND a numeric wall-time/s_per_step figure"
        )

    # A full 27-config cost projection (spec.md's other required element) must appear too.
    assert re.search(r"27[\s-]*config", text, re.IGNORECASE), (
        "pilot report is missing a full 27-config cost-projection reference"
    )
    assert re.search(r"\d+(\.\d+)?\s*(hours?|h\b|days?)", text, re.IGNORECASE), (
        "pilot report is missing a numeric wall-time figure for the cost projection"
    )


def test_pilot_report_flags_the_hinge_geometry_defect_and_unconfirmed_stability():
    """The report's geometry note names the hinge defect and does NOT claim stability transfers.

    fix-force-surrogate-sweep-hinge: an earlier draft of this note claimed the dt=5e-4 stability
    result was unaffected by hinge placement -- wrong, since marker velocity (and therefore CFL
    margin) scales with the hinge-to-tip arm, which the bug roughly halved. This pins the note to
    NOT make that retracted claim, and to explicitly call out that stability needs re-confirming.
    """
    text = _REPORT.read_text(encoding="utf-8")
    assert "midspan pivot" in text
    assert "not confirmed to transfer" in text
    assert "re-confirm" in text.lower()


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


def _load_metadata(path: Path) -> dict:
    """Parse a ``run_metadata_*.json`` file, raising a clear error on malformed content.

    A bare ``json.loads`` failure surfaces as an opaque ``JSONDecodeError`` pointing at a
    line/column with no file context; wrapping it here gives a clear, file-identified message.
    """
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def test_load_metadata_raises_clear_error_on_malformed_json(tmp_path):
    """A malformed metadata file surfaces a clear, file-identified error, not a bare traceback."""
    bad = tmp_path / "run_metadata_bad.json"
    bad.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        _load_metadata(bad)


def _read_last_csv_time(csv_path: Path) -> float:
    """Return the ``time`` column value of a force CSV's last data row."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header, data_rows = rows[0], rows[1:]
    time_idx = header.index("time")
    return float(data_rows[-1][time_idx])


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

    metadata = _load_metadata(metadata_path)
    for field in _REQUIRED_METADATA_FIELDS:
        assert _get_dotted(metadata, field) is not None, (
            f"run_metadata_{config_name}.json missing required field {field!r}"
        )


@pytest.mark.parametrize("config_name", _PILOT_CONFIG_NAMES)
def test_pilot_run_metadata_final_time_matches_last_csv_row(config_name):
    """``timing.final_time`` must equal the actual last recorded row of the force CSV.

    ``IB_Particle_1.csv`` always has exactly ``max_step`` rows (``iStep`` 0..``max_step - 1``) --
    one ``dt`` short of the deck's target ``stop_time`` (a pre-existing IAMReX writer convention,
    not a divergence/truncation bug). A hand-written ``run_metadata`` that instead records
    ``stop_time`` is factually wrong against its own committed CSV -- exactly the gap
    ``/review-pr`` found in all 3 of PR #58's original metadata files.
    """
    metadata_path = Path(
        f"examples/prelim_sweep_fine_pilot/run_metadata_{config_name}.json"
    )
    csv_path = Path(f"examples/prelim_sweep_fine_pilot/forces_{config_name}.csv")
    if not (metadata_path.exists() and csv_path.exists()):
        pytest.skip(
            f"run_metadata/forces CSV for {config_name} not present (Session B)"
        )

    metadata = _load_metadata(metadata_path)
    last_csv_time = _read_last_csv_time(csv_path)
    assert metadata["timing"]["final_time"] == pytest.approx(last_csv_time, abs=1e-9), (
        f"run_metadata_{config_name}.json timing.final_time="
        f"{metadata['timing']['final_time']!r} does not match forces_{config_name}.csv's "
        f"last recorded row (time={last_csv_time!r})"
    )


@pytest.mark.parametrize("config_name", _PILOT_CONFIG_NAMES)
def test_pilot_run_metadata_dt_reduced_correlates_with_fixed_dt(config_name):
    """``dt_reduced`` must correlate with ``fixed_dt``: ``True`` -> the 2.5e-4 T3c fallback,
    ``False`` -> the standard 5e-4. The schema test only checks each field's presence, not that
    the two agree -- a metadata file could otherwise claim ``dt_reduced=True`` while ``fixed_dt``
    still shows the standard value (or vice versa) with nothing to catch it.
    """
    metadata_path = Path(
        f"examples/prelim_sweep_fine_pilot/run_metadata_{config_name}.json"
    )
    if not metadata_path.exists():
        pytest.skip(f"run_metadata for {config_name} not present (Session B)")

    metadata = _load_metadata(metadata_path)
    fixed_dt = metadata["fixed_dt"]
    if metadata["dt_reduced"]:
        assert fixed_dt == pytest.approx(2.5e-4), (
            f"run_metadata_{config_name}.json has dt_reduced=True but fixed_dt={fixed_dt!r} "
            "(expected the T3c fallback 2.5e-4)"
        )
    else:
        assert fixed_dt == pytest.approx(5e-4), (
            f"run_metadata_{config_name}.json has dt_reduced=False but fixed_dt={fixed_dt!r} "
            "(expected the standard 5e-4)"
        )


@pytest.mark.parametrize("config_name", _PILOT_CONFIG_NAMES)
def test_pilot_run_metadata_git_commit_is_full_sha(config_name):
    """``git.commit`` must be a full 40-char SHA, not a truncated/abbreviated one.

    ``/review-pr`` on PR #58 found 2 of the 3 original metadata files recorded a truncated
    7-char commit hash (inconsistent with the third, which had a full SHA) -- a give-away that
    they were hand-typed rather than machine-captured. No function in this codebase's
    ``get_git_info``/metadata-capture path ever produces a short hash on its own, so this pins
    the field to the format it should always have.
    """
    metadata_path = Path(
        f"examples/prelim_sweep_fine_pilot/run_metadata_{config_name}.json"
    )
    if not metadata_path.exists():
        pytest.skip(f"run_metadata for {config_name} not present (Session B)")

    metadata = _load_metadata(metadata_path)
    commit = metadata["git"]["commit"]
    assert len(commit) == 40, (
        f"run_metadata_{config_name}.json git.commit={commit!r} is not a full 40-char SHA "
        f"(len={len(commit)})"
    )
    assert all(c in "0123456789abcdef" for c in commit), (
        f"run_metadata_{config_name}.json git.commit={commit!r} is not lowercase hex"
    )
