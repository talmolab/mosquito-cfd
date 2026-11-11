"""Tests for mosquito_cfd.field_surrogate.corpus (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import json
import re
import shutil
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


def test_resolves_a_snapshot_by_config_and_step(tmp_path):
    corpus = FieldCorpus(_corpus(tmp_path))

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

    real_iterdir = Path.iterdir

    def reverse_numeric_iterdir(self):
        # Order by the STEP NUMBER descending, so the raw listing is [100, 10, 2] -- unambiguously
        # the wrong answer. Ordering by name descending would yield plt2, plt10, plt00100, i.e.
        # [2, 10, 100], which is accidentally correct and lets the mutant survive (this test's
        # first version made exactly that mistake).
        def step_of(q):
            digits = q.name[3:]
            return int(digits) if q.name.startswith("plt") and digits.isdigit() else -1

        return iter(sorted(real_iterdir(self), key=step_of, reverse=True))

    monkeypatch.setattr(Path, "iterdir", reverse_numeric_iterdir)
    assert FieldCorpus(root).steps("s35_f085_p30") == [2, 10, 100]


# --- harden-field-corpus-requests: step validation, duplicates, the canonical fast path --------


class _IoSpy:
    """Record manifest loads and ``Path`` directory checks/listings, installed AFTER construction.

    ``FieldCorpus.__init__`` itself calls ``root.is_dir()``, so a spy installed before
    construction would record that call. Only the ``Path`` API is covered: an ``os.path.isdir`` or
    ``os.scandir`` call would not be seen, which is why every zero-call assertion below has a
    positive control showing the same spy DOES see a real lookup.
    """

    def __init__(self, monkeypatch):
        import mosquito_cfd.force_surrogate.dataset as fs_dataset

        self.calls: list[str] = []
        real_is_dir, real_iterdir = Path.is_dir, Path.iterdir
        real_load = fs_dataset.load_manifest_configs

        def is_dir(path, *args, **kwargs):
            self.calls.append(f"is_dir:{path.name}")
            return real_is_dir(path, *args, **kwargs)

        def iterdir(path):
            self.calls.append(f"iterdir:{path.name}")
            return real_iterdir(path)

        def load(*args, **kwargs):
            # _configs imports load_manifest_configs lazily, inside the call, so patching the
            # module attribute is observed.
            self.calls.append("load_manifest")
            return real_load(*args, **kwargs)

        monkeypatch.setattr(Path, "is_dir", is_dir)
        monkeypatch.setattr(Path, "iterdir", iterdir)
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


_BAD_STEPS = ["100", 100.0, True, np.bool_(True), -1, None]


@pytest.mark.parametrize("accessor", ["plotfile", "snapshot"])
@pytest.mark.parametrize("step", _BAD_STEPS, ids=[repr(s) for s in _BAD_STEPS])
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
        match=r"step must be a non-negative integer, got " + re.escape(repr(step)),
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


def _listing_order(monkeypatch, names_first: list[str]) -> None:
    """Force ``Path.iterdir`` to yield ``names_first`` (in that order) before anything else.

    NTFS already lists names sorted and ext4 lists them hash-ordered, so a check that depends on
    the order it sees must be pinned to an adverse one, not left to the filesystem.
    """
    real_iterdir = Path.iterdir

    def ordered(path):
        entries = list(real_iterdir(path))
        rank = {name: i for i, name in enumerate(names_first)}
        return iter(sorted(entries, key=lambda q: rank.get(q.name, len(rank))))

    monkeypatch.setattr(Path, "iterdir", ordered)


def test_duplicate_step_directories_raise(tmp_path, monkeypatch):
    # plt100 and plt00100 both parse to step 100. steps() used to return [100, 100, 200] and
    # plotfile() returned whichever directory the filesystem listed first. Every operation that
    # lists the run directory now raises, naming both directories in SORTED order -- the listing is
    # forced to put plt100 first, so a message built in listing order fails
    # (harden-field-corpus-requests D5). plt200 is non-canonical, so plotfile(c, 200) cannot take
    # the canonical fast path and must scan.
    root, _ = _bare_corpus(tmp_path, ["plt100", "plt00100", "plt200"])
    _listing_order(monkeypatch, ["plt100", "plt200", "plt00100"])
    corpus = FieldCorpus(root)
    expected = r"two plotfile directories parse to step 100: plt00100, plt100$"

    with pytest.raises(ValueError, match=expected):
        corpus.steps("s35_f085_p30")
    with pytest.raises(ValueError, match=expected):
        corpus.plotfile("s35_f085_p30", 200)


def test_non_directory_entries_never_duplicate_or_resolve(tmp_path, monkeypatch):
    # A regular FILE with a plotfile name is ignored both by the duplicate check (it runs after
    # the is_dir filter) and by plotfile() (a file named plt00100 is not a canonical hit). The
    # directory is forced to list BEFORE the same-step file: a duplicate check placed ahead of the
    # is_dir filter only fires in that order.
    _listing_order(monkeypatch, ["plt00100", "plt100"])
    root, run = _bare_corpus(tmp_path, ["plt00100"])
    (run / "plt100").write_text("not a plotfile")
    assert FieldCorpus(root).steps("s35_f085_p30") == [100]

    root2, run2 = _bare_corpus(tmp_path / "second", ["plt100"])
    (run2 / "plt00100").write_text("not a plotfile")
    corpus2 = FieldCorpus(root2)
    assert corpus2.steps("s35_f085_p30") == [100]
    assert corpus2.plotfile("s35_f085_p30", 100) == run2 / "plt100"


def test_missing_step_lists_the_run_directory_once(tmp_path, monkeypatch):
    # The miss path used to list the run directory, then call steps(), which re-ran the manifest
    # lookup, the run-directory stat and a second listing. It now reports the available steps
    # from the one scan it already did.
    root, _ = _bare_corpus(tmp_path, ["plt7"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    with pytest.raises(ValueError, match=r"available steps: \[7\]$"):
        corpus.plotfile("s35_f085_p30", 8)
    assert spy.count("iterdir:") == 1, spy.calls


def test_noncanonical_step_resolves_with_one_listing(tmp_path, monkeypatch):
    # Anchor (passes before the change): a step present only under a non-canonical name is found
    # by the scan, which lists the run directory exactly once.
    root, run = _bare_corpus(tmp_path, ["plt7"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    assert corpus.plotfile("s35_f085_p30", 7) == run / "plt7"
    assert spy.count("iterdir:") == 1, spy.calls


def test_canonical_plotfile_resolves_without_listing(tmp_path, monkeypatch):
    # AMReX names plotfiles plt{step:05d} (at least five digits, so plt100000 for step 100000).
    # That name is tried with one is_dir() before any listing of the run directory -- on cluster
    # NFS each per-entry stat of a listing is a round trip (harden-field-corpus-requests D2). Step
    # 100 kills a `:05d` -> `:d` mutant (plt100 does not exist here).
    root, run = _bare_corpus(tmp_path, ["plt00100", "plt100000"])
    corpus = FieldCorpus(root)
    spy = _IoSpy(monkeypatch)
    assert corpus.plotfile("s35_f085_p30", 100) == run / "plt00100"
    assert corpus.plotfile("s35_f085_p30", 100000) == run / "plt100000"
    assert spy.count("iterdir:") == 0, spy.calls
    assert spy.calls.count("is_dir:plt00100") == 1, spy.calls


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
