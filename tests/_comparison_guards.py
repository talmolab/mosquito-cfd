"""Committed-figure checker for the coarse-vs-fine figures (add-real-comparison-figures, design D7).

``check_committed_figure(root, figure)`` raises ``AssertionError`` naming the figure and the failing
field or input role when a committed figure no longer matches its inputs or its renderer. It is a
pure function so its red/green logic is tested on synthetic layouts
(``tests/test_comparison_guards.py``) before it is applied to the repository.

Order matters: input hashes are checked **before** any recomputation, so a changed input fails as a
named hash mismatch rather than as whatever the library would make of it.

``git.dirty`` comes from ``git diff HEAD`` and ignores untracked files; ``dirty is False`` does not
prove the render tree was clean (the render procedure checks ``git status`` separately).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

from mosquito_cfd.force_surrogate import comparison_figure as cf

COARSE_DIR = "examples/prelim_sweep"
FINE_DIR = "examples/prelim_sweep_fine"
FIGURE_DIR = "examples/prelim_sweep_fine/figures/coarse_vs_fine"

COMPUTE = {
    "skill_ranges": cf.compute_skill_ranges_metrics,
    "error_histograms": cf.compute_error_histograms_metrics,
    "cycle_mean_r2_diagnostic": cf.compute_cycle_mean_r2_diagnostic_metrics,
}

# Recomputed floats are compared at rel=1e-12, abs=0 (an exact zero must be exactly zero);
# everything else (values read verbatim, counts, edges, strings, drawn states) exactly.
COMPUTED_KEYS = frozenset(
    {
        "sigma",
        "eps",
        "eps_primary_measured",
        "waveform_rms",
        "rmse0",
        "rmse_surrogate",
        "skill",
    }
)
_HEX40 = re.compile(r"[0-9a-f]{40}")
_LIBRARIES = ("python", "numpy", "pandas", "pyarrow", "matplotlib")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == 0 or b == 0:
            return a == b
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=0)
    return a == b


def _compare(
    committed: Any, fresh: Any, figure: str, path: str, computed: bool
) -> None:
    if isinstance(committed, dict) and isinstance(fresh, dict):
        assert set(committed) == set(fresh), (
            f"{figure}: {figure}_metrics.json keys at '{path}' differ: "
            f"{sorted(set(committed) ^ set(fresh))}"
        )
        for key in committed:
            _compare(
                committed[key],
                fresh[key],
                figure,
                f"{path}.{key}" if path else key,
                computed or key in COMPUTED_KEYS,
            )
        return
    ok = _close(committed, fresh) if computed else committed == fresh
    assert ok, (
        f"{figure}: {figure}_metrics.json value at '{path}' is stale: committed "
        f"{committed!r}, recomputed {fresh!r}"
    )


def check_committed_figure(root: Path, figure: str) -> None:
    """Assert that ``figure``'s committed sidecars still match its inputs and renderer."""
    root = Path(root)
    out = root / FIGURE_DIR
    meta = json.loads((out / f"{figure}_run_metadata.json").read_text(encoding="utf-8"))
    committed = json.loads((out / f"{figure}_metrics.json").read_text(encoding="utf-8"))

    # 1. Input hashes, before anything is recomputed.
    roles = {f"{c}_{r}" for c in ("coarse", "fine") for r in cf.ROLE_FILES}
    assert set(meta.get("input_files", {})) == roles, (
        f"{figure}: input_files roles {sorted(meta.get('input_files', {}))} != {sorted(roles)}"
    )
    for role, entry in meta["input_files"].items():
        recorded = entry["path"]
        assert "\\" not in recorded, (
            f"{figure}: input_files.{role} path has a backslash: {recorded}"
        )
        posix = PurePosixPath(recorded)
        assert (
            not posix.is_absolute() and ":" not in recorded and ".." not in posix.parts
        ), f"{figure}: input_files.{role} path is not repository-relative: {recorded}"
        file = root / recorded
        assert file.is_file(), f"{figure}: input {role} ({recorded}) is missing"
        assert _sha256(file) == entry["sha256"], (
            f"{figure}: input {role} ({recorded}) changed since the figure was rendered"
        )
    assert meta.get("inputs") == {
        "file": meta["input_files"]["coarse_metrics"]["path"],
        "hash": meta["input_files"]["coarse_metrics"]["sha256"],
    }, f"{figure}: inputs does not name coarse_metrics"

    # 2. The metrics sidecar equals a fresh recomputation from the committed inputs.
    try:
        fresh = COMPUTE[figure](root=root, coarse_dir=COARSE_DIR, fine_dir=FINE_DIR)
    except ValueError as exc:
        raise AssertionError(
            f"{figure}: the committed inputs fail a guard: {exc}"
        ) from exc
    _compare(committed, json.loads(cf._dumps(fresh)), figure, "", computed=False)

    # 3. The enumerated run-metadata fields.
    sources = cf._renderer_sources()
    assert all(v is not None for v in sources.values()), (
        f"{figure}: a renderer file is missing"
    )
    assert meta.get("renderer_sources") == sources, (
        f"{figure}: renderer_sources differ from the current renderer; re-render all three figures"
    )
    images = {}
    for corpus, base in (("coarse", COARSE_DIR), ("fine", FINE_DIR)):
        record = root / base / "surrogate" / "run_metadata.json"
        images[corpus] = json.loads(record.read_text(encoding="utf-8"))["docker_image"]
    assert meta.get("corpus_docker_images") == images, (
        f"{figure}: corpus_docker_images differ"
    )
    fine_record = json.loads(
        (root / FINE_DIR / "run_metadata.json").read_text(encoding="utf-8")
    )
    assert meta.get("docker_image") == fine_record["docker_image"], (
        f"{figure}: docker_image is not the fine corpus's CFD digest"
    )
    versions = meta.get("library_versions", {})
    assert set(versions) == set(_LIBRARIES) and all(
        isinstance(versions[k], str) and versions[k] for k in _LIBRARIES
    ), f"{figure}: library_versions incomplete: {versions}"
    git = meta.get("git", {})
    assert isinstance(git.get("commit"), str) and _HEX40.fullmatch(git["commit"]), (
        f"{figure}: git.commit is not a 40-hex commit: {git.get('commit')!r}"
    )
    assert git.get("dirty") is False, f"{figure}: git.dirty is not false"
    assert meta.get("figure") == figure, (
        f"{figure}: figure field is {meta.get('figure')!r}"
    )
    png = out / f"{figure}.png"
    assert png.is_file() and meta.get("png_sha256") == _sha256(png), (
        f"{figure}: {figure}.png does not match its recorded png_sha256"
    )
