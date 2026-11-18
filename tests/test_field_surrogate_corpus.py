"""Tests for mosquito_cfd.field_surrogate.corpus (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import errno
import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.field_surrogate.corpus import FieldCorpus

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lev_boxlib_plt"

_KINEMATICS = {
    "stroke_amp_deg": 35.0,
    "frequency_fstar": 0.85,
    "pitch_amp_deg": 30.0,
    "reynolds": 42.5537291206389,
    "split": "train",
}


def _manifest(names: list[str]) -> dict:
    return {
        "schema_version": 1,
        "configs": [
            {
                "name": name,
                "index": i,
                "input_file": f"inputs/inputs.3d.{name}",
                **_KINEMATICS,
            }
            for i, name in enumerate(names)
        ],
    }


def _corpus(tmp_path: Path, names=("s35_f085_p30",), steps=(100,)) -> Path:
    root = tmp_path / "corpus"
    (root / "runs").mkdir(parents=True)
    (root / "sweep_manifest.json").write_text(json.dumps(_manifest(list(names))))
    for name in names:
        for step in steps:
            shutil.copytree(FIXTURE, root / "runs" / name / f"plt{step:05d}")
    return root


def _under(path, root: Path) -> bool:
    """Whether an ``os`` call's path argument lies under ``root`` (an fd never does)."""
    if path is None or isinstance(path, int):
        return False
    target = os.path.abspath(os.fsdecode(os.fspath(path)))
    return Path(target).is_relative_to(os.path.abspath(root))


class _Listing:
    """Stand-in for ``os.scandir``'s iterator: iterable, a context manager, and closable."""

    def __init__(self, entries):
        self._it = iter(entries)
        self.closed = 0

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._it)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.closed += 1


class _StubEntry:
    """A ``DirEntry`` stand-in whose ``is_dir()`` returns, or raises, ``is_dir``."""

    def __init__(self, run: Path, name: str, is_dir=True):
        self.name = name
        self.path = os.path.join(run, name)
        self._is_dir = is_dir

    def is_dir(self, *, follow_symlinks=True):
        if isinstance(self._is_dir, BaseException):
            raise self._is_dir
        return self._is_dir


def _fake_scandir(monkeypatch, root: Path, *, order=(), extra=()) -> list[str]:
    """Replace ``os.scandir`` for paths under ``root`` with a forced-order listing.

    The real ``DirEntry`` objects are yielded with the names in ``order`` first, then the rest,
    then the ``extra`` stub entries. NTFS lists names sorted and ext4 hash-ordered, so a check that
    depends on the order it sees is pinned to an adverse one rather than left to the filesystem.

    Returns:
        The names of the directories listed, so the caller can assert the fake was used: a test
        that forces an order the code never sees passes vacuously.
    """
    real = os.scandir
    calls: list[str] = []
    rank = {name: i for i, name in enumerate(order)}

    def fake(path="."):
        if not _under(path, root):
            return real(path)
        calls.append(Path(os.fsdecode(os.fspath(path))).name)
        with real(path) as it:
            entries = sorted(it, key=lambda e: rank.get(e.name, len(rank)))
        return _Listing([*entries, *extra])

    monkeypatch.setattr(os, "scandir", fake)
    return calls


def _symlink_or_skip(target: Path, link: Path) -> None:
    # Skip only where the platform needs it: Windows without the symlink privilege. On Linux CI
    # a failure here is a real error (e.g. a fixture bug), and turning it into a skip would
    # leave the only real-filesystem symlink tests silently unrun.
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        if sys.platform != "win32":
            raise
        pytest.skip(f"cannot create a directory symlink here: {exc}")


def test_resolves_a_snapshot_by_config_and_step(tmp_path):
    root = _corpus(tmp_path)
    _write_run_metadata(root / "runs" / "s35_f085_p30")
    corpus = FieldCorpus(root)

    assert corpus.config_ids() == ["s35_f085_p30"]
    assert corpus.steps("s35_f085_p30") == [100]

    params = corpus.global_params("s35_f085_p30")
    assert params["stroke_amp_deg"] == 35.0
    assert params["frequency_fstar"] == 0.85
    assert params["pitch_amp_deg"] == 30.0

    snap = corpus.snapshot("s35_f085_p30", step=100)
    assert snap.time == pytest.approx(0.5)
    assert snap.arrays["u"].shape == (6, 6, 6)


def test_steps_come_from_disk_not_from_plot_int(tmp_path):
    # A run can be truncated -- 15 of 27 configs were at ns.cfl = 0.3 -- so the deck's plot_int
    # is not evidence about which plotfiles exist.
    root = _corpus(tmp_path, names=("a", "b"), steps=(100, 200))
    shutil.rmtree(root / "runs" / "b" / "plt00200")

    corpus = FieldCorpus(root)
    assert corpus.steps("a") == [100, 200]
    assert corpus.steps("b") == [100]


def test_steps_ignore_non_plotfile_entries_and_are_deterministic(tmp_path):
    root = _corpus(tmp_path, steps=(100, 1000))
    run = root / "runs" / "s35_f085_p30"
    (run / "plt00200").write_text("a file, not a directory")
    (run / "plt00300.old").mkdir()
    (run / "pltXXXXX").mkdir()

    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == [100, 1000]
    assert corpus.steps("s35_f085_p30") == corpus.steps("s35_f085_p30")


def test_missing_config_is_self_describing(tmp_path):
    corpus = FieldCorpus(_corpus(tmp_path))
    with pytest.raises(ValueError, match="nope") as excinfo:
        corpus.snapshot("nope", step=100)
    assert "s35_f085_p30" in str(excinfo.value)


def test_missing_step_is_self_describing(tmp_path):
    corpus = FieldCorpus(_corpus(tmp_path))
    with pytest.raises(ValueError) as excinfo:
        corpus.snapshot("s35_f085_p30", step=999)
    message = str(excinfo.value)
    assert "999" in message
    assert "plt00999" in message or "s35_f085_p30" in message


