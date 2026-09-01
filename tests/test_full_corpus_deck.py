"""Full 27-config fine-grid corpus: default grid/holdout, reproducibility, isolation guards.

OpenSpec change ``add-fine-grid-corpus-full``. All checks here are cluster-free (no RunAI, GPU,
or plotfiles) -- they gate the scaffolding needed before the (separate, later, operator-confirmed)
live cluster run. Unlike ``tests/test_fine_pilot_deck.py`` (3 configs, forced ``n_holdout=0``),
this corpus uses ``generate_sweep()``'s defaults: the full 27-point Aedes grid and ``n_holdout=6``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate import build_kinematic_grid, generate_sweep

_FINE_BASE = Path("examples/prelim_sweep_fine_pilot/base_inputs.3d.fine")
_FULL_CORPUS_SCRIPT = Path("examples/prelim_sweep_fine/generate_full_corpus.py")
_COARSE_CORPUS_DIR = Path("examples/prelim_sweep")
_PILOT_DIR = Path("examples/prelim_sweep_fine_pilot")
_COARSE_WORKSPACE_HOSTPATH = (
    "/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep"
)
_PILOT_WORKSPACE_HOSTPATH = (
    "/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine_pilot"
)
_TIMESTAMP = "2026-08-03T00:00:00+00:00"


def _load_full_corpus_script():
    spec = importlib.util.spec_from_file_location(
        "generate_full_corpus", _FULL_CORPUS_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Config count and grid defaults
# ---------------------------------------------------------------------------


def test_full_corpus_uses_default_27_config_grid(tmp_path):
    """No ``configs=``/``n_holdout=`` override: the default 27-point grid and ``n_holdout=6``."""
    manifest = generate_sweep(_FINE_BASE, tmp_path, timestamp=_TIMESTAMP)

    assert len(manifest["configs"]) == 27

    grid = build_kinematic_grid()
    grid_points = {
        (c["stroke_amp_deg"], c["frequency_fstar"], c["pitch_amp_deg"]) for c in grid
    }
    manifest_points = {
        (c["stroke_amp_deg"], c["frequency_fstar"], c["pitch_amp_deg"])
        for c in manifest["configs"]
    }
    assert manifest_points == grid_points

    assert manifest["holdout"]["n_holdout"] == 6
    assert len(manifest["holdout"]["config_names"]) == 6


# ---------------------------------------------------------------------------
# Byte-reproducibility
# ---------------------------------------------------------------------------


def test_full_corpus_decks_are_byte_reproducible_from_generate_sweep(tmp_path):
    """Two identical ``generate_sweep()`` calls against the fine base deck produce identical trees."""
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    for out_dir in (out_a, out_b):
        generate_sweep(_FINE_BASE, out_dir, timestamp=_TIMESTAMP)

    manifest_a = (out_a / "sweep_manifest.json").read_bytes()
    manifest_b = (out_b / "sweep_manifest.json").read_bytes()
    assert manifest_a == manifest_b

    manifest = json.loads(manifest_a)
    for config in manifest["configs"]:
        rel = config["input_file"]
        assert (out_a / rel).read_bytes() == (out_b / rel).read_bytes(), (
            f"deck {rel} is not byte-reproducible"
        )


# ---------------------------------------------------------------------------
# Isolation guard: unit-level and CLI wiring
# ---------------------------------------------------------------------------


def test_validate_output_dir_rejects_coarse_corpus_and_pilot_dir():
    """The runtime guard rejects an ``--output`` resolving to either frozen path."""
    full_corpus = _load_full_corpus_script()

    with pytest.raises(ValueError, match="frozen coarse corpus"):
        full_corpus._validate_output_dir(_COARSE_CORPUS_DIR)

    with pytest.raises(ValueError, match="pilot"):
        full_corpus._validate_output_dir(_PILOT_DIR)

    # The script's own real output directory must NOT be rejected.
    full_corpus._validate_output_dir(full_corpus.OUTPUT_DIR)


def test_generate_full_corpus_main_rejects_frozen_paths_via_cli(tmp_path, monkeypatch):
    """``main()`` refuses an ``--output`` resolving to either configured frozen-path constant.

    Monkeypatches both ``_FROZEN_CORPUS_DIR`` and ``_PILOT_DIR`` to separate ``tmp_path`` decoys
    (never the real frozen directories), exercising the full CLI wiring (guard -> ``parser.error``
    -> ``SystemExit``) for each independently. Also asserts the decoy directory was never created,
    proving the guard ran *before* ``generate_sweep()`` (which would ``mkdir`` and write into it) --
    not just that ``SystemExit`` eventually happened by some other path.
    """
    full_corpus = _load_full_corpus_script()

    # --timestamp is supplied explicitly (now required -- fix-force-surrogate-sweep-hinge) so the
    # SystemExit asserted below is caused by the frozen-path guard specifically, not by a missing
    # required argument (see test_main_requires_timestamp for that case).
    decoy_coarse = tmp_path / "decoy_prelim_sweep"
    monkeypatch.setattr(full_corpus, "_FROZEN_CORPUS_DIR", decoy_coarse)
    with pytest.raises(SystemExit):
        full_corpus.main(["--output", str(decoy_coarse), "--timestamp", _TIMESTAMP])
    assert not decoy_coarse.exists(), (
        "generate_sweep() must not run before the guard rejects"
    )

    decoy_pilot = tmp_path / "decoy_prelim_sweep_fine_pilot"
    monkeypatch.setattr(full_corpus, "_PILOT_DIR", decoy_pilot)
    with pytest.raises(SystemExit):
        full_corpus.main(["--output", str(decoy_pilot), "--timestamp", _TIMESTAMP])
    assert not decoy_pilot.exists(), (
        "generate_sweep() must not run before the guard rejects"
    )


def test_main_requires_timestamp(tmp_path):
    """Omitting --timestamp is rejected before any file is read or written (fix-force-surrogate-sweep-hinge).

    A real regeneration must supply a fresh, caller-chosen timestamp -- never silently reuse the
    stale 2026-08-03 literal from the script's original (buggy-hinge) authoring session.
    """
    full_corpus = _load_full_corpus_script()

    decoy = tmp_path / "decoy_output"
    with pytest.raises(SystemExit):
        full_corpus.main(["--output", str(decoy)])
    assert not decoy.exists(), (
        "no file should be read or written before the missing --timestamp is rejected"
    )


@pytest.mark.parametrize("bad_timestamp", ["", "not-a-timestamp", "2026-13-45"])
def test_main_rejects_malformed_timestamp(tmp_path, bad_timestamp):
    """--timestamp being *present* isn't enough -- an empty/garbage value must also be rejected."""
    full_corpus = _load_full_corpus_script()

    decoy = tmp_path / "decoy_output"
    with pytest.raises(SystemExit):
        full_corpus.main(["--output", str(decoy), "--timestamp", bad_timestamp])
    assert not decoy.exists()


