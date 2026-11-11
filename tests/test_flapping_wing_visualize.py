"""The flapping-wing ``visualize.py`` has no ``forces`` subcommand (issue #109, design D5).

The removed subcommand summed raw particle forces from plotfiles and plotted them as the wing's force
without the sign: ``ib_force`` acts on the fluid. The committed force figures come from the
IB-particle CSV through ``force_on_wing`` instead.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "examples" / "flapping_wing" / "visualize.py"
)


def test_visualize_subcommands_are_velocity_and_vorticity_only():
    help_text = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    choices = re.search(r"\{([a-z,]+)\}", help_text)
    assert choices is not None, help_text
    assert set(choices.group(1).split(",")) == {"velocity", "vorticity"}
    source = _SCRIPT.read_text(encoding="utf-8")
    for removed in (
        "def extract_forces",
        "def visualize_forces",
        "visualize.py forces",
    ):
        assert removed not in source, removed