def test_missing_step_message_does_not_claim_a_fixed_digit_width(tmp_path):
    # Review correction. The message hardcoded `plt{step:05d}` as "looked for", but the actual
    # matching regex (_PLT_PATTERN, shared with steps()) accepts any digit width and compares by
    # parsed integer -- so once a plotfile directory uses non-5-digit padding, the message names
    # a literal filename the code never actually searches for.
    root = _corpus(tmp_path, steps=(100,))
    run = root / "runs" / "s35_f085_p30"
    (run / "plt00100").rename(run / "plt100")

    corpus = FieldCorpus(root)
    with pytest.raises(ValueError) as excinfo:
        corpus.plotfile("s35_f085_p30", step=999)
    message = str(excinfo.value)
    assert "plt00999" not in message
    assert "999" in message


def test_missing_root_is_self_describing(tmp_path):
    with pytest.raises(ValueError, match="does_not_exist"):
        FieldCorpus(tmp_path / "does_not_exist")


def test_malformed_manifest_surfaces_the_guarded_error(tmp_path):
    root = _corpus(tmp_path)
    (root / "sweep_manifest.json").write_text(json.dumps({"not_configs": []}))
    corpus = FieldCorpus(root)
    with pytest.raises(ValueError, match="configs"):
        corpus.config_ids()


# --- review corrections (tasks 52-53) ---------------------------------------------------------


def test_global_params_returns_exactly_the_kinematic_keys(tmp_path):
    # Task 52. `return dict(config)` survived the original suite, leaking reynolds, split,
    # input_file and index into what a caller hands to to_domino_volume as global_params_values.
    # Key names are literal here, NOT imported from the module under test.
    params = FieldCorpus(_corpus(tmp_path)).global_params("s35_f085_p30")
    assert set(params) == {"stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"}


def test_manifest_missing_a_kinematic_key_is_rejected_by_the_manifest_guard(tmp_path):
    # End-to-end: the rejection comes from force_surrogate.dataset._validate_configs, reached
    # through _configs() before global_params() runs -- not from corpus.py itself.
    root = _corpus(tmp_path)
    manifest_path = root / "sweep_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["configs"][0]["pitch_amp_deg"]
    manifest_path.write_text(json.dumps(manifest))

    corpus = FieldCorpus(root)
    with pytest.raises(ValueError, match="pitch_amp_deg"):
        corpus.global_params("s35_f085_p30")


def test_global_param_keys_are_all_required_by_the_manifest_guard():
    # The invariant global_params() relies on to index keys directly. If a kinematic key is ever
    # added to GLOBAL_PARAM_KEYS without the manifest guard requiring it, this fails first.
    from mosquito_cfd.field_surrogate.corpus import GLOBAL_PARAM_KEYS
    from mosquito_cfd.force_surrogate.dataset import _REQUIRED_CONFIG_KEYS

    assert set(GLOBAL_PARAM_KEYS) <= _REQUIRED_CONFIG_KEYS


def test_global_params_never_returns_a_shortened_dict(tmp_path, monkeypatch):
    # Bypasses the manifest guard to exercise global_params() itself: a config missing a key
    # must fail loudly, not come back one entry short and misalign positionally against
    # global_params_reference in to_domino_volume.
    import mosquito_cfd.force_surrogate.dataset as fs_dataset

    root = _corpus(tmp_path)
    config = {"name": "s35_f085_p30", "stroke_amp_deg": 35.0, "frequency_fstar": 0.85}
    monkeypatch.setattr(fs_dataset, "load_manifest_configs", lambda _path: [config])
    with pytest.raises(KeyError, match="pitch_amp_deg"):
        FieldCorpus(root).global_params("s35_f085_p30")


def test_manifest_is_parsed_from_disk_only_once_per_instance(tmp_path, monkeypatch):
    # Review correction. _configs() re-parsed sweep_manifest.json from disk on every call, with
    # no caching -- config_ids(), _config() (hence run_dir/global_params/plotfile/snapshot) all
    # go through it. The module docstring says the real corpus root lives on cluster NFS, so this
    # becomes a real per-call cost once F3 builds a DataLoader on top of it.
    import mosquito_cfd.force_surrogate.dataset as fs_dataset

    root = _corpus(tmp_path)
    calls = []
    real = fs_dataset.load_manifest_configs

    def _counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(fs_dataset, "load_manifest_configs", _counting)
    corpus = FieldCorpus(root)
    corpus.config_ids()
    corpus.global_params("s35_f085_p30")
    corpus.steps("s35_f085_p30")
    assert len(calls) == 1, f"expected exactly one manifest parse, got {len(calls)}"


def _pass_corpus(tmp_path: Path) -> Path:
    """3 configs x 5 canonically named empty plotfiles, plus a non-canonical ``plt7`` in ``c0``."""
    root = tmp_path / "corpus"
    names = ["c0", "c1", "c2"]
    (root / "runs").mkdir(parents=True)
    (root / "sweep_manifest.json").write_text(json.dumps(_manifest(names)))
    for name in names:
        for step in (100, 200, 300, 400, 500):
            (root / "runs" / name / f"plt{step:05d}").mkdir(parents=True)
    (root / "runs" / "c0" / "plt7").mkdir()
    return root


def test_corpus_pass_reads_the_manifest_once(tmp_path, monkeypatch):
    # Anchor (holds since 1146552): a full config_ids() -> steps() -> plotfile() pass parses the
    # manifest once, however many public calls it makes.
    import mosquito_cfd.force_surrogate.dataset as fs_dataset

    corpus = FieldCorpus(_pass_corpus(tmp_path))
    calls = []
    real = fs_dataset.load_manifest_configs

    def _counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(fs_dataset, "load_manifest_configs", _counting)
    pairs = [(c, s) for c in corpus.config_ids() for s in corpus.steps(c)]
    for config_id, step in pairs:
        corpus.plotfile(config_id, step)
    assert len(pairs) == 16
    assert len(calls) == 1, calls


