"""``FieldCorpus``: address plotfiles by ``(config_id, step)`` against a caller-supplied root.

The root is caller-supplied because the real 27-config corpus lives on cluster NFS, not in the
repository -- ``openspec/project.md`` documents its three mount points (the ``Z:`` drive on
Windows, ``/mnt/hpi_dev/users/eberrigan/...`` under WSL, and
``/hpi/hpi_dev/users/eberrigan/...`` on the cluster). Steps are discovered from the ``plt*``
directories actually present on disk rather than assumed from a deck's ``plot_int`` -- a run
can be truncated, as 15 of 27 configs were at ``ns.cfl = 0.3``. ``plotfile()`` first tries the
canonical AMReX name ``plt{step:05d}`` with a single ``is_dir()`` and lists the run directory
only when that name is not a directory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

from mosquito_cfd.field_surrogate.snapshot import DEFAULT_FIELDS, FieldSnapshot

#: Plotfile directory names are ``plt`` followed by digits only. ``plt00300.old`` and ``pltXXXXX``
#: are deliberately not matched.
_PLT_PATTERN = re.compile(r"^plt(\d+)$")


def _validate_step(step: Any) -> int:
    # Mirrors snapshot._validate_halo. bool is an int subclass (plotfile(c, True) would resolve
    # step 1); np.bool_ is not an np.integer, so the type test rejects it. Checked before any
    # manifest read or filesystem access, so a bad step is reported as a bad step
    # (harden-field-corpus-requests D4). repr() so the string '100' is distinguishable from 100.
    if isinstance(step, bool) or not isinstance(step, (int, np.integer)) or step < 0:
        raise ValueError(f"step must be a non-negative integer, got {step!r}")
    return int(step)


def _scan(run: Path) -> dict[int, Path]:
    """Map step -> plotfile directory for every ``plt<digits>`` directory in ``run``.

    The shared listing behind ``steps()`` and ``plotfile()``'s fallback, so both give the same
    verdict on the same directory. Non-directories are filtered out BEFORE the duplicate check: a
    stray file named like a plotfile is never a duplicate (harden-field-corpus-requests D5).

    Raises:
        ValueError: If two directories parse to the same step, naming both in sorted order so the
            message does not depend on the filesystem's listing order.
    """
    found: dict[int, Path] = {}
    for entry in run.iterdir():
        match = _PLT_PATTERN.match(entry.name)
        if not (match and entry.is_dir()):
            continue
        step = int(match.group(1))
        if step in found:
            names = ", ".join(sorted((found[step].name, entry.name)))
            raise ValueError(
                f"ambiguous plotfiles under {run}: "
                f"two plotfile directories parse to step {step}: {names}"
            )
        found[step] = entry
    return found


#: Kinematic parameters carried per config in the sweep manifest.
GLOBAL_PARAM_KEYS: tuple[str, ...] = (
    "stroke_amp_deg",
    "frequency_fstar",
    "pitch_amp_deg",
)


class FieldCorpus:
    """Address a field-capture corpus by config id and timestep.

    The manifest is parsed once per instance and cached. Plotfile presence is never cached, since
    which plotfiles exist can change while a run is in progress: ``steps()`` lists the ``plt*``
    directories on every call, and ``plotfile()`` stats the canonical ``plt{step:05d}`` first and
    lists only on a miss. Construct a new ``FieldCorpus`` to pick up a manifest edited on disk.
    """

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
        self._configs_cache: list[dict] | None = None

    def _configs(self) -> list[dict]:
        # The manifest is fixed at sweep creation, so it is parsed once per instance; plt*
        # presence is NOT cached (steps() re-lists it). A failed parse is not cached. The cached
        # list and its dicts are shared -- callers must not mutate them.
        if self._configs_cache is None:
            # Imported lazily: force_surrogate.dataset pulls pandas, and this module must stay
            # cheap for callers that only want snapshots (design.md D4).
            from mosquito_cfd.force_surrogate.dataset import load_manifest_configs

            self._configs_cache = load_manifest_configs(self.manifest_path)
        return self._configs_cache

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

        Raises:
            ValueError: If the config is not in the manifest, its run directory is absent, or
                two directories parse to the same step (e.g. ``plt100`` and ``plt00100``).
        """
        return sorted(_scan(self.run_dir(config_id)))

    def global_params(self, config_id: str) -> dict[str, Any]:
        """Return this config's kinematic parameters from the manifest.

        Args:
            config_id: Config name as listed in the manifest.

        Returns:
            The kinematic parameters for this config, one entry per
            :data:`GLOBAL_PARAM_KEYS`.

        Raises:
            ValueError: If the config is not in the manifest, or (via ``_configs()``'s
                ``load_manifest_configs``) if the manifest is missing a required key.
        """
        # Every key is guaranteed by the manifest guard (_REQUIRED_CONFIG_KEYS). Index directly so
        # a broken guarantee is a KeyError, never a shorter dict that misaligns positionally
        # against global_params_reference.
        config = self._config(config_id)
        return {k: config[k] for k in GLOBAL_PARAM_KEYS}

    def plotfile(self, config_id: str, step: int) -> Path:
        """Return the plotfile directory for one ``(config_id, step)``.

        The canonical AMReX name ``plt{step:05d}`` is tried first with one ``is_dir()``; only if
        it is not a directory is the run directory listed. The fast path therefore trusts the
        canonical name: with both ``plt100`` and ``plt00100`` present it returns ``plt00100``
        without reporting the ambiguity, which ``steps()`` and this method's scan do report
        (``harden-field-corpus-requests`` D2).

        Args:
            config_id: Config name as listed in the manifest.
            step: Non-negative integer timestep (``int`` or ``np.integer``, not ``bool``), as
                written in the ``pltNNNNN`` directory name.

        Returns:
            Path to the plotfile directory.

        Raises:
            ValueError: If ``step`` is not a non-negative integer (checked before any I/O), if
                the config is not in the manifest or its run directory is absent, if two
                directories in the run directory parse to the same step, or if no plotfile for
                that step exists.
        """
        step = _validate_step(step)
        self._config(config_id)  # manifest membership first, on both paths
        canonical = self.runs_dir / config_id / f"plt{step:05d}"
        if canonical.is_dir():
            return canonical
        run = self.run_dir(config_id)
        found = _scan(run)
        if step in found:
            return found[step]
        # Available steps come from the scan already done: calling steps() here re-ran the
        # manifest lookup, the run-directory stat and a second listing.
        raise ValueError(
            f"no plotfile for step {step} of config {config_id!r} under {run} "
            f"(no 'plt<digits>' directory parses to step {step}); "
            f"available steps: {sorted(found)}"
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
            step: Non-negative integer timestep, as written in the ``pltNNNNN`` directory name.
            lo: Physical lower corner; defaults to the full domain.
            hi: Physical upper corner; defaults to the full domain.
            halo: Extra cells sliced on every side.
            fields: Short names to read.

        Returns:
            The :class:`~mosquito_cfd.field_surrogate.snapshot.FieldSnapshot` for that plotfile.

        Raises:
            ValueError: Anything :meth:`plotfile` raises (a bad ``step`` before any I/O), and
                anything ``read_field_snapshot`` raises, including ``lo > hi`` on any axis.
        """
        from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

        return read_field_snapshot(
            self.plotfile(config_id, step), lo=lo, hi=hi, halo=halo, fields=fields
        )
