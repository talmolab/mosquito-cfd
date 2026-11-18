"""``FieldCorpus``: address plotfiles by ``(config_id, step)`` against a caller-supplied root.

The root is caller-supplied because the real 27-config corpus lives on cluster NFS, not in the
repository -- ``openspec/project.md`` documents its three mount points (the ``Z:`` drive on
Windows, ``/mnt/hpi_dev/users/eberrigan/...`` under WSL, and
``/hpi/hpi_dev/users/eberrigan/...`` on the cluster). Steps are discovered from the ``plt*``
directories actually present on disk rather than assumed from a deck's ``plot_int`` -- a run
can be truncated, as 15 of 27 configs were at ``ns.cfl = 0.3``. ``plotfile()`` first tries the
canonical AMReX name ``plt{step:05d}`` with a single ``is_dir()`` and lists the run directory
only when that name is not a directory. A listing is one ``os.scandir`` with no Python-level
``stat`` per entry: each entry's type comes from its ``DirEntry``. Every path the module takes
or returns is a ``pathlib.Path``.

``snapshot()`` stamps each snapshot with its ``(config_id, step)`` and the run's digest-pinned
provenance -- ``git.commit`` and ``docker_image`` -- copied from the ``run_metadata.json`` the pod
wrote into the run directory, strictly validated and never fabricated; a run without one cannot
produce a corpus snapshot. ``run_metadata()`` returns that file read through.
"""

from __future__ import annotations

import dataclasses
import errno
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

from mosquito_cfd._messages import plain_repr
from mosquito_cfd.field_surrogate._provenance import read_run_metadata, run_provenance
from mosquito_cfd.field_surrogate.snapshot import (
    DEFAULT_FIELDS,
    FieldSnapshot,
    _check_plotfile_dir,
    _validate_request,
)

#: Plotfile directory names are ``plt`` followed by ASCII digits only, matched with ``fullmatch``
#: against the whole name. ``plt00300.old`` and ``pltXXXXX`` are deliberately not matched, nor are
#: ``plt`` + non-ASCII decimal digits (``\d`` would match them, and ``int()`` parses them) or a
#: name with a trailing newline (``$`` would match before it) -- #145.
_PLT_PATTERN = re.compile(r"plt([0-9]+)")


def _validate_step(step: Any) -> int:
    # Mirrors snapshot._validate_halo. bool is an int subclass (plotfile(c, True) would resolve
    # step 1); np.bool_ is not an np.integer, so the type test rejects it. Checked before any
    # manifest read or filesystem access, so a bad step is reported as a bad step
    # (harden-field-corpus-requests D4). repr() so the string '100' is distinguishable from 100.
    if isinstance(step, bool) or not isinstance(step, (int, np.integer)) or step < 0:
        # plain_repr: numpy scalars are shown as their plain value, as in the halo and
        # box_margin messages -- never numpy 2's "np.int64(-1)" repr.
        raise ValueError(f"step must be a non-negative integer, got {plain_repr(step)}")
    return int(step)


#: The type-check failures Python 3.11's ``Path.is_dir()`` reported as "not a directory"
#: (``pathlib._IGNORED_ERRNOS`` and ``_IGNORED_WINERRORS``): a vanished entry, a symlink through
#: a file, a bad descriptor, a symlink loop, and three Windows path errors. ``DirEntry.is_dir()``
#: itself swallows only ``FileNotFoundError``.
_NOT_A_DIRECTORY_ERRNOS = frozenset(
    {errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP}
)
_NOT_A_DIRECTORY_WINERRORS = frozenset({21, 123, 1921})


def _is_dir(entry: os.DirEntry) -> bool:
    # Keeps the verdict Path.is_dir() gave before the listing moved to os.scandir, so one broken
    # symlink cannot take down a config's whole step list; any other OSError (e.g. EACCES, EIO)
    # still propagates. ValueError is Path.is_dir()'s "non-encodable path".
    try:
        return entry.is_dir()
    except OSError as exc:
        if (
            exc.errno in _NOT_A_DIRECTORY_ERRNOS
            or getattr(exc, "winerror", None) in _NOT_A_DIRECTORY_WINERRORS
        ):
            return False
        raise
    except ValueError:
        return False