def test_corpus_pass_lists_each_run_directory_once(tmp_path, monkeypatch):
    # #112 item 1: steps() lists each run directory with one os.scandir, and a canonically named
    # plotfile() resolves without listing. plotfile("c0", 7) is the positive control: plt7 is not
    # canonical, so it must list, and the spy must see it.
    root = _pass_corpus(tmp_path)
    corpus = FieldCorpus(root)
    listed: list[str] = []
    real = os.scandir

    def spy(path="."):
        if _under(path, root):
            listed.append(Path(os.fsdecode(os.fspath(path))).name)
        return real(path)

    monkeypatch.setattr(os, "scandir", spy)
    steps = {c: corpus.steps(c) for c in corpus.config_ids()}
    assert listed == ["c0", "c1", "c2"], listed
    for config_id, config_steps in steps.items():
        for step in config_steps:
            if step != 7:
                corpus.plotfile(config_id, step)
    assert listed == ["c0", "c1", "c2"], listed
    assert corpus.plotfile("c0", 7) == root / "runs" / "c0" / "plt7"
    assert listed == ["c0", "c1", "c2", "c0"], listed


def test_plotfile_presence_is_reread_and_the_manifest_is_not(tmp_path):
    # Anchor: plotfile presence is never cached, since a run can still be writing; the manifest is.
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == [100]
    (run / "plt00500").mkdir()
    assert corpus.steps("s35_f085_p30") == [100, 500]

    manifest = _manifest(["s35_f085_p30", "added"])
    (root / "sweep_manifest.json").write_text(json.dumps(manifest))
    assert corpus.config_ids() == ["s35_f085_p30"]
    assert FieldCorpus(root).config_ids() == ["s35_f085_p30", "added"]


def test_symlinked_plotfile_directory_counts(tmp_path):
    # Anchor: DirEntry.is_dir() follows symlinks, as Path.is_dir() did. plt300 is non-canonical, so
    # steps() AND plotfile() both go through the listing.
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    target = tmp_path / "elsewhere"
    target.mkdir()
    _symlink_or_skip(target, run / "plt300")
    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == [100, 300]
    assert corpus.plotfile("s35_f085_p30", 300) == run / "plt300"


_ARABIC_INDIC_100 = "plt١٠٠"  # int("١٠٠") == 100


def test_only_ascii_digit_whole_name_plotfiles_count(tmp_path, monkeypatch):
    # #145: `\d` matched any Unicode decimal digit, and `$` matches before a trailing newline, so
    # both names below parsed as step 100 and, beside plt00100, made steps() raise "ambiguous".
    # AMReX writes neither name.
    root, run = _bare_corpus(tmp_path / "alone", [_ARABIC_INDIC_100])
    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == []
    with pytest.raises(ValueError, match="no plotfile for step 100"):
        corpus.plotfile("s35_f085_p30", 100)

    root, run = _bare_corpus(tmp_path / "beside", [_ARABIC_INDIC_100, "plt00100"])
    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == [100]
    assert corpus.plotfile("s35_f085_p30", 100) == run / "plt00100"

    # Simulated, so it runs on Windows too, which forbids a newline in a name.
    root, run = _bare_corpus(tmp_path / "stubs", ["plt00100"])
    stubs = [_StubEntry(run, _ARABIC_INDIC_100), _StubEntry(run, "plt100\n")]
    calls = _fake_scandir(monkeypatch, root, extra=stubs)
    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == [100]
    assert corpus.plotfile("s35_f085_p30", 100) == run / "plt00100"
    assert calls == ["s35_f085_p30"]


class _SymlinkToDirEntry(_StubEntry):
    """A symlink to a directory: a directory only when the type check follows symlinks."""

    def is_dir(self, *, follow_symlinks=True):
        return follow_symlinks


def test_listing_follows_symlinks_on_every_os(tmp_path, monkeypatch):
    # The symlink anchor above skips where os.symlink needs a privilege (Windows without
    # developer mode), so this stub carries the follow-symlinks contract on every OS: it is a
    # directory only if the scan asks DirEntry.is_dir() to follow it.
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    calls = _fake_scandir(monkeypatch, root, extra=[_SymlinkToDirEntry(run, "plt300")])
    assert FieldCorpus(root).steps("s35_f085_p30") == [100, 300]
    assert calls == ["s35_f085_p30"]


def test_listing_costs_one_scandir_and_no_per_entry_stat(tmp_path, monkeypatch):
    # #112 item 1: Path.iterdir() + Path.is_dir() cost one os.stat per plt-named entry, an NFS
    # round trip each. A DirEntry carries its type, so the stat count must not grow with the
    # number of entries. One scandir per call is the positive control that the spy fires.
    root = tmp_path / "corpus"
    (root / "runs").mkdir(parents=True)
    (root / "sweep_manifest.json").write_text(json.dumps(_manifest(["small", "large"])))
    sizes = {"small": 3, "large": 30}
    for name, count in sizes.items():
        run = root / "runs" / name
        for i in range(count):
            (run / f"plt{(i + 1) * 10:05d}").mkdir(parents=True)
        (run / "plt99999").write_text("a file named like a plotfile")
    corpus = FieldCorpus(root)
    corpus.config_ids()

    calls: list[str] = []
    for name in ("scandir", "stat"):

        def spy(path=".", *args, _real=getattr(os, name), _name=name, **kwargs):
            if _under(path, root):
                calls.append(_name)
            return _real(path, *args, **kwargs)

        monkeypatch.setattr(os, name, spy)

    counts = {}
    for name, count in sizes.items():
        calls.clear()
        assert len(corpus.steps(name)) == count
        counts[name] = (calls.count("scandir"), calls.count("stat"))
    assert counts["small"][0] == counts["large"][0] == 1, counts
    # Positive control for the stat spy: run_dir()'s is_dir() must register, or an equal count
    # would be 0 == 0 (e.g. on a Python whose Path.is_dir() no longer calls os.stat).
    assert counts["small"][1] >= 1, counts
    assert counts["small"][1] == counts["large"][1], counts


