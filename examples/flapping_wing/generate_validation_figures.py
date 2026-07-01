"""Verification figures for the van Veen normalization (standardize-force-normalization).

Each figure visualizes a quantity that is independently unit-tested, and each generator
returns the key numbers it displays so a test can assert the figure shows the tested values
(the figure can never silently drift from the math). Pure, cluster-free, committed-data only.

  V1  three-convention CF overlay vs the [0.5,1.5] band   (F_ref values)
  V2  planform + second-moment integrand c(y)*y^2          (r_gyr, S_yy)
  V3  scale-invariance scatter before/after                (Delta R^2)
  V4  added-mass decomposition (ib vs added-mass)          (RMS fractions; NOT gated)
  V5  lab-vs-body frame at the alpha=45 deg midstroke      (frame caveat)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mosquito_cfd.benchmarks.flapping_wing import (
    STEADY_WINDOW_T0,
    added_mass_fraction,
    reconstruct_wing_forces,
)
from mosquito_cfd.force_surrogate import compute_force_reference
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, R_TIP, RHO, SPAN
from mosquito_cfd.force_surrogate.train import _r2

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_BAND = (0.5, 1.5)


def fig_v1_three_convention(out_dir: Path) -> dict:
    """V1: same forces, three F_ref, vs the van Veen plausibility band."""
    f_current = compute_force_reference(1.0, 70.0, R_TIP, SPAN, CHORD, RHO).f_ref
    f_vanveen = compute_force_reference(1.0, 70.0, R_GYRATION, SPAN, CHORD, RHO).f_ref
    f_mean = f_current * (2.0 / np.pi) ** 2  # mean-wingtip (issue's original proposal)
    df = pd.read_csv(_HERE / "forces.csv")
    t, fx, fz = (df[c].to_numpy(float) for c in ("time", "Fx", "Fz"))
    m = t >= STEADY_WINDOW_T0
    refs = {
        "current (peak tip)": (f_current, "#888888"),
        "mean tip": (f_mean, "#1f77b4"),
        "van Veen": (f_vanveen, "#d62728"),
    }
    fig, (axx, axz) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    for name, (fref, col) in refs.items():
        axx.plot(t[m], fx[m] / fref, color=col, lw=1.5, label=f"{name} (F_ref={fref:.0f})")
        axz.plot(t[m], fz[m] / fref, color=col, lw=1.5, label=f"{name} (F_ref={fref:.0f})")
    for ax, lab in ((axx, "CF_x (lab, stroke)"), (axz, "CF_z (lab, lift)")):
        for s in (1, -1):
            ax.axhspan(s * _BAND[0], s * _BAND[1], color="green", alpha=0.08)
        ax.axhline(0, color="gray", lw=0.5, ls="--")
        ax.set_ylabel(lab)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(alpha=0.25)
    axz.set_xlabel("time (wingbeats)")
    axx.set_title("V1  Three normalization conventions vs van Veen band [0.5,1.5]\n"
                  "(same forces; only F_ref differs)")
    fig.tight_layout()
    fig.savefig(out_dir / "V1_three_convention_CF.png", dpi=130)
    plt.close(fig)
    return {"f_current": f_current, "f_mean": f_mean, "f_vanveen": f_vanveen}


def fig_v2_second_moment(out_dir: Path) -> dict:
    """V2: planform + the tip-weighted second-moment integrand; r_gyr from markers."""
    verts = np.loadtxt(_HERE / "wing.vertex", skiprows=1)
    x = verts[:, 0]  # chord
    # Span is the widest-extent axis: T2a re-orients it to y; the legacy geometry used z. Detecting
    # it keeps r_gyr/S_yy orientation-invariant across the axis-convention refactor.
    span = verts[:, int(np.argmax(np.ptp(verts, axis=0)))]
    r = span + (R_TIP - span.max())
    r_gyr = float(np.sqrt(np.mean(r**2)))
    s_planform = np.pi / 4.0 * SPAN * CHORD
    s_yy = r_gyr**2 * s_planform
    nb = 30
    edges = np.linspace(r.min(), r.max(), nb + 1)
    ctr = 0.5 * (edges[:-1] + edges[1:])
    chord_r = np.array([
        np.ptp(x[(r >= edges[i]) & (r < edges[i + 1])])
        if np.sum((r >= edges[i]) & (r < edges[i + 1])) > 1 else 0.0
        for i in range(nb)
    ])
    integrand = chord_r * ctr**2
    fig, (axp, axi) = plt.subplots(1, 2, figsize=(12, 4.5))
    axp.scatter(r, x, s=3, color="#1f77b4", alpha=0.6)
    for val, lab, col in ((1.5, "r_mid=1.50", "orange"),
                          (r_gyr, f"r_gyr={r_gyr:.2f}", "red"),
                          (R_TIP, "r_tip=3.00", "black")):
        axp.axvline(val, color=col, ls="--", lw=1.4, label=lab)
    axp.set_xlabel("hinge distance r")
    axp.set_ylabel("chord x")
    axp.set_title("V2a  Planform: van Veen uses r_gyr, not r_tip")
    axp.legend(fontsize=8)
    axp.grid(alpha=0.25)
    axi.plot(ctr, integrand, color="#d62728", lw=1.8)
    axi.fill_between(ctr, integrand, color="#d62728", alpha=0.12)
    axi.axvline(r_gyr, color="red", ls="--", lw=1.2)
    axi.set_xlabel("hinge distance r")
    axi.set_ylabel("c(y)*y^2  (S_yy integrand)")
    axi.set_title(f"V2b  Tip-weighted load: S_yy={s_yy:.2f}, r_gyr={r_gyr:.2f}")
    axi.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "V2_second_moment.png", dpi=130)
    plt.close(fig)
    return {"r_gyr": r_gyr, "s_yy": s_yy}


def fig_v3_scale_invariance(out_dir: Path) -> dict:
    """V3: predicted-vs-CFD scatter before/after re-normalization; R^2 unchanged."""
    pred = pd.read_parquet(_REPO / "examples/prelim_sweep/surrogate/holdout_predictions.parquet")
    k = compute_force_reference(1.0, 70.0, R_TIP, SPAN, CHORD, RHO).f_ref / \
        compute_force_reference(1.0, 70.0, R_GYRATION, SPAN, CHORD, RHO).f_ref
    out = {}
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    for i, coef in enumerate(("CF_x", "CF_z")):
        y = pred[f"{coef}_true"].to_numpy(float)
        yhat = pred[f"{coef}_pred"].to_numpy(float)
        r2b, r2a = _r2(y, yhat), _r2(y * k, yhat * k)
        out[coef] = {"r2_before": r2b, "r2_after": r2a, "delta": abs(r2b - r2a)}
        for j, (sc, tag, r2) in enumerate(((1.0, "BEFORE", r2b), (k, "AFTER (van Veen)", r2a))):
            ax = axes[i][j]
            ax.scatter(y * sc, yhat * sc, s=6, alpha=0.3, color="#1f77b4")
            lo, hi = (y * sc).min(), (y * sc).max()
            ax.plot([lo, hi], [lo, hi], "k--", lw=1)
            ax.set_title(f"{coef} {tag}: R2={r2:.6f}")
            ax.grid(alpha=0.25)
    fig.suptitle("V3  Scale-invariance: re-normalization rescales both axes by k; R^2 unchanged")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_dir / "V3_scale_invariance.png", dpi=130)
    plt.close(fig)
    return out


def fig_v4_added_mass(out_dir: Path) -> dict:
    """V4: ib_force vs added-mass decomposition over the cycle (added-mass NOT gated)."""
    d = reconstruct_wing_forces(_HERE / "forces.csv", f_star=1.0, phi_amp_deg=70.0)
    frac = added_mass_fraction(d)
    m = d.time >= STEADY_WINDOW_T0
    fig, (axx, axz) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    for ax, ib, am, fh, lab in (
        (axx, d.cf_x_ib, d.cf_x_added, d.cf_x_hydro, "CF_x"),
        (axz, d.cf_z_ib, d.cf_z_added, d.cf_z_hydro, "CF_z"),
    ):
        ax.plot(d.time[m], ib[m], color="#1f77b4", lw=1.6, label="ib_force (gated)")
        ax.plot(d.time[m], am[m], color="#E69F00", lw=1.4, label="added-mass (rho*SumU)")
        ax.plot(d.time[m], fh[m], color="#d62728", lw=1.2, ls="--", label="6-DOF F_hydro")
        ax.axhline(0, color="gray", lw=0.5, ls="--")
        ax.set_ylabel(lab)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.25)
    axz.set_xlabel("time (wingbeats)")
    axx.set_title(f"V4  Added-mass decomposition (reported, NOT gated)\n"
                  f"RMS fraction of ib_force: stroke {frac['stroke']:.0%}, lift {frac['lift']:.0%}")
    fig.tight_layout()
    fig.savefig(out_dir / "V4_added_mass.png", dpi=130)
    plt.close(fig)
    return frac


def fig_v5_lab_vs_body(out_dir: Path) -> dict:
    """V5: lab vs body frame at the alpha=45 deg midstroke (the frame caveat, honesty figure)."""
    alpha = 45.0
    fig, ax = plt.subplots(figsize=(6, 6))
    a = np.radians(alpha)
    # wing chord line tilted by alpha; lab axes vs body (chord/normal) axes
    chord = np.array([np.cos(-a), np.sin(-a)])
    normal = np.array([-np.sin(-a), np.cos(-a)])
    ax.plot([-chord[0], chord[0]], [-chord[1], chord[1]], color="k", lw=3, label="wing chord")
    ax.annotate("", xy=(1.1, 0), xytext=(0, 0), arrowprops=dict(arrowstyle="->", color="#888"))
    ax.annotate("", xy=(0, 1.1), xytext=(0, 0), arrowprops=dict(arrowstyle="->", color="#888"))
    ax.text(1.12, 0, "lab x (CF_x)", color="#888", va="center")
    ax.text(0, 1.12, "lab z (CF_z)", color="#888", ha="center")
    ax.annotate("", xy=tuple(0.9 * chord), xytext=(0, 0),
                arrowprops=dict(arrowstyle="->", color="#d62728"))
    ax.annotate("", xy=tuple(0.9 * normal), xytext=(0, 0),
                arrowprops=dict(arrowstyle="->", color="#1f77b4"))
    ax.text(*(1.0 * chord), "chord-wise\n(van Veen F_x)", color="#d62728", fontsize=8)
    ax.text(*(1.0 * normal), "wing-normal\n(van Veen F_z)", color="#1f77b4", fontsize=8)
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-1.4, 1.4)
    ax.set_aspect("equal")
    ax.set_title(f"V5  Lab vs body frame at the alpha={alpha:.0f} deg midstroke\n"
                 "lab CF_x/CF_z != van Veen body chord/normal -> body-frame deferred to T2a/T4")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "V5_lab_vs_body.png", dpi=130)
    plt.close(fig)
    return {"alpha_deg": alpha}


def main(out_dir: Path | None = None) -> dict:
    """Generate V1-V5 and return the displayed numbers (also written to a sidecar JSON)."""
    out_dir = out_dir or (_HERE / "figures")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "v1": fig_v1_three_convention(out_dir),
        "v2": fig_v2_second_moment(out_dir),
        "v3": fig_v3_scale_invariance(out_dir),
        "v4": fig_v4_added_mass(out_dir),
        "v5": fig_v5_lab_vs_body(out_dir),
    }
    (out_dir / "validation_figures_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    return summary


if __name__ == "__main__":
    main()