def test_full_corpus_output_dir_and_workspace_differ_from_coarse_and_pilot():
    """Static isolation guard: the script's constants are distinct from both frozen paths.

    Deliberately does not execute ``generate_sweep()`` against any real, non-tmp_path directory --
    pointed at the script's real defaults, that risks triggering ``generate_sweep()``'s
    stale-deck-pruning ``unlink()`` against a committed corpus. Pure string/Path comparison only.
    """
    full_corpus = _load_full_corpus_script()

    assert full_corpus.OUTPUT_DIR != _COARSE_CORPUS_DIR
    assert full_corpus.OUTPUT_DIR.resolve() != _COARSE_CORPUS_DIR.resolve()
    assert full_corpus.OUTPUT_DIR != _PILOT_DIR
    assert full_corpus.OUTPUT_DIR.resolve() != _PILOT_DIR.resolve()

    assert full_corpus.WORKSPACE_HOSTPATH != _COARSE_WORKSPACE_HOSTPATH
    assert full_corpus.WORKSPACE_HOSTPATH != _PILOT_WORKSPACE_HOSTPATH


def test_committed_fine_corpus_matches_regeneration(tmp_path):
    """The committed fine corpus is byte-identical to a fresh regen with its recorded settings.

    Mirrors the coarse corpus's own `test_committed_sweep_matches_regeneration` (byte-identity,
    not a spot-check) -- this corpus has now been regenerated twice (hinge fix, then field
    capture) with no equivalent permanent regression test before this one. Deliberately does
    NOT assert anything about `sweep_provenance.json`'s `git_commit` -- that value legitimately
    varies from run to run and can't be pinned here; see
    `test_fine_corpus_git_commit_is_a_capable_ancestor` for that separate property.
    """
    fine_corpus = Path("examples/prelim_sweep_fine")
    manifest = json.loads(
        (fine_corpus / "sweep_manifest.json").read_text(encoding="utf-8")
    )
    provenance = json.loads(
        (fine_corpus / "sweep_provenance.json").read_text(encoding="utf-8")
    )
    field_capture = provenance.get("field_capture", {})
    generate_sweep(
        _FINE_BASE,
        tmp_path,
        seed=manifest["holdout"]["seed"],
        n_holdout=manifest["holdout"]["n_holdout"],
        timestamp=provenance["generated_at"],
        plot_int=field_capture.get("plot_int", -1),
        init_iter=field_capture.get("init_iter"),
    )
    committed = sorted((fine_corpus / "inputs").glob("inputs.3d.*"))
    assert len(committed) == 27
    for deck in committed:
        assert deck.read_bytes() == (tmp_path / "inputs" / deck.name).read_bytes()
    assert (fine_corpus / "sweep_manifest.json").read_bytes() == (
        tmp_path / "sweep_manifest.json"
    ).read_bytes()