def _winerror(code: int) -> OSError:
    exc = OSError(f"simulated winerror {code}")
    exc.winerror = code  # set by hand, so the case runs on every OS
    return exc


#: The type-check failures Python 3.11's Path.is_dir() treated as "not a directory"
#: (pathlib._IGNORED_ERRNOS, _IGNORED_WINERRORS, and ValueError). Written out, not imported:
#: the test must not trust the list the code uses.
_SKIPPED_ERRORS = [
    pytest.param(FileNotFoundError(errno.ENOENT, "gone"), id="ENOENT"),
    pytest.param(NotADirectoryError(errno.ENOTDIR, "through a file"), id="ENOTDIR"),
    pytest.param(OSError(errno.EBADF, "bad descriptor"), id="EBADF"),
    pytest.param(OSError(errno.ELOOP, "symlink loop"), id="ELOOP"),
    pytest.param(_winerror(21), id="winerror21_not_ready"),
    pytest.param(_winerror(123), id="winerror123_invalid_name"),
    pytest.param(_winerror(1921), id="winerror1921_cant_resolve"),
    pytest.param(ValueError("non-encodable"), id="ValueError"),
]


@pytest.mark.parametrize("error", _SKIPPED_ERRORS)
def test_an_entry_path_is_dir_would_skip_is_still_skipped(error, tmp_path, monkeypatch):
    # os.scandir's DirEntry.is_dir() swallows only FileNotFoundError; Path.is_dir() also
    # treated a symlink loop, a symlink through a file and the rest of this list as "not a
    # directory". The listing keeps that verdict, so one broken link cannot take down a
    # config's whole step list.
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    calls = _fake_scandir(monkeypatch, root, extra=[_StubEntry(run, "plt00200", error)])
    assert FieldCorpus(root).steps("s35_f085_p30") == [100]
    assert calls == ["s35_f085_p30"]


@pytest.mark.parametrize(
    "error",
    [
        # The errno must be set: the code decides by errno, and an errno-less PermissionError
        # would pass even with EACCES wrongly added to the skip list.
        pytest.param(PermissionError(errno.EACCES, "simulated EACCES"), id="EACCES"),
        pytest.param(OSError(errno.EIO, "simulated EIO"), id="EIO"),
    ],
)
def test_failing_entry_type_check_propagates_unless_path_is_dir_ignored_it(
    error, tmp_path, monkeypatch
):
    # Any other OSError from the type check propagates, as it did from Path.is_dir(), rather
    # than hiding a damaged filesystem as a missing step.
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    calls = _fake_scandir(monkeypatch, root, extra=[_StubEntry(run, "plt00200", error)])
    with pytest.raises(type(error), match="simulated"):
        FieldCorpus(root).steps("s35_f085_p30")
    assert calls == ["s35_f085_p30"]


def test_a_dangling_symlink_is_skipped(tmp_path):
    # Real filesystem: DirEntry.is_dir() returns False for a target that does not exist.
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    _symlink_or_skip(tmp_path / "gone", run / "plt00200")
    assert FieldCorpus(root).steps("s35_f085_p30") == [100]


def test_a_symlink_loop_and_a_symlink_through_a_file_are_skipped(tmp_path):
    # Real filesystem (Linux CI): the two cases DirEntry.is_dir() raises on (ELOOP, ENOTDIR)
    # but Path.is_dir() skipped.
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    _symlink_or_skip(run / "plt00900", run / "plt00900")
    (tmp_path / "a_file").write_text("not a directory")
    _symlink_or_skip(tmp_path / "a_file" / "sub", run / "plt01100")
    assert FieldCorpus(root).steps("s35_f085_p30") == [100]


def test_scan_closes_the_listing_on_the_duplicate_raise(tmp_path, monkeypatch):
    # The listing must be closed when the duplicate check raises mid-iteration, not left to the
    # garbage collector: an open directory handle is a held resource, on NFS too.
    root, _ = _bare_corpus(tmp_path, ["plt100", "plt00100"])
    corpus = FieldCorpus(root)
    real = os.scandir
    listings: list[_Listing] = []

    class _Closing(_Listing):
        def __init__(self, it):
            super().__init__(it)
            self._real = it

        def close(self):
            super().close()
            self._real.close()

    def spy(path="."):
        it = real(path)
        if _under(path, root):
            it = _Closing(it)
            listings.append(it)
        return it

    monkeypatch.setattr(os, "scandir", spy)
    with pytest.raises(ValueError, match="ambiguous plotfiles"):
        corpus.steps("s35_f085_p30")
    assert [listing.closed for listing in listings] == [1]


def test_steps_sort_numerically_not_lexically(tmp_path, monkeypatch):
    # Task 53. The regex permits any digit width, and plt10 sorts BEFORE plt2 lexically, so with
    # uniform 5-digit padding lexical and numeric order coincide and a dropped sorted() goes
    # unnoticed.
    #
    # The adverse directory order is FORCED rather than assumed. Relying on the filesystem makes
    # the test's teeth platform-dependent: NTFS happens to yield lexical order (which exposes the
    # mutant), but CI is ubuntu-latest, where ext4 readdir is hash-ordered -- if that order came
    # out ascending, `return found` would survive. Pinning the order makes the check
    # deterministic everywhere.
    root = _corpus(tmp_path, steps=(2, 10, 100))
    run = root / "runs" / "s35_f085_p30"
    for padded, bare in ((2, "plt2"), (10, "plt10")):
        (run / f"plt{padded:05d}").rename(run / bare)

    # Order by the STEP NUMBER descending, so the raw listing is [100, 10, 2] -- unambiguously the
    # wrong answer. Ordering by name descending would yield plt2, plt10, plt00100, i.e.
    # [2, 10, 100], which is accidentally correct and lets the mutant survive (this test's first
    # version made exactly that mistake).
    calls = _fake_scandir(monkeypatch, root, order=["plt00100", "plt10", "plt2"])
    assert FieldCorpus(root).steps("s35_f085_p30") == [2, 10, 100]
    assert calls == ["s35_f085_p30"]


