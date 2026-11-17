"""Tests for the field cache and its provenance checks (plan Task 2). No network drive needed."""

import shutil

import numpy as np
import pytest

from experiments.common.data import CORPUS_DIR
from experiments.field import cache
from experiments.field.provenance import ProvenanceError, check_plotfile
from mosquito_cfd.field_surrogate.corpus import FieldCorpus

HEADER = "NavierStokes-V1.1\n8\n" + "\n".join(
    ["x_velocity", "y_velocity", "z_velocity", "density", "tracer", "gradpx", "gradpy", "gradpz"]
) + "\n3\n{time}\n0\n0 0 0 \n8 4 8 \n"
JOB_INFO = (
    "IAMR   git hash: v1.0-30-gf93dc794\namr.n_cell = 256 128 256\nmax_step = 4000\n"
    "ns.cfl = {cfl}\nns.do_diffused_ib = 1\nns.fixed_dt = 0.0005\n"
)


def _plt(tmp_path, *, cfl="0.6", time="0.999999999999945", name="plt02000"):
    d = tmp_path / name
    d.mkdir()
    (d / "Header").write_text(HEADER.format(time=time))
    (d / "job_info").write_text(JOB_INFO.format(cfl=cfl))
    return d


def test_provenance_accepts_live(tmp_path):
    check_plotfile(_plt(tmp_path), 2000)


def test_provenance_rejects_cfl_03(tmp_path):
    with pytest.raises(ProvenanceError, match="ns.cfl"):
        check_plotfile(_plt(tmp_path, cfl="0.3"), 2000)


def test_provenance_rejects_wrong_time(tmp_path):
    with pytest.raises(ProvenanceError, match="time"):
        check_plotfile(_plt(tmp_path, time="0.83"), 2000)


def test_provenance_rejects_missing_job_info(tmp_path):
    d = _plt(tmp_path)
    (d / "job_info").unlink()
    with pytest.raises(ProvenanceError):
        check_plotfile(d, 2000)


def test_old_dirs_not_listed(tmp_path):
    shutil.copy(CORPUS_DIR["fine"] / "sweep_manifest.json", tmp_path / "sweep_manifest.json")
    run = tmp_path / "runs" / "s45_f100_p45"
    for name in ("plt00100", "plt00100.old.1513210", "plt00200", "chk00000"):
        (run / name).mkdir(parents=True)
    assert FieldCorpus(tmp_path).steps("s45_f100_p45") == [100, 200]


def test_block_mean_downsample():
    a = np.arange(8 * 4 * 8, dtype=float).reshape(8, 4, 8)
    out = cache.block_mean(a, 4)
    assert out.shape == (2, 1, 2)
    assert out[0, 0, 0] == a[:4, :4, :4].mean() and out[1, 0, 1] == a[4:, :, 4:].mean()


def test_patch_slice_selects_cells_inside_box():
    x = (np.arange(256) + 0.5) * 0.03125
    sl = cache.axis_slice(x, 1.0, 7.0)
    assert (sl.start, sl.stop) == (32, 224)
    z = (np.arange(256) + 0.5) * 0.03125
    assert (cache.axis_slice(z, 2.5, 5.5).start, cache.axis_slice(z, 2.5, 5.5).stop) == (80, 176)


def test_phase_and_beat_at_boundaries():
    assert cache.phase_and_beat(0.999999999999945, 1.0) == (0.0, 1)
    ph, beat = cache.phase_and_beat(1.5 / 0.85, 0.85)
    assert beat == 1 and abs(ph - 0.5) < 1e-9
    assert cache.phase_and_beat(0.25, 1.0) == (0.25, 0)


def test_cache_is_atomic_and_resumable(tmp_path):
    arrays = {"patch_u": np.ones((2, 2, 2, 3), np.float32), "time": np.float64(0.05)}
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "00200.tmp.npz").write_bytes(b"half written")
    assert not cache.is_cached(tmp_path, "cfg", 200)
    cache.write_atomic(tmp_path, "cfg", 100, arrays)
    cache.write_atomic(tmp_path, "cfg", 200, arrays)
    idx = cache.index(tmp_path)
    assert sorted(idx.step) == [100, 200] and set(idx.config) == {"cfg"}
    assert cache.is_cached(tmp_path, "cfg", 200)
    assert cache.load(tmp_path, "cfg", 200)["patch_u"].dtype == np.float32


def test_markers_rotate_about_hinge():
    body = np.array([[0.0, -1.475, 0.0], [0.5, 1.475, 0.0], [-0.5, 0.0, 0.0]])
    kw = dict(body=body, center=(4.0, 2.0, 4.0), hinge=(4.0, 0.5, 4.0), frequency=1.0, stroke_amp_deg=45.0, pitch_amp_deg=0.0)
    rest = cache.wing_markers(time=0.5, **kw)  # phi = 0, alpha = pitch_amp*cos(pi) = 0 with pitch_amp 0
    assert np.allclose(rest, body + np.array([4.0, 2.0, 4.0]))
    moved = cache.wing_markers(time=0.25, **kw)  # phi = +45 deg about z through the hinge
    h = np.array([4.0, 0.5, 4.0])
    assert np.allclose(np.linalg.norm(moved - h, axis=1), np.linalg.norm(rest - h, axis=1))
    assert np.allclose(moved[:, 2], rest[:, 2]) and not np.allclose(moved, rest)
