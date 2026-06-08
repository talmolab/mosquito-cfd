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
# NOTE: R_TIP (tip radius, 3.0) is the normalization arm. The midspan arm r_mid = 1.5
# (hinge-to-midspan) is used for viscosity / Reynolds scaling (see
# examples/flapping_wing/RESULTS.md), NOT for force normalization. Do not conflate them.
RHO = 1.0  # fluid density [dimensionless]

# Validated reference kinematics (the van Veen-style demo point documented in RESULTS.md).
VALIDATED_F_STAR = 1.0  # dimensionless flap frequency (1 wingbeat per time unit)
VALIDATED_PHI_AMP_DEG = 70.0  # stroke amplitude [deg]
VALIDATED_PITCH_AMP_DEG = 45.0  # pitch amplitude [deg]
