"""Scale-invariance guard for the van Veen re-normalization (CPU-only, cluster-free).

Re-deriving the corpus coefficients under a different per-config convention multiplies
BOTH the CFD target and the surrogate prediction by the same constant
``k = f_ref_old / f_ref_new``. R^2 is invariant under that common rescale (RMSE/MAE
scale by ``k``), so the held-out skill is unchanged and no retrain is needed. This pins
that property on the committed ``holdout_predictions.parquet`` (proves Track-B re-deriva-
tion is safe). See openspec/changes/standardize-force-normalization (Task B / scenario
"R^2 is invariant under re-normalization").
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import (
    compute_force_coefficients,
    compute_force_reference,
)
from mosquito_cfd.force_surrogate.constants import (
    CHORD,
    R_GYRATION,
    R_TIP,
    RHO,
    SPAN,
)
from mosquito_cfd.force_surrogate.train import _r2

_PRED = Path("examples/prelim_sweep/surrogate/holdout_predictions.parquet")

# Convention factor k = f_ref_old / f_ref_new = (R_TIP / R_GYRATION)^2 ~= 3.119.
# Both references come from the single-source helper (old = tip arm, new = gyration arm).
_F_REF_OLD = compute_force_reference(1.0, 70.0, R_TIP, SPAN, CHORD, RHO).f_ref
_F_REF_NEW = compute_force_reference(1.0, 70.0, R_GYRATION, SPAN, CHORD, RHO).f_ref
_K = _F_REF_OLD / _F_REF_NEW


def test_convention_factor_is_geometry_ratio():
    """k = f_ref_old/f_ref_new equals (R_TIP/R_GYRATION)^2 ~= 3.119."""
    assert _K == pytest.approx((R_TIP / R_GYRATION) ** 2, rel=1e-12)
    assert _K == pytest.approx(3.119, rel=1e-3)


@pytest.mark.parametrize("coef", ["CF_x", "CF_z"])
def test_r2_invariant_under_renormalization(coef):
    """Scaling true and pred by the same k leaves R^2 unchanged; RMSE scales by k."""
    df = pd.read_parquet(_PRED)
    y = df[f"{coef}_true"].to_numpy(dtype=float)
    yhat = df[f"{coef}_pred"].to_numpy(dtype=float)

    r2_before = _r2(y, yhat)
    r2_after = _r2(y * _K, yhat * _K)
    assert r2_after == pytest.approx(r2_before, abs=1e-9)

    rmse_before = float(np.sqrt(np.mean((y - yhat) ** 2)))
    rmse_after = float(np.sqrt(np.mean((y * _K - yhat * _K) ** 2)))
    assert rmse_after == pytest.approx(_K * rmse_before, rel=1e-9)


@pytest.mark.parametrize("coef", ["CF_x", "CF_z"])
def test_unscaled_r2_matches_committed_metrics(coef):
    """The committed predictions reproduce metrics.json R^2 (the baseline being preserved)."""
    import json

    df = pd.read_parquet(_PRED)
    metrics = json.loads(
        (Path("examples/prelim_sweep/surrogate/metrics.json")).read_text()
    )
    y = df[f"{coef}_true"].to_numpy(dtype=float)
    yhat = df[f"{coef}_pred"].to_numpy(dtype=float)
    assert _r2(y, yhat) == pytest.approx(metrics["per_target"][coef]["r2"], abs=1e-9)


# Pinned SHA256 of the committed raw force/moment columns (Fx..Mz). The Track-B
# re-derivation freezes these — a future regeneration that disturbs the raw CFD forces
# (not just the derived CF) would change this digest and fail the test.
# NOTE: `pd.util.hash_pandas_object` is value-based but pandas-major-version coupled. pandas
# is pinned in uv.lock, so this is stable in CI; if pandas is upgraded and this digest trips
# on unchanged data, re-pin it (it is a corpus tripwire, not phantom data corruption).
_FROZEN_RAW_FORCE_SHA = (
    "02b04f46a99655122f402433e4d0c1afb8cd0e5b28c9b85236ed96cbab14486e"
)


def test_committed_corpus_cf_is_van_veen_consistent():
    """Every distinct config's CF_* equals raw force / per-config van Veen f_ref.

    Scenario: Raw corpus stays frozen; only derived coefficients move. Covers ALL distinct
    (stroke, freq) keys (f_ref ∝ stroke², so a stroke-dependent bug must not slip through),
    using a vectorized per-config check.
    """
    import hashlib

    from mosquito_cfd.force_surrogate import compute_moment_reference

    df = pd.read_parquet("examples/prelim_sweep/dataset.parquet")
    keys = df.drop_duplicates(["stroke_amp_deg", "frequency_fstar"])[
        ["stroke_amp_deg", "frequency_fstar"]
    ]
    assert len(keys) == 9  # the full 3x3 (stroke x freq) grid
    for stroke, freq in keys.itertuples(index=False):
        sub = df[(df["stroke_amp_deg"] == stroke) & (df["frequency_fstar"] == freq)]
        f_ref = compute_force_reference(
            freq, stroke, R_GYRATION, SPAN, CHORD, RHO
        ).f_ref
        m_ref = compute_moment_reference(
            freq, stroke, R_GYRATION, SPAN, CHORD, RHO
        ).m_ref
        np.testing.assert_allclose(sub["CF_x"], sub["Fx"] / f_ref, rtol=1e-9)
        np.testing.assert_allclose(sub["CF_z"], sub["Fz"] / f_ref, rtol=1e-9)
        np.testing.assert_allclose(sub["CF_my"], sub["My"] / m_ref, rtol=1e-9)

    # Raw force/moment columns are frozen (only derived CF columns were re-derived).
    raw = df[["Fx", "Fy", "Fz", "Mx", "My", "Mz"]]
    raw_sha = hashlib.sha256(
        pd.util.hash_pandas_object(raw, index=False).values.tobytes()
    ).hexdigest()
    assert raw_sha == _FROZEN_RAW_FORCE_SHA, (
        "raw CFD forces changed — they must stay frozen"
    )


# The fine corpus's equivalent of _FROZEN_RAW_FORCE_SHA (same hash recipe), minted from the
# committed examples/prelim_sweep_fine/dataset.parquet BEFORE fix-moment-reference-hinge
# re-extracted it, in a commit touching no parquet -- a digest minted from the regenerated
# file could not tell it apart from the old one and would launder raw-column corruption.
# Row counts cannot do this job: both corpora have identical per-config max_step maps
# (109,656 rows each), so only these two digests distinguish a swapped --input-dir.
# A trip during a corpus re-extraction is a HALT, not a re-pin: the pandas-upgrade re-pin
# allowance above does not extend to a change that rewrites the parquet.
_FROZEN_FINE_RAW_FORCE_SHA = (
    "2666301934a30dd378ec3594709d3ed9f0e464398ec8515c4b47ac3d84e846e4"
)


@pytest.mark.parametrize(
    ("corpus", "expected"),
    [
        ("examples/prelim_sweep", _FROZEN_RAW_FORCE_SHA),
        ("examples/prelim_sweep_fine", _FROZEN_FINE_RAW_FORCE_SHA),
    ],
)
def test_committed_corpus_raw_forces_are_frozen(corpus, expected):
    """Each corpus's raw Fx..Mz columns hash to their pinned digest, and the two differ.

    Scenario: A reference-point change ... the raw Fx..Mz columns remain exactly equal to the
    committed corpus.
    """
    import hashlib

    assert _FROZEN_RAW_FORCE_SHA != _FROZEN_FINE_RAW_FORCE_SHA
    df = pd.read_parquet(Path(corpus) / "dataset.parquet")
    raw = df[["Fx", "Fy", "Fz", "Mx", "My", "Mz"]]
    raw_sha = hashlib.sha256(
        pd.util.hash_pandas_object(raw, index=False).values.tobytes()
    ).hexdigest()
    assert raw_sha == expected, (
        f"{corpus}: raw CFD forces changed — they must stay frozen"
    )


def test_degenerate_renormalization_is_rejected():
    """A zero new reference (k undefined) or a missing column is rejected, not inf/NaN.

    Scenario: Degenerate re-normalization is rejected. Re-normalizing by ``f_ref_new = 0``
    is rejected by the single-source coefficient helper (parity with non-positive f_ref);
    a missing predicted/target column raises KeyError rather than silently skipping.
    """
    with pytest.raises(ValueError):
        compute_force_coefficients(1.0, 2.0, 3.0, 0.0)  # f_ref_new = 0 -> k undefined
    df = pd.read_parquet(_PRED)
    with pytest.raises(KeyError):
        _ = df["CF_q_true"]  # absent target column


# ---------------------------------------------------------------------------
# Hinge-referenced moments in the committed corpora (fix-moment-reference-hinge, design D8)
# ---------------------------------------------------------------------------

_CORPORA = ("examples/prelim_sweep", "examples/prelim_sweep_fine")
_CANONICAL_VERTEX = Path("examples/flapping_wing/wing.vertex")


def _committed_decks(corpus: str) -> dict[str, dict[str, np.ndarray]]:
    """Each config's particle origin and declared hinge, read from its COMMITTED deck.

    Deliberately not from the corpus run_metadata.json that the same extraction wrote: an
    extractor computing ``hinge - origin`` would record the negated offset and a guard reading
    it back would reconcile the two happily. The deck is a different artifact and code path.
    """
    import json

    from mosquito_cfd.force_surrogate.geometry_guard import read_deck_value

    manifest = json.loads(
        (Path(corpus) / "sweep_manifest.json").read_text(encoding="utf-8")
    )
    decks = {}
    for config in manifest["configs"]:
        text = (Path(corpus) / config["input_file"]).read_text(encoding="utf-8")
        decks[config["name"]] = {
            "particle": np.array(
                [read_deck_value(text, f"particle_inputs.{a}") for a in "xyz"]
            ),
            "hinge": np.array(
                [read_deck_value(text, f"particle_inputs.hinge_{a}") for a in "xyz"]
            ),
        }
    return decks


def _m_ref(sub: pd.DataFrame) -> float:
    from mosquito_cfd.force_surrogate import compute_moment_reference

    (stroke,) = sub["stroke_amp_deg"].unique()
    (freq,) = sub["frequency_fstar"].unique()
    return compute_moment_reference(freq, stroke, R_GYRATION, SPAN, CHORD, RHO).m_ref


@pytest.mark.parametrize("corpus", _CORPORA)
def test_committed_moment_coefficients_are_hinge_referenced(corpus):
    """Per config (not per (stroke, freq) key, which groups 3 configs and can mask one):
    CF_m* equal the raw moments shifted by (particle - hinge) x F, over m_ref; and CF_mx is
    NOT the unshifted Mx/m_ref, so a zero offset or a dropped shift cannot pass vacuously.

    Scenario: Committed corpora reconcile against their declared offset (design D8.4).
    """
    df = pd.read_parquet(Path(corpus) / "dataset.parquet")
    decks = _committed_decks(corpus)
    assert set(df["config_name"]) == set(decks)
    failures = []
    for name, deck in decks.items():
        d = deck["particle"] - deck["hinge"]
        sub = df[df["config_name"] == name]
        m_ref = _m_ref(sub)
        fx, fy, fz = (sub[c].to_numpy() for c in ("Fx", "Fy", "Fz"))
        mx, my, mz = (sub[c].to_numpy() for c in ("Mx", "My", "Mz"))
        expected = {
            "CF_mx": (mx + d[1] * fz - d[2] * fy) / m_ref,
            "CF_my": (my + d[2] * fx - d[0] * fz) / m_ref,
            "CF_mz": (mz + d[0] * fy - d[1] * fx) / m_ref,
        }
        for col, want in expected.items():
            if not np.allclose(sub[col].to_numpy(), want, rtol=1e-9, atol=1e-12):
                failures.append(f"{name}: {col} != (M + (particle - hinge) x F)/m_ref")
        if np.allclose(sub["CF_mx"].to_numpy(), mx / m_ref, rtol=1e-9, atol=1e-12):
            failures.append(f"{name}: CF_mx equals the unshifted Mx/m_ref")
        # d_x = d_z = 0 makes the y-term of d x F exactly zero for finite forces, so CF_my
        # must COMPARE EQUAL to My/m_ref on real data, not merely be close (design D8.2).
        if (
            d[0] == 0
            and d[2] == 0
            and not (sub["CF_my"].to_numpy() == my / m_ref).all()
        ):
            failures.append(f"{name}: CF_my != My/m_ref exactly despite d_x = d_z = 0")
    assert not failures, f"{corpus}: {len(failures)} failure(s):\n" + "\n".join(
        failures
    )


@pytest.mark.parametrize("corpus", _CORPORA)
def test_committed_decks_declare_the_hinge_in_the_particle_frame(corpus):
    """hinge_y + SPAN/2 == particle_y (and x, z coincide) for every committed deck.

    ``constants.SPAN`` is authored separately from the decks, so this reconciles the deck's
    ``particle_inputs.hinge_*`` against an independent declaration, establishing that it is
    an absolute position in the same frame as ``particle_inputs.{x,y,z}`` -- not a relative
    offset, under which the whole shift would be wrong while every self-consistency check
    passed. It does NOT establish that the particle origin is the mesh's mid-span point: both
    sides use the nominal SPAN = 3.0, while the committed geometry's span is 2.95. Committed
    corpora only; a future multi-wing deck may legitimately break it. (Design D8.5.)
    """
    for name, deck in _committed_decks(corpus).items():
        particle, hinge = deck["particle"], deck["hinge"]
        assert hinge[1] + SPAN / 2 == particle[1], name
        assert (hinge[0], hinge[2]) == (particle[0], particle[2]), name


@pytest.mark.parametrize("corpus", _CORPORA)
def test_committed_moments_put_the_ib_part_arm_on_the_wing(corpus):
    """Empirical sign discriminator (design D8.6) -- the one check that leaves our bookkeeping.

    The force-weighted spanwise arm from the hinge, ``b = M_hinge_x / F_z``, should fall
    inside the wing, ``(0, tip_arm]``, for most settled-beat rows. Measured with the correct
    sign: 96.8% (coarse) / 98.1% (fine); with a sign-flipped shift: 0.9% / 0.5%. The gate is
    a calibrated fraction (>= 0.90), NOT a bound on every row: ``b`` is a mixed-sign-weighted
    mean (f_z changes sign across the wing), so it is not bounded by the wing's extent; it
    also omits the ``-(z_i - z_h) F_y`` term of M_x. ``F``/``M`` are the spread IB force and
    moment only, so ``b`` is the IB-part arm, not the true centre of pressure.

    ``tip_arm`` is derived from the deck and the wing's own vertex file (hinge 0.5, tip
    2.0 + 1.475 = 3.475, so 2.975 for the committed geometry), not typed in.
    """
    from mosquito_cfd.force_surrogate.geometry_guard import wing_half_span

    df = pd.read_parquet(Path(corpus) / "dataset.parquet")
    settled = df[df["wingbeat"] >= 1]
    half_span = wing_half_span(_CANONICAL_VERTEX)
    in_band = flipped_in_band = 0
    for name, deck in _committed_decks(corpus).items():
        sub = settled[settled["config_name"] == name]
        tip_arm = deck["particle"][1] + half_span - deck["hinge"][1]
        b = sub["CF_mx"].to_numpy() * _m_ref(sub) / sub["Fz"].to_numpy()
        in_band += int(((b > 0) & (b <= tip_arm)).sum())
        # Calibration: the same rows with the shift's sign reversed, from the raw columns.
        a = deck["particle"][1] - deck["hinge"][1]
        b_flip = (sub["Mx"].to_numpy() - a * sub["Fz"].to_numpy()) / sub[
            "Fz"
        ].to_numpy()
        flipped_in_band += int(((b_flip > 0) & (b_flip <= tip_arm)).sum())
    assert flipped_in_band / len(settled) < 0.10  # the discriminator discriminates here
    fraction = in_band / len(settled)
    assert fraction >= 0.90, (
        f"{corpus}: only {fraction:.1%} of settled-beat rows put the IB-part arm "
        "M_hinge_x/F_z on the wing (expected ~97%; a sign-flipped shift gives <1%)"
    )


# The CFD image each corpus's solver ran under, as recorded by the CFD runs themselves: the
# coarse sweep_provenance and the fine per-config run metadata, not the extraction's own record.
def _cfd_digests(corpus: str) -> set[str]:
    import json

    root = Path(corpus)
    if corpus.endswith("prelim_sweep_fine"):
        return {
            json.loads(p.read_text(encoding="utf-8"))["docker_image"].split("@", 1)[1]
            for p in root.glob("run_metadata_*.json")
        }
    provenance = json.loads(
        (root / "sweep_provenance.json").read_text(encoding="utf-8")
    )
    return {provenance["downstream_artifacts_regenerated_from"]["docker_image_digest"]}


@pytest.mark.parametrize("corpus", _CORPORA)
def test_committed_extraction_provenance_matches_the_decks_and_the_cfd_run(corpus):
    """The committed corpus run_metadata.json records what the spec fixes: the per-config
    offsets (checked against the committed decks, an independent artifact), a hash for
    every consumed CSV, and the digest of the image the CFD RAN under, not whatever host
    re-extracted it. The fine corpus's decks are all anchored to their runs' deck_sha256.

    Scenarios: Moment reference point travels with the corpus; Re-extraction preserves the
    CFD digest.
    """
    import json

    meta = json.loads((Path(corpus) / "run_metadata.json").read_text(encoding="utf-8"))
    decks = _committed_decks(corpus)
    ref, inputs = meta["moment_reference"], meta["extraction_inputs"]
    assert ref["point"] == "wing_hinge" and ref["axes"] == "lab"
    assert set(ref["configs"]) == set(decks) == set(inputs["csv_sha256"])
    for name, deck in decks.items():
        assert (
            ref["configs"][name]["offset"]
            == (deck["particle"] - deck["hinge"]).tolist()
        )
        assert len(inputs["csv_sha256"][name]) == 64
    assert meta["dropped_configs"] == []

    (cfd_digest,) = _cfd_digests(corpus)
    assert meta["docker_image"].split("@", 1)[1] == cfd_digest

    anchored = [r["deck_sha256_verified_against"] for r in ref["configs"].values()]
    if corpus.endswith("prelim_sweep_fine"):
        assert all(anchored), "every fine deck has its run's deck_sha256 to match"
    else:
        assert not any(anchored)  # coarse: no per-config metadata (known limitation)


def test_readme_staleness_banner_tracks_whether_the_surrogate_matches_the_dataset():
    """The coarse README carries a staleness banner exactly while the committed surrogate's
    CF_mx/CF_mz targets disagree with the committed dataset (fix-moment-reference-hinge
    re-extracted the dataset in PR2 and retrains in PR3). Both directions are pinned: the
    banner cannot be forgotten while stale, and the retrain cannot leave it behind."""
    base = Path("examples/prelim_sweep")
    holdout = pd.read_parquet(base / "surrogate" / "holdout_predictions.parquet")
    dataset = pd.read_parquet(base / "dataset.parquet")
    joined = holdout.merge(
        dataset[["config_name", "time", "CF_mx", "CF_mz"]], on=["config_name", "time"]
    )
    assert len(joined) == len(holdout)  # every holdout row is a dataset row
    stale = not all(
        np.allclose(joined[f"{c}_true"], joined[c], rtol=1e-9, atol=1e-12)
        for c in ("CF_mx", "CF_mz")
    )
    readme = (base / "README.md").read_text(encoding="utf-8")
    assert ("are stale against `dataset.parquet`" in readme) == stale
