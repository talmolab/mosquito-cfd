"""``FieldCorpus``: address plotfiles by ``(config_id, step)`` against a caller-supplied root.

The root is caller-supplied because the real 27-config corpus lives on cluster NFS, not in the
repository -- ``openspec/project.md`` documents its three mount points (the ``Z:`` drive on
Windows, ``/mnt/hpi_dev/users/eberrigan/...`` under WSL, and
``/hpi/hpi_dev/users/eberrigan/...`` on the cluster). Steps are discovered from the ``plt*``
directories actually present on disk rather than assumed from a deck's ``plot_int`` -- a run
can be truncated, as 15 of 27 configs were at ``ns.cfl = 0.3``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mosquito_cfd.field_surrogate.snapshot import DEFAULT_FIELDS, FieldSnapshot

#: Plotfile directory names are ``plt`` followed by digits only. ``plt00300.old`` and ``pltXXXXX``
#: are deliberately not matched.
_PLT_PATTERN = re.compile(r"^plt(\d+)$")

#: Kinematic parameters carried per config in the sweep manifest.
GLOBAL_PARAM_KEYS: tuple[str, ...] = (
    "stroke_amp_deg",
    "frequency_fstar",
    "pitch_amp_deg",
)


class FieldCorpus:
    """Address a field-capture corpus by config id and timestep."""

    def __init__(
        self,
        root: str | Path,
        *,
        manifest: str | Path = "sweep_manifest.json",
        runs_dir: str = "runs",
    ) -> None:
        """Bind the corpus to a root directory.

        Args:
            root: Corpus root containing the sweep manifest and a ``runs/`` directory.
            manifest: Manifest filename or path, relative to ``root`` when relative.
            runs_dir: Name of the directory holding per-config run directories.

        Raises:
            ValueError: If ``root`` does not exist.
        """
        self.root = Path(root)
        if not self.root.is_dir():
            raise ValueError(f"corpus root does not exist: {self.root}")
        manifest_path = Path(manifest)
        self.manifest_path = (
            manifest_path if manifest_path.is_absolute() else self.root / manifest_path
        )
        self.runs_dir = self.root / runs_dir

    def _configs(self) -> list[dict]:
        # Imported lazily: force_surrogate.dataset pulls pandas, and this module must stay cheap
        # for callers that only want snapshots (design.md D4).
        from mosquito_cfd.force_surrogate.dataset import load_manifest_configs

        return load_manifest_configs(self.manifest_path)

    def config_ids(self) -> list[str]:
        """Return the config names listed in the sweep manifest, in manifest order.

        Returns:
            The config names.
        """
        return [str(c["name"]) for c in self._configs()]

    def _config(self, config_id: str) -> dict:
        for config in self._configs():
            if str(config["name"]) == config_id:
                return config
        raise ValueError(
            f"config {config_id!r} is not in manifest {self.manifest_path}; "
            f"known configs: {self.config_ids()}"
        )

    def run_dir(self, config_id: str) -> Path:
        """Return the run directory for a config.

        Args:
            config_id: Config name as listed in the manifest.

        Returns:
            Path to the config's run directory.

        Raises:
            ValueError: If the config is not in the manifest, or its run directory is absent.
        """
        self._config(config_id)
        path = self.runs_dir / config_id
        if not path.is_dir():
            raise ValueError(f"no run directory for config {config_id!r} at {path}")
        return path

    def steps(self, config_id: str) -> list[int]:
        """Return the timesteps whose plotfiles are actually present on disk, ascending.

        Non-directories and names whose suffix after ``plt`` is not an integer are ignored, so a
        stray file or a ``.old`` copy cannot masquerade as a step.

        Args:
            config_id: Config name as listed in the manifest.

        Returns:
            The available steps, sorted ascending.
        """
        found = []
        for entry in self.run_dir(config_id).iterdir():
            match = _PLT_PATTERN.match(entry.name)
            if match and entry.is_dir():
                found.append(int(match.group(1)))
        return sorted(found)

    def global_params(self, config_id: str) -> dict[str, Any]:
        """Return this config's kinematic parameters from the manifest.

        Args:
            config_id: Config name as listed in the manifest.

        Returns:
            The kinematic parameters present for this config.
        """
        config = self._config(config_id)
        return {k: config[k] for k in GLOBAL_PARAM_KEYS if k in config}

    def plotfile(self, config_id: str, step: int) -> Path:
        """Return the plotfile directory for one ``(config_id, step)``.

        Args:
            config_id: Config name as listed in the manifest.
            step: Timestep, as written in the ``pltNNNNN`` directory name.

        Returns:
            Path to the plotfile directory.

        Raises:
            ValueError: If no plotfile for that step exists.
        """
        run = self.run_dir(config_id)
        for candidate in run.iterdir():
            match = _PLT_PATTERN.match(candidate.name)
            if match and candidate.is_dir() and int(match.group(1)) == step:
                return candidate
        raise ValueError(
            f"no plotfile for step {step} of config {config_id!r} under {run} "
            f"(looked for plt{step:05d}); available steps: {self.steps(config_id)}"
        )

    def snapshot(
        self,
        config_id: str,
        step: int,
        *,
        lo=(float("-inf"),) * 3,
        hi=(float("inf"),) * 3,
        halo: int = 0,
        fields: tuple[str, ...] = DEFAULT_FIELDS,
    ) -> FieldSnapshot:
        """Read one training example's field snapshot.

        Args:
            config_id: Config name as listed in the manifest.
            step: Timestep, as written in the ``pltNNNNN`` directory name.
            lo: Physical lower corner; defaults to the full domain.
            hi: Physical upper corner; defaults to the full domain.
            halo: Extra cells sliced on every side.
            fields: Short names to read.

        Returns:
            The :class:`~mosquito_cfd.field_surrogate.snapshot.FieldSnapshot` for that plotfile.
        """
        from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

        return read_field_snapshot(
            self.plotfile(config_id, step), lo=lo, hi=hi, halo=halo, fields=fields
        )
