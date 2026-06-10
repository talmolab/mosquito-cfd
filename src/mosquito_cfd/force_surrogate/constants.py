"""Validated baseline constants for the flapping-wing force surrogate.

All values are dimensionless: the validated flapping-wing pipeline has no physical
scaling (see the force-surrogate design doc, decision D3).
"""

# Wing geometry (dimensionless chord units).
SPAN = 3.0  # wing span [chord lengths]
CHORD = 1.0  # wing chord [reference length]
R_TIP = (
    3.0  # hinge-to-tip distance, used for tip-velocity normalization [chord lengths]
)
R_MID = (
    1.5  # hinge-to-midspan arm, used for viscosity / Reynolds scaling [chord lengths]
)
# NOTE: R_TIP (tip radius, 3.0) is the normalization arm. The midspan arm R_MID = 1.5
# (hinge-to-midspan) is used for viscosity / Reynolds scaling (see
# examples/flapping_wing/RESULTS.md), NOT for force normalization. Do not conflate them:
# force coefficients normalize on R_TIP; compute_reynolds (sweep.py) uses R_MID.
RHO = 1.0  # fluid density [dimensionless]

# Validated reference kinematics (the van Veen-style demo point documented in RESULTS.md).
VALIDATED_F_STAR = 1.0  # dimensionless flap frequency (1 wingbeat per time unit)
VALIDATED_PHI_AMP_DEG = 70.0  # stroke amplitude [deg]
VALIDATED_PITCH_AMP_DEG = 45.0  # pitch amplitude [deg]
VALIDATED_NU_STAR = (
    0.115  # dimensionless viscosity (ns.vel_visc_coef); Re~100 at phi=70
)

# Sweep run-control defaults (force-surrogate PR2). dt matches inputs.3d.validation.
DT = 5e-4  # fixed timestep [dimensionless time]; ns.fixed_dt in the validated base
N_WINGBEATS = 2  # whole wingbeats each sweep config must cover (run-duration scaling)

# Aedes aegypti-anchored kinematic sweep grid (Bomphrey et al. 2017, Nature 544:92-95,
# DOI 10.1038/nature21727; see docs/force_surrogate/roadmap.md "Verified source numbers").
# Stroke brackets the Aedes 39 deg; f* = 1.0 ~ 717 Hz (0.85/1.15 ~ 609/825 Hz); pitch
# centred on the validated 45 deg.
AEDES_STROKE_AMP_DEG = (35.0, 45.0, 55.0)  # stroke amplitude levels [deg]
AEDES_FREQUENCY_FSTAR = (0.85, 1.0, 1.15)  # dimensionless frequency levels (f*)
AEDES_PITCH_AMP_DEG = (30.0, 45.0, 60.0)  # pitch amplitude levels [deg]

# Held-out split for the eventual predicted-vs-CFD figure (CC-4): seeded, non-corner.
N_HOLDOUT = 6  # number of held-out configs (training-exclusion label only)
HOLDOUT_SEED = 20260609  # fixed seed for reproducible holdout selection