def scan_plotfiles(run: Path) -> dict[int, Path]:
    """Map step -> plotfile directory for every ``plt<digits>`` directory in ``run``.

    The repository's one definition of "which plotfiles a directory holds": the listing behind
    ``steps()`` and ``plotfile()``'s fallback, and ``visualization.flow_video``'s frame discovery
    (#144), so every consumer gives the same verdict on the same directory. Any digit width counts
    (AMReX's ``plt{step:05d}`` has six digits from step 100000 on); sort the keys for step order. Non-directories are filtered out BEFORE the duplicate check: a
    stray file named like a plotfile is never a duplicate (harden-field-corpus-requests D5).

    One ``os.scandir`` lists the directory, and each entry's type comes from its ``DirEntry``
    where the filesystem reports it, so there is no Python-level ``stat`` per entry (on NFS the
    kernel may still stat an entry whose type the server did not return, or a symlink). No
    ``Path`` API keeps the ``DirEntry`` before Python 3.14's ``Path.info``
    (improve-field-reader-perf-memory D1). The type check follows symlinks and skips exactly the
    entries ``Path.is_dir()`` skipped -- vanished, dangling, looping, or through a file; see
    :func:`_is_dir` -- and any other ``OSError`` propagates.

    Raises:
        ValueError: If two directories parse to the same step, naming both in sorted order so the
            message does not depend on the filesystem's listing order.
    """
    found: dict[int, Path] = {}
    # `with` closes the directory handle on the duplicate raise too, not only on exhaustion.
    with os.scandir(run) as entries:
        for entry in entries:
            match = _PLT_PATTERN.fullmatch(entry.name)
            if not (match and _is_dir(entry)):
                continue
            step = int(match.group(1))
            if step in found:
                names = ", ".join(sorted((found[step].name, entry.name)))
                raise ValueError(
                    f"ambiguous plotfiles under {run}: "
                    f"two plotfile directories parse to step {step}: {names}"
                )
            found[step] = run / entry.name
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
    directories on every call (one ``os.scandir``, no per-entry ``stat``), and ``plotfile()``
    stats the canonical ``plt{step:05d}`` first and lists only on a miss. Construct a new
    ``FieldCorpus`` to pick up a manifest edited on disk.
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

        Non-directories and names whose suffix after ``plt`` is not one or more ASCII digits are
        ignored, so a stray file or a ``.old`` copy cannot masquerade as a step.

        Args:
            config_id: Config name as listed in the manifest.

        Returns:
            The available steps, sorted ascending.

        Raises:
            ValueError: If the config is not in the manifest, its run directory is absent, or
                two directories parse to the same step (e.g. ``plt100`` and ``plt00100``).
        """
        return sorted(scan_plotfiles(self.run_dir(config_id)))

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

    def plotfile(self, config_id: str, step: int | np.integer) -> Path:
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
        found = scan_plotfiles(run)
        if step in found:
            return found[step]
        # Available steps come from the scan already done: calling steps() here re-ran the
        # manifest lookup, the run-directory stat and a second listing.
        raise ValueError(
            f"no plotfile for step {step} of config {config_id!r} under {run} "
            f"(no 'plt<digits>' directory parses to step {step}); "
            f"available steps: {sorted(found)}"
        )

    def run_metadata(self, config_id: str) -> dict[str, Any]:
        """Return the run's own pod-written ``run_metadata.json``, read through unchanged.

        Parsed afresh on every call -- never cached -- so mutating a result cannot reach a later
        call, and a file the pod writes at the end of a run is seen.

        Args:
            config_id: Config name as listed in the manifest.

        Returns:
            The parsed JSON object, with no key added, defaulted, renamed or derived.

        Raises:
            ValueError: If the config is not in the manifest or its run directory is absent, or
                if ``run_metadata.json`` is absent, unreadable, not JSON, or not a JSON object.
        """
        path = self.run_dir(config_id) / "run_metadata.json"
        return read_run_metadata(path, config_id=config_id)

    def snapshot(
        self,
        config_id: str,
        step: int | np.integer,
        *,
        lo=(float("-inf"),) * 3,
        hi=(float("inf"),) * 3,
        halo: int = 0,
        fields: tuple[str, ...] = DEFAULT_FIELDS,
    ) -> FieldSnapshot:
        """Read one training example's field snapshot, with the run's identity and digest.

        Order (harden-field-reader-pre-f3 D4): the ``step`` and region arguments are checked with
        no I/O; then the plotfile is resolved; then the run's ``run_metadata.json`` is read and
        validated -- **before** the plotfile is read, so a run without valid provenance fails
        fast; then the plotfile is read.

        Args:
            config_id: Config name as listed in the manifest.
            step: Non-negative integer timestep, as written in the ``pltNNNNN`` directory name.
            lo: Physical lower corner; defaults to the full domain.
            hi: Physical upper corner; defaults to the full domain.
            halo: Extra cells sliced on every side.
            fields: Short names to read.

        Returns:
            The :class:`~mosquito_cfd.field_surrogate.snapshot.FieldSnapshot` for that plotfile,
            with ``config_id``, ``step`` (a Python ``int``), ``git_commit`` and ``docker_image``
            set. The last two are copied from the run's ``run_metadata.json``, never inferred.

        Raises:
            ValueError: An invalid ``step`` or region argument (before any I/O); anything
                :meth:`plotfile` raises; a missing or unverifiable ``run_metadata.json`` (absent,
                unreadable, not a JSON object, a ``config`` naming another run, a commit that is
                not 40 lowercase hex characters, or an image that is not ``<repo>@sha256:<64
                hex>``); anything ``read_field_snapshot`` raises; and a region with zero cells
                on any axis (refused after the read, which costs nothing for such a region).
            FileNotFoundError: If the resolved plotfile directory has no ``Header``.
        """
        from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

        step = _validate_step(step)
        # The NORMALIZED values are what gets read: _validate_request consumes an iterator
        # `fields`, so passing the caller's object on would read zero fields (design D8.1).
        lo_v, hi_v, halo_v, fields_v = _validate_request(lo, hi, halo, fields)
        plotfile = self.plotfile(config_id, step)
        # A plotfile still being written (no Header) is reported as such, not as a provenance
        # error (D8.1).
        _check_plotfile_dir(plotfile)
        meta_path = self.runs_dir / config_id / "run_metadata.json"
        meta = read_run_metadata(meta_path, config_id=config_id)
        git_commit, docker_image = run_provenance(
            meta, config_id=config_id, path=meta_path
        )
        snap = read_field_snapshot(
            plotfile, lo=lo_v, hi=hi_v, halo=halo_v, fields=fields_v
        )
        counts = (snap.x.size, snap.y.size, snap.z.size)
        if 0 in counts:
            # A zero-point example is structurally valid, batches, and trains on nothing: refuse it
            # here, at the corpus entry point every field consumer uses (harden-field-reader-pre-f3
            # D5). read_field_snapshot itself keeps returning it, as specified.
            raise ValueError(
                f"zero-cell snapshot for config {config_id!r} step={step}: region "
                f"lo={tuple(float(v) for v in lo_v)} hi={tuple(float(v) for v in hi_v)} "
                f"halo={halo_v} has {counts} cells per axis; a training example needs at least "
                f"one cell on every axis"
            )
        return dataclasses.replace(
            snap,
            config_id=config_id,
            step=step,
            git_commit=git_commit,
            docker_image=docker_image,
        )
