"""Validated baseline constants for the flapping-wing force surrogate.

All values are dimensionless: the validated flapping-wing pipeline has no physical
scaling (see the force-surrogate design doc, decision D3).
"""

# Wing geometry (dimensionless chord units).
SPAN = 3.0  # wing span [chord lengths]
CHORD = 1.0  # wing chord [reference length]
R_TIP = 3.0  # hinge-to-tip distance [chord lengths]; the geometry's tip arm
R_MID = (
    1.5  # hinge-to-midspan arm, used for viscosity / Reynolds scaling [chord lengths]
)
# Radius of gyration r_gyr = sqrt(S_yy / area), the van Veen (2022) force-normalization
# arm (S_yy = integral c(y) y^2 dy is the spanwise second moment of area). Derived once
# from the committed examples/flapping_wing/wing.vertex (908 markers) and guarded by
# test_radius_of_gyration_traced_from_wing_vertex. It sits outboard of the geometric
# midspan (1.5) because the elliptic load is tip-weighted, and inboard of R_TIP (3.0).
R_GYRATION = 1.6984914918884995  # van Veen S_yy normalization arm [chord lengths]
# NOTE: force coefficients normalize on R_GYRATION (van Veen F_ref = 0.5*rho*omega^2*S_yy,
# i.e. the speed at the radius of gyration). R_TIP (3.0) is the geometric tip arm and is
# NOT the normalization arm; R_MID (1.5) is the viscosity/Reynolds arm used by
# compute_reynolds (sweep.py). Do not conflate the three.
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