# --- harden-field-corpus-requests: step validation, duplicates, the canonical fast path --------


class _IoSpy:
    """Record manifest loads, ``Path.is_dir`` checks and ``os.scandir`` listings.

    Installed AFTER construction: ``FieldCorpus.__init__`` itself calls ``root.is_dir()``, so a spy
    installed before construction would record that call. An ``os.path.isdir`` call would not be
    seen, which is why every zero-call assertion below has a positive control showing the same spy
    DOES see a real lookup. Unlike the other spies it records calls on every path, not only under
    the corpus root: its tests assert exact or zero counts, which that only makes stricter.
    """

    def __init__(self, monkeypatch):
        import mosquito_cfd.force_surrogate.dataset as fs_dataset

        self.calls: list[str] = []
        real_is_dir, real_scandir = Path.is_dir, os.scandir
        real_load = fs_dataset.load_manifest_configs

        def is_dir(path, *args, **kwargs):
            self.calls.append(f"is_dir:{path.name}")
            return real_is_dir(path, *args, **kwargs)

        def scandir(path="."):
            self.calls.append(f"scandir:{Path(os.fsdecode(os.fspath(path))).name}")
            return real_scandir(path)

        def load(*args, **kwargs):
            # _configs imports load_manifest_configs lazily, inside the call, so patching the
            # module attribute is observed.
            self.calls.append("load_manifest")
            return real_load(*args, **kwargs)

        monkeypatch.setattr(Path, "is_dir", is_dir)
        monkeypatch.setattr(os, "scandir", scandir)
        monkeypatch.setattr(fs_dataset, "load_manifest_configs", load)

    def count(self, prefix: str) -> int:
        return sum(1 for c in self.calls if c.startswith(prefix))


def _bare_corpus(tmp_path: Path, plt_names: list[str]) -> tuple[Path, Path]:
    """A one-config corpus whose run directory holds empty ``plt*`` directories.

    ``plotfile()``/``steps()`` never read a plotfile's contents, so empty directories suffice.
    """
    root = tmp_path / "corpus"
    run = root / "runs" / "s35_f085_p30"
    run.mkdir(parents=True)
    (root / "sweep_manifest.json").write_text(json.dumps(_manifest(["s35_f085_p30"])))
    for name in plt_names:
        (run / name).mkdir()
    return root, run


@pytest.mark.parametrize(
    "step",
    [np.int64(100), np.int32(100), np.uint64(100), 0],
    ids=["np_int64", "np_int32", "np_uint64", "zero"],
)
def test_integer_like_steps_resolve(tmp_path, step):
    # Anchor (passes before the step validation): numpy integers -- e.g. a value taken from an
    # array of steps -- and step 0 (plt00000 is written at initialization) stay valid.
    root, run = _bare_corpus(tmp_path, ["plt00000", "plt00100"])
    assert (
        FieldCorpus(root).plotfile("s35_f085_p30", step) == run / f"plt{int(step):05d}"
    )


_BAD_STEPS = ["100", 100.0, True, np.bool_(True), -1, np.int64(-1), None]


def _shown(step):
    # numpy scalars are shown as their plain Python value, as in the halo and box_margin
    # messages -- never numpy 2's "np.int64(-1)" repr. Written out rather than imported from
    # mosquito_cfd._messages, so the test does not trust the code it checks.
    return repr(step.item() if isinstance(step, np.generic) else step)


