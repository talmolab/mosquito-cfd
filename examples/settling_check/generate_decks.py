r"""Generate the Stage 1 settling-check decks (OpenSpec change add-settled-beat-corpus, #192).

Every deck starts from the committed 2-beat corpus deck of the same configuration and grid, and
changes only a declared key set; ``settling.deck_key_mismatches`` checks that before anything is
written. What the runs are and why is in ``PREREGISTRATION.md``; this file's bytes are pinned by
every run record, so change it only before the runs or with a ``deviations.json`` entry.

Writes (relative to this directory):

- ``<grid>/inputs/inputs.3d.<config>``: the 8-beat decks (six in all);
- ``<grid>/controls/inputs.3d.c1_s55_f115_p30``: the C1 control decks (400 steps);
- ``<grid>/sweep_manifest.json``: the configs in the sweep-manifest schema, so the existing
  ``scripts/extract_forces.py`` builds each grid's dataset unchanged;
- ``settling_manifest.json``: runs, controls, deck hashes, declared keys and images.

Usage, from the repository root::

    uv run python examples/settling_check/generate_decks.py          # write
    uv run python examples/settling_check/generate_decks.py --check  # compare, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.metadata_capture import parse_deck
from mosquito_cfd.force_surrogate.settling import deck_key_mismatches
from mosquito_cfd.force_surrogate.sweep import derive_run_duration

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

N_WINGBEATS = 8
FRAMES_PER_BEAT = 20
CHECKPOINTS_PER_BEAT = 1
ARENA_BYTES = 12884901888  # 12 GiB: the A5000's 24 GB cannot take AMReX's default arena
C1_CONFIG = "s55_f115_p30"
C1_STEPS = 400
CONFIGS = ("s35_f085_p30", "s45_f100_p30", "s55_f115_p30")
SOURCES = {"coarse": "examples/prelim_sweep", "fine": "examples/prelim_sweep_fine"}
IMAGES = {
    "coarse": "ghcr.io/talmolab/mosquito-cfd@sha256:"
    "07625ce41bef8dae5983afddf5a3d09a3fb7706cb29292d19a479600967b24d3",
    "fine": "ghcr.io/talmolab/mosquito-cfd@sha256:"
    "92817878fead23f9c6b8219706a2ebcec7cccf2158db8016e867e0227ca68a47",
}
LONG_KEYS = (
    "amr.check_int",
    "amr.check_per",
    "amr.plot_int",
    "amr.plot_per",
    "amrex.the_arena_init_size",
    "max_step",
    "stop_time",
)
# The coarse corpus decks already have amr.plot_int = -1, so that key is not a change there.
LONG_KEYS_BY_GRID = {
    "coarse": tuple(k for k in LONG_KEYS if k != "amr.plot_int"),
    "fine": LONG_KEYS,
}
C1_KEYS = ("amrex.the_arena_init_size", "max_step")


def _num(value: float) -> str:
    """Shortest round-trippable float text, as ``sweep.render_inputs`` writes it."""
    return str(float(value))


def rewrite_deck(text: str, values: dict[str, str]) -> str:
    """Set each key in ``values``: rewrite its value token in place, or append it if absent.

    Only the value token of an existing key is replaced; alignment and inline comments survive.
    Absent keys are appended, in sorted order, under one comment line.
    """
    remaining = dict(values)
    out: list[str] = []
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            before, after = line.split("=", 1)
            key = before.strip()
            if key in remaining:
                lead = after[: len(after) - len(after.lstrip())]
                tail = after[len(lead) :]
                end = 0
                while end < len(tail) and not tail[end].isspace():
                    end += 1
                out.append(f"{before}={lead}{remaining.pop(key)}{tail[end:]}")
                continue
        out.append(line)
    if remaining:
        out.append("")
        out.append(
            "# settling check (add-settled-beat-corpus): keys absent from the corpus deck"
        )
        width = max(len(k) for k in remaining)
        for key in sorted(remaining):
            out.append(f"{key.ljust(width)} = {remaining[key]}")
    return "\n".join(out) + "\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dump(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _source_entry(grid: str, config: str, repo: Path) -> tuple[dict, dict, Path]:
    base = repo / SOURCES[grid]
    manifest = json.loads((base / "sweep_manifest.json").read_text(encoding="utf-8"))
    entry = next(c for c in manifest["configs"] if c["name"] == config)
    return manifest, entry, base / entry["input_file"]


def _render(
    source_deck: Path, values: dict[str, str], declared: Sequence[str]
) -> bytes:
    text = rewrite_deck(source_deck.read_text(encoding="utf-8"), values)
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "deck"
        probe.write_text(text, encoding="utf-8", newline="\n")
        problems = deck_key_mismatches(
            parse_deck(source_deck), parse_deck(probe), set(declared)
        )
    if problems:
        raise ValueError(f"{source_deck}: " + "; ".join(problems))
    return text.encode("utf-8")


def build(repo: Path = REPO) -> dict[str, bytes]:
    """Return ``{relative path: bytes}`` for every generated file (nothing is written)."""
    files: dict[str, bytes] = {}
    runs: list[dict] = []
    controls: list[dict] = []
    for grid in ("coarse", "fine"):
        sweep_configs: list[dict] = []
        top: dict = {}
        for config in CONFIGS:
            manifest, entry, source_deck = _source_entry(grid, config, repo)
            f_star = float(entry["frequency_fstar"])
            max_step, stop_time = derive_run_duration(f_star, n_wingbeats=N_WINGBEATS)
            values = {
                "max_step": str(max_step),
                "stop_time": _num(stop_time),
                "amrex.the_arena_init_size": str(ARENA_BYTES),
                "amr.plot_int": "-1",
                "amr.plot_per": _num(1.0 / (FRAMES_PER_BEAT * f_star)),
                "amr.check_int": "-1",
                "amr.check_per": _num(1.0 / (CHECKPOINTS_PER_BEAT * f_star)),
            }
            deck_rel = f"{grid}/inputs/inputs.3d.{config}"
            files[deck_rel] = _render(source_deck, values, LONG_KEYS_BY_GRID[grid])
            source_rel = source_deck.relative_to(repo).as_posix()
            runs.append(
                {
                    "name": f"{grid}_{config}",
                    "grid": grid,
                    "config": config,
                    "kind": "long",
                    "deck": deck_rel,
                    "deck_sha256": _sha(files[deck_rel]),
                    "source_deck": source_rel,
                    "source_deck_sha256": _sha(source_deck.read_bytes()),
                    "declared_keys": list(LONG_KEYS_BY_GRID[grid]),
                    "image": IMAGES[grid],
                    "n_wingbeats": N_WINGBEATS,
                    "max_step": max_step,
                    "stop_time": stop_time,
                    "controls": ["C3", "C4"],
                }
            )
            sweep_configs.append(
                {
                    **{k: v for k, v in entry.items() if k != "plot_int"},
                    "input_file": f"inputs/inputs.3d.{config}",
                    "max_step": max_step,
                    "stop_time": stop_time,
                    "plot_per": 1.0 / (FRAMES_PER_BEAT * f_star),
                    "check_per": 1.0 / (CHECKPOINTS_PER_BEAT * f_star),
                }
            )
            top = {k: v for k, v in manifest.items() if k not in ("configs", "holdout")}
            if config == C1_CONFIG:
                c1_rel = f"{grid}/controls/inputs.3d.c1_{config}"
                files[c1_rel] = _render(
                    source_deck,
                    {
                        "max_step": str(C1_STEPS),
                        "amrex.the_arena_init_size": str(ARENA_BYTES),
                    },
                    C1_KEYS,
                )
                controls.append(
                    {
                        "name": f"{grid}_c1_{config}",
                        "grid": grid,
                        "config": config,
                        "kind": "C1",
                        "deck": c1_rel,
                        "deck_sha256": _sha(files[c1_rel]),
                        "source_deck": source_rel,
                        "source_deck_sha256": _sha(source_deck.read_bytes()),
                        "declared_keys": list(C1_KEYS),
                        "image": IMAGES[grid],
                        "max_step": C1_STEPS,
                        "stop_time": float(entry["stop_time"]),
                        "reference": f"{SOURCES[grid]}/dataset.parquet",
                    }
                )
        files[f"{grid}/sweep_manifest.json"] = _dump(
            {**top, "n_wingbeats": N_WINGBEATS, "configs": sweep_configs}
        )
    files["settling_manifest.json"] = _dump(
        {
            "schema_version": 1,
            "change": "add-settled-beat-corpus",
            "preregistration": "examples/settling_check/PREREGISTRATION.md",
            "n_wingbeats": N_WINGBEATS,
            "frames_per_beat": FRAMES_PER_BEAT,
            "checkpoints_per_beat": CHECKPOINTS_PER_BEAT,
            "images": IMAGES,
            "runs": runs,
            "controls": controls,
        }
    )
    return files


def generate(repo: Path, out_dir: Path) -> dict[str, bytes]:
    """Write every generated file under ``out_dir`` (LF line endings)."""
    files = build(repo)
    for rel, data in files.items():
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return files


def main(argv: Sequence[str] | None = None) -> int:
    """Write the decks, or with ``--check`` compare them with the committed files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="compare only; write nothing"
    )
    args = parser.parse_args(argv)
    if not args.check:
        generate(REPO, HERE)
        return 0
    stale = [
        rel
        for rel, data in build(REPO).items()
        if not (HERE / rel).exists() or (HERE / rel).read_bytes() != data
    ]
    for rel in stale:
        print(f"stale or missing: examples/settling_check/{rel}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