def test_fine_corpus_git_commit_is_a_capable_ancestor():
    """`sweep_provenance.json`'s `git_commit` must name a commit CAPABLE of producing this corpus.

    Regression guard for a real bug caught only by a manual review round: the recorded
    `git_commit` once named a commit whose checked-out code had no `plot_int`/`init_iter`
    parameters at all -- the regeneration had actually run on a dirty working tree before the
    code was committed. `test_committed_fine_corpus_matches_regeneration` doesn't (and can't)
    catch this, since it only proves the CURRENTLY checked-out code can reproduce the file, not
    that the specific commit recorded in provenance could have.

    An earlier version of this test checked ONLY topological ancestry
    (`git merge-base --is-ancestor`) -- but on a linear branch, ancestry is satisfied by almost
    any older commit, including the exact pre-feature commit this test is supposed to catch: a
    self-review round confirmed `git merge-base --is-ancestor <original-buggy-commit> HEAD`
    trivially succeeds, since that commit IS an ancestor (it's `main`'s own tip). Ancestry alone
    is not a capability check. This test now additionally reads the recorded commit's own tree
    and asserts it actually contains the CLI flags this corpus's `field_capture` block claims
    were used -- a real, discriminating capability check, not just a topological one.

    Skips (doesn't fail) in a shallow clone that doesn't have the recorded commit locally --
    e.g. CI's default `actions/checkout` depth -- rather than reporting a false failure for an
    environment limitation unrelated to the corpus's actual correctness.
    """
    provenance = json.loads(
        Path("examples/prelim_sweep_fine/sweep_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    commit = provenance["git_commit"]
    have_commit = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True,
    )
    if have_commit.returncode != 0:
        pytest.skip(
            f"commit {commit} not present locally (shallow clone?) -- cannot check ancestry"
        )
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True,
    )
    assert ancestor_check.returncode == 0, (
        f"sweep_provenance.json's git_commit={commit!r} is not an ancestor of HEAD -- it "
        "cannot be the commit whose checked-out code produced this corpus"
    )
    # The real, discriminating check: does that commit's OWN tree have the code capable of
    # writing this field-capture corpus? Not "is it old enough" (ancestry) but "does it have the
    # feature at all."
    script_at_commit = subprocess.run(
        ["git", "show", f"{commit}:examples/prelim_sweep_fine/generate_full_corpus.py"],
        capture_output=True,
        text=True,
    )
    assert script_at_commit.returncode == 0, (
        f"could not read generate_full_corpus.py at commit {commit!r}"
    )
    for required_flag in ("--plot-int", "--init-iter"):
        assert required_flag in script_at_commit.stdout, (
            f"commit {commit!r} predates {required_flag} support in "
            "generate_full_corpus.py -- it cannot have produced this field-capture-enabled "
            "corpus, regardless of whether it's topologically an ancestor of HEAD"
        )


def test_generate_full_corpus_cli_accepts_plot_int_and_init_iter_flags(tmp_path):
    """--plot-int/--init-iter are wired through main() to generate_sweep()'s new parameters."""
    full_corpus = _load_full_corpus_script()
    out = tmp_path / "field_capture_run"

    rc = full_corpus.main(
        [
            "--output",
            str(out),
            "--timestamp",
            _TIMESTAMP,
            "--plot-int",
            "100",
            "--init-iter",
            "2",
        ]
    )
    assert rc == 0

    manifest = json.loads((out / "sweep_manifest.json").read_text(encoding="utf-8"))
    for record in manifest["configs"]:
        assert record["plot_int"] == 100
        assert record["init_iter"] == 2

    # Omitting both flags reproduces today's exact force-only default.
    out_default = tmp_path / "default_run"
    rc = full_corpus.main(["--output", str(out_default), "--timestamp", _TIMESTAMP])
    assert rc == 0
    manifest_default = json.loads(
        (out_default / "sweep_manifest.json").read_text(encoding="utf-8")
    )
    for record in manifest_default["configs"]:
        assert record["plot_int"] == -1
        assert "init_iter" not in record


def test_fine_corpus_provenance_flags_superseded_runs():
    """The committed sweep_provenance.json names the stale cluster runs it supersedes.

    fix-force-surrogate-sweep-hinge: the cluster workflows that previously generated this
    corpus's raw CFD output (force-surrogate-sweep-vb8t5 + the retry force-surrogate-retry-
    failed-trz9k) ran against the pre-fix, buggy-hinge decks -- a concrete, machine-checkable
    flag rather than only a prose note, so a truncated/short corpus (or a stale one) is never
    silently mistaken for current.
    """
    provenance = json.loads(
        (Path("examples/prelim_sweep_fine") / "sweep_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    assert provenance.get("superseded_by"), (
        "sweep_provenance.json is missing 'superseded_by'"
    )
    assert provenance["superseded_by"]["cluster_workflows"] == [
        "force-surrogate-sweep-vb8t5",
        "force-surrogate-retry-failed-trz9k",
    ], (
        "superseded_by.cluster_workflows must name exactly the two stale runs, not just be "
        "non-empty -- a typo'd or wrong workflow name must not pass silently"
    )