@pytest.mark.parametrize("accessor", ["plotfile", "snapshot"])
@pytest.mark.parametrize(
    "step", _BAD_STEPS, ids=[f"{type(s).__name__}:{_shown(s)}" for s in _BAD_STEPS]
)
def test_invalid_step_is_rejected_before_any_io(tmp_path, monkeypatch, accessor, step):
    # "100" used to fail with "no plotfile for step 100 ... available steps: [100]"; 100.0 and
    # True resolved plt00100; -1 scanned the run directory. All are caller bugs, reported as a bad
    # step before the manifest is read or the run directory is touched
    # (harden-field-corpus-requests D4). A fresh instance per case: once the manifest is cached a
    # validate-after-_config mutant would also record no manifest load.
    root, _ = _bare_corpus(tmp_path, ["plt00100"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)

    with pytest.raises(
        ValueError,
        match=r"step must be a non-negative integer, got "
        + re.escape(_shown(step))
        + "$",
    ):
        getattr(corpus, accessor)("s35_f085_p30", step)
    assert spy.calls == []


def test_io_spy_sees_a_real_plotfile_lookup(tmp_path, monkeypatch):
    # Positive control for the zero-call assertion above.
    root, _ = _bare_corpus(tmp_path, ["plt00100"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    corpus.plotfile("s35_f085_p30", 100)
    assert spy.count("load_manifest") == 1
    assert spy.count("is_dir:") >= 1


def test_duplicate_step_directories_raise(tmp_path, monkeypatch):
    # plt100 and plt00100 both parse to step 100. steps() used to return [100, 100, 200] and
    # plotfile() returned whichever directory the filesystem listed first. Every operation that
    # lists the run directory now raises, naming both directories in SORTED order -- the listing is
    # forced to put plt100 first, so a message built in listing order fails
    # (harden-field-corpus-requests D5). plt200 is non-canonical, so plotfile(c, 200) cannot take
    # the canonical fast path and must scan.
    root, _ = _bare_corpus(tmp_path, ["plt100", "plt00100", "plt200"])
    calls = _fake_scandir(monkeypatch, root, order=["plt100", "plt200", "plt00100"])
    corpus = FieldCorpus(root)
    expected = r"two plotfile directories parse to step 100: plt00100, plt100$"

    with pytest.raises(ValueError, match=expected):
        corpus.steps("s35_f085_p30")
    with pytest.raises(ValueError, match=expected):
        corpus.plotfile("s35_f085_p30", 200)
    assert calls == ["s35_f085_p30", "s35_f085_p30"]


def test_non_directory_entries_never_duplicate_or_resolve(tmp_path, monkeypatch):
    # A regular FILE with a plotfile name is ignored both by the duplicate check (it runs after
    # the is_dir filter) and by plotfile() (a file named plt00100 is not a canonical hit). The
    # directory is forced to list BEFORE the same-step file: a duplicate check placed ahead of the
    # is_dir filter only fires in that order.
    calls = _fake_scandir(monkeypatch, tmp_path, order=["plt00100", "plt100"])
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    (run / "plt100").write_text("not a plotfile")
    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == [100]
    assert corpus.plotfile("s35_f085_p30", 100) == run / "plt00100"

    root2, run2 = _bare_corpus(tmp_path / "second", ["plt100"])
    (run2 / "plt00100").write_text("not a plotfile")
    corpus2 = FieldCorpus(root2)
    assert corpus2.steps("s35_f085_p30") == [100]
    assert corpus2.plotfile("s35_f085_p30", 100) == run2 / "plt100"
    # steps() on each corpus, plus the second plotfile() call's fallback scan.
    assert calls == ["s35_f085_p30"] * 3


def test_missing_step_lists_the_run_directory_once(tmp_path, monkeypatch):
    # The miss path used to list the run directory, then call steps(), which re-ran the manifest
    # lookup, the run-directory stat and a second listing. It now reports the available steps
    # from the one scan it already did.
    root, _ = _bare_corpus(tmp_path, ["plt7"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    with pytest.raises(ValueError, match=r"available steps: \[7\]$"):
        corpus.plotfile("s35_f085_p30", 8)
    assert spy.count("scandir:") == 1, spy.calls


def test_noncanonical_step_resolves_with_one_listing(tmp_path, monkeypatch):
    # Anchor (passes before the change): a step present only under a non-canonical name is found
    # by the scan, which lists the run directory exactly once.
    root, run = _bare_corpus(tmp_path, ["plt7"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    assert corpus.plotfile("s35_f085_p30", 7) == run / "plt7"
    assert spy.count("scandir:") == 1, spy.calls


def test_canonical_plotfile_resolves_without_listing(tmp_path, monkeypatch):
    # AMReX names plotfiles plt{step:05d} (at least five digits, so plt100000 for step 100000).
    # That name is tried with one is_dir() before any listing of the run directory -- on cluster
    # NFS each per-entry stat of a listing is a round trip (harden-field-corpus-requests D2). Step
    # 100 kills a `:05d` -> `:d` mutant (plt100 does not exist here).
    root, run = _bare_corpus(tmp_path, ["plt00100", "plt100000", "plt7"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    assert corpus.plotfile("s35_f085_p30", 100) == run / "plt00100"
    assert corpus.plotfile("s35_f085_p30", 100000) == run / "plt100000"
    assert spy.count("scandir:") == 0, spy.calls
    assert spy.calls.count("is_dir:plt00100") == 1, spy.calls
    # Positive control: the same spy sees the one listing a non-canonical name needs.
    assert corpus.plotfile("s35_f085_p30", 7) == run / "plt7"
    assert spy.count("scandir:") == 1, spy.calls


def test_unknown_config_is_rejected_before_the_fast_path(tmp_path):
    # Anchor: a canonical-looking directory on disk for a config the manifest does not list must
    # not be served -- manifest membership is checked first, on both paths.
    root, _ = _bare_corpus(tmp_path, ["plt00100"])
    (root / "runs" / "ghost" / "plt00100").mkdir(parents=True)
    with pytest.raises(ValueError, match=r"config 'ghost' is not in manifest"):
        FieldCorpus(root).plotfile("ghost", 100)


def test_fast_path_does_not_see_a_noncanonical_twin(tmp_path):
    # The documented trade-off (harden-field-corpus-requests D2), pinned so changing it is a
    # deliberate decision: a fast-path hit never lists the run directory, so it cannot see that
    # plt100 duplicates plt00100. Only the listing operations report the ambiguity.
    root, run = _bare_corpus(tmp_path, ["plt100", "plt00100"])
    corpus = FieldCorpus(root)
    assert corpus.plotfile("s35_f085_p30", 100) == run / "plt00100"
    with pytest.raises(ValueError, match=r"two plotfile directories parse to step 100"):
        corpus.steps("s35_f085_p30")


def test_missing_run_directory_is_self_describing_after_a_fast_path_miss(tmp_path):
    # The fast path's canonical is_dir() is False when the whole run directory is absent; the
    # fallback must still report the missing run directory, not a "no plotfile" or OS error.
    root = tmp_path / "corpus"
    (root / "runs").mkdir(parents=True)
    (root / "sweep_manifest.json").write_text(json.dumps(_manifest(["s35_f085_p30"])))
    with pytest.raises(ValueError, match=r"no run directory for config 's35_f085_p30'"):
        FieldCorpus(root).plotfile("s35_f085_p30", 100)


# --- harden-field-reader-pre-f3 §4: digest-pinned run provenance (#113) -----------------------

_COMMIT = "5d5f1ad49da19f9aeafeeaf86e535d04ef28d6c5"
_DIGEST = "92817878fead23f9c6b8219706a2ebcec7cccf2158db8016e867e0227ca68a47"
_IMAGE = f"ghcr.io/talmolab/mosquito-cfd@sha256:{_DIGEST}"
_CFG = "s35_f085_p30"
_MISSING = object()


def _pod_metadata(config: str = _CFG) -> dict:
    """The real pod-side ``run_metadata.json`` key set (Z: fine corpus), plus an unknown key."""
    return {
        "run_id": f"{config}-run",
        "timestamp": "2026-09-20T00:00:00Z",
        "git": {"commit": _COMMIT, "source": "docker-image-build-arg"},
        "hardware": {"gpu": "NVIDIA A40"},
        "docker_image": _IMAGE,
        "config": config,
        "deck": f"inputs/inputs.3d.{config}",
        "deck_sha256": "0" * 64,
        "command": "amr3d.gnu.MPI.CUDA.ex inputs",
        "ib_particle_csv": "IB_Particle_1.csv",
        "log": "run.log",
        "rows": 1000,
        "max_step": 4706,
        "threshold": 0.0,
        "status": "completed",
        "orchestration": {"workflow": "wf"},
        "unknown_extra_key": [1, 2, 3],
    }


def _write_run_metadata(
    run_dir: Path, *, raw: bytes | None = None, **overrides
) -> Path:
    """Opt-in: write ``run_metadata.json`` into ``run_dir``. ``_corpus()`` never does."""
    path = run_dir / "run_metadata.json"
    if raw is not None:
        path.write_bytes(raw)
        return path
    meta = _pod_metadata()
    for key, value in overrides.items():
        if value is _MISSING:
            meta.pop(key, None)
        else:
            meta[key] = value
    path.write_text(json.dumps(meta))
    return path


def _prefix(config: str, path: Path) -> str:
    return f"run_metadata for config {config!r} ({path}): "


@pytest.fixture
def yt_tripwire(monkeypatch):
    """Replace ``yt.load``; record whether the reader got as far as loading a plotfile."""
    import yt

    calls: list[str] = []
    real = yt.load

    def load(path, *args, **kwargs):
        calls.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(yt, "load", load)
    return calls


def _bad_metadata_cases():
    run_dir_file = "run_metadata.json"
    commit_key = "git.commit"
    cases = [
        ("absent", None, run_dir_file),
        ("directory", "dir", run_dir_file),
        ("non_utf8", b"\xff\xfe\x00garbage", run_dir_file),
        ("invalid_json", b"{not json", run_dir_file),
        ("top_level_array", b"[1, 2, 3]", run_dir_file),
        ("config_absent", {"config": _MISSING}, "config"),
        ("config_null", {"config": None}, "config"),
        ("config_other", {"config": "s55_f115_p30"}, "config"),
        ("git_absent", {"git": _MISSING}, "git"),
        ("git_null", {"git": None}, "git"),
        ("commit_absent", {"git": {"source": "x"}}, commit_key),
        ("commit_int", {"git": {"commit": 123}}, commit_key),
        ("commit_short", {"git": {"commit": _COMMIT[:7]}}, commit_key),
        ("commit_upper", {"git": {"commit": _COMMIT.upper()}}, commit_key),
        ("commit_newline", {"git": {"commit": _COMMIT + "\n"}}, commit_key),
        ("image_absent", {"docker_image": _MISSING}, "docker_image"),
        ("image_int", {"docker_image": 5}, "docker_image"),
        (
            "image_tag",
            {"docker_image": "ghcr.io/talmolab/mosquito-cfd:latest"},
            "docker_image",
        ),
        ("image_bare_digest", {"docker_image": f"sha256:{_DIGEST}"}, "docker_image"),
        (
            "image_tag_hash",
            {"docker_image": f"repo:latest #sha256:{_DIGEST}"},
            "docker_image",
        ),
        ("image_empty_repo", {"docker_image": f":@sha256:{_DIGEST}"}, "docker_image"),
        (
            "image_upper_repo",
            {"docker_image": f"GHCR.io/x@sha256:{_DIGEST}"},
            "docker_image",
        ),
        ("image_leading_space", {"docker_image": " " + _IMAGE}, "docker_image"),
        ("image_trailing_space", {"docker_image": _IMAGE + " "}, "docker_image"),
        ("image_trailing_newline", {"docker_image": _IMAGE + "\n"}, "docker_image"),
    ]
    return [pytest.param(spec, field, id=case_id) for case_id, spec, field in cases]


def _install_bad_metadata(run_dir: Path, spec) -> Path:
    path = run_dir / "run_metadata.json"
    if spec is None:
        return path
    if spec == "dir":
        path.mkdir()
        return path
    if isinstance(spec, bytes):
        return _write_run_metadata(run_dir, raw=spec)
    return _write_run_metadata(run_dir, **spec)


@pytest.mark.parametrize(("spec", "field"), _bad_metadata_cases())
def test_unverifiable_provenance_is_refused_before_any_read(
    tmp_path, yt_tripwire, spec, field
):
    root = _corpus(tmp_path)
    path = _install_bad_metadata(root / "runs" / _CFG, spec)
    with pytest.raises(ValueError) as excinfo:
        FieldCorpus(root).snapshot(_CFG, 100)
    assert type(excinfo.value) is ValueError
    assert str(excinfo.value).startswith(_prefix(_CFG, path) + f"{field}: "), str(
        excinfo.value
    )
    assert yt_tripwire == []


def test_valid_provenance_reaches_the_read_and_is_carried_verbatim(
    tmp_path, yt_tripwire
):
    from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

    root = _corpus(tmp_path)
    _write_run_metadata(root / "runs" / _CFG)
    corpus = FieldCorpus(root)
    snap = corpus.snapshot(_CFG, np.int64(100))
    assert len(yt_tripwire) == 1  # positive control for the tripwire
    assert snap.config_id == _CFG
    assert type(snap.step) is int and snap.step == 100
    assert snap.git_commit == _COMMIT
    assert snap.docker_image == _IMAGE
    want = read_field_snapshot(
        corpus.plotfile(_CFG, 100), lo=(-np.inf,) * 3, hi=(np.inf,) * 3
    )
    assert list(snap.arrays) == list(want.arrays)
    for name in want.arrays:
        assert snap.arrays[name].tobytes() == want.arrays[name].tobytes(), name
    for attr in ("x", "y", "z", "dx"):
        assert getattr(snap, attr).tobytes() == getattr(want, attr).tobytes(), attr
    for attr in ("time", "max_level", "field_names", "source"):
        assert getattr(snap, attr) == getattr(want, attr), attr


def test_run_metadata_is_read_through_and_fresh(tmp_path):
    root = _corpus(tmp_path)
    path = _write_run_metadata(root / "runs" / _CFG)
    corpus = FieldCorpus(root)
    first = corpus.run_metadata(_CFG)
    assert type(first) is dict
    assert first == json.loads(path.read_text())
    assert first["unknown_extra_key"] == [1, 2, 3]
    first["status"] = "mutated"
    first["git"]["commit"] = "mutated"
    second = corpus.run_metadata(_CFG)
    assert second == json.loads(path.read_text())


def test_run_metadata_absent_names_the_expected_path(tmp_path):
    root = _corpus(tmp_path)
    path = root / "runs" / _CFG / "run_metadata.json"
    with pytest.raises(ValueError) as excinfo:
        FieldCorpus(root).run_metadata(_CFG)
    assert str(excinfo.value).startswith(_prefix(_CFG, path) + "run_metadata.json: ")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fields": "u"},
        {"fields": ("nope",)},
        {"lo": (4.0, 4.0, 4.0), "hi": (2.0, 2.0, 2.0)},
        {"halo": -1},
    ],
    ids=["bare_string_field", "unknown_field", "inverted", "neg_halo"],
)
def test_argument_errors_win_over_provenance_with_no_io(tmp_path, monkeypatch, kwargs):
    # No run_metadata.json on disk: a provenance-first mutant would report that instead.
    root, _ = _bare_corpus(tmp_path, ["plt00100"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    with pytest.raises(ValueError) as excinfo:
        corpus.snapshot(_CFG, 100, **kwargs)
    assert "run_metadata" not in str(excinfo.value)
    assert spy.calls == []


def test_config_and_step_errors_win_over_provenance(tmp_path):
    corpus = FieldCorpus(_corpus(tmp_path))  # no run_metadata.json anywhere
    with pytest.raises(ValueError, match="is not in manifest") as excinfo:
        corpus.snapshot("nope", 100)
    assert "run_metadata" not in str(excinfo.value)
    with pytest.raises(ValueError, match="no plotfile for step 999") as excinfo:
        corpus.snapshot(_CFG, 999)
    assert "run_metadata" not in str(excinfo.value)


_PROVENANCE_PROBE = """
import json, sys
from pathlib import Path
from mosquito_cfd.field_surrogate import _provenance
path = Path(sys.argv[1])
meta = _provenance.read_run_metadata(path, config_id=sys.argv[2])
_provenance.run_provenance(meta, config_id=sys.argv[2], path=path)
heavy = [m for m in ("mosquito_cfd.force_surrogate", "pandas", "matplotlib.pyplot")
         if m in sys.modules]
print(json.dumps(heavy))
"""


def test_reading_provenance_loads_no_force_surrogate_stack(tmp_path):
    import subprocess

    root = _corpus(tmp_path)
    path = _write_run_metadata(root / "runs" / _CFG)
    result = subprocess.run(
        [sys.executable, "-c", _PROVENANCE_PROBE, str(path), _CFG],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_provenance_module_imports_only_the_standard_library():
    import ast

    import mosquito_cfd.field_surrogate as pkg

    source = (Path(pkg.__file__).parent / "_provenance.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, (
                f"relative import: from {'.' * node.level}{node.module}"
            )
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        for name in names:
            assert name.split(".")[0] in sys.stdlib_module_names, name


# --- harden-field-reader-pre-f3 §5: zero-cell refusal at the corpus entry point ---------------

_ZERO_CELL = {
    "beyond_domain_by_more_than_halo": (
        {"lo": (10.0, 0.0, 0.0), "hi": (11.0, 6.0, 6.0), "halo": 1},
        "(0, 6, 6)",
    ),
    "point_on_upper_edge": (
        {"lo": (6.0, 3.0, 3.0), "hi": (6.0, 3.0, 3.0)},
        "(0, 1, 1)",
    ),
}


@pytest.mark.parametrize("case", sorted(_ZERO_CELL))
def test_corpus_snapshot_refuses_a_zero_cell_region(tmp_path, case):
    region, counts = _ZERO_CELL[case]
    root = _corpus(tmp_path)
    _write_run_metadata(root / "runs" / _CFG)
    with pytest.raises(ValueError) as excinfo:
        FieldCorpus(root).snapshot(_CFG, 100, **region)
    message = str(excinfo.value)
    assert f"config {_CFG!r}" in message
    assert "step=100" in message
    assert f"lo={tuple(float(v) for v in region['lo'])}" in message
    assert f"hi={tuple(float(v) for v in region['hi'])}" in message
    assert f"halo={region.get('halo', 0)}" in message
    assert counts in message


def test_corpus_snapshot_accepts_one_cell_and_zero_column_requests(tmp_path):
    root = _corpus(tmp_path)
    _write_run_metadata(root / "runs" / _CFG)
    corpus = FieldCorpus(root)
    one = corpus.snapshot(_CFG, 100, lo=(2.5, 2.5, 2.5), hi=(2.5, 2.5, 2.5))
    assert one.arrays["u"].shape == (1, 1, 1)
    # Cells but no columns: the guard is on the axes, not on values.size.
    no_columns = corpus.snapshot(_CFG, 100, fields=())
    assert (no_columns.x.size, no_columns.y.size, no_columns.z.size) == (6, 6, 6)
    assert no_columns.field_names == ()


# --- harden-field-reader-pre-f3 §10.1 (design D8.1) -------------------------------------------


@pytest.mark.parametrize(
    "make_fields",
    [lambda: (f for f in ("u", "v")), lambda: iter(["u", "v"])],
    ids=["generator", "iterator"],
)
def test_iterator_fields_are_read_not_consumed_by_validation(tmp_path, make_fields):
    root = _corpus(tmp_path)
    _write_run_metadata(root / "runs" / _CFG)
    snap = FieldCorpus(root).snapshot(_CFG, 100, fields=make_fields())
    assert snap.field_names == ("u", "v")
    assert list(snap.arrays) == ["u", "v"]


def test_headerless_plotfile_error_wins_over_provenance(tmp_path):
    root = _corpus(tmp_path)  # no run_metadata.json
    plt = root / "runs" / _CFG / "plt00100"
    (plt / "Header").unlink()
    with pytest.raises(FileNotFoundError, match="Header") as excinfo:
        FieldCorpus(root).snapshot(_CFG, 100)
    assert "run_metadata" not in str(excinfo.value)
