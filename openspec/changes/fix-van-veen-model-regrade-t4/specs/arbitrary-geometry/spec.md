## RENAMED Requirements

- FROM: `### Requirement: Validation Against Van Veen Parameters`
- TO: `### Requirement: Reference Kinematic Parameters`

## MODIFIED Requirements

### Requirement: Prescribed Sinusoidal Kinematics

IAMReX SHALL update wing marker positions each timestep according to **generic sinusoidal validation
kinematics**: stroke `φ(t) = φ₀·sin(ωt)` and pitch `α(t) = α₀·cos(ωt)`, so the wing pitches through
horizontal at each stroke reversal. This waveform is the project's own. It is **not** taken from van Veen
et al. (2022), whose simulations hold the angle of attack constant within each single stroke (§2.5).

#### Scenario: Stroke angle varies sinusoidally

**Given** a simulation running with prescribed kinematics
**When** time = T/4 (quarter period, T = 1/600 s)
**Then** the stroke angle φ = φ₀ = 70° (maximum stroke)

#### Scenario: Pitch leads stroke by 90°

**Given** a simulation running with prescribed kinematics
**When** time = 0 (start of wingbeat)
**Then** stroke angle φ = 0° AND pitch angle α = 45° (pitch at maximum when stroke crosses zero)

#### Scenario: Markers rotate about hinge

**Given** a wing with hinge at (0.015, 0.015, 0.015)
**When** kinematics are applied
**Then** all markers rotate about the hinge point (not the domain origin)

#### Scenario: Marker positions are updated each timestep

**Given** a simulation with Δt = 1×10⁻⁷ s
**When** advancing from step n to step n+1
**Then** marker positions are recomputed based on the new time t = (n+1)×Δt

### Requirement: Reference Kinematic Parameters

The implementation SHALL use the project's reference kinematic parameters. They are the project's own
choices and are not a parameter set simulated by van Veen et al. (2022), whose simulations hold the angle
of attack constant over single strokes.

#### Scenario: Frequency is 600 Hz

**Given** the hardcoded kinematics implementation
**When** its wingbeat frequency is read
**Then** wingbeat frequency = 600 Hz exactly

#### Scenario: Stroke amplitude is ±70°

**Given** the hardcoded kinematics implementation
**When** its stroke amplitude is read
**Then** stroke amplitude = ±70° (140° peak-to-peak)

#### Scenario: Pitch amplitude is 45°

**Given** the hardcoded kinematics implementation
**When** its pitch amplitude is read
**Then** pitch angle at midstroke = 45°

#### Scenario: Reynolds number range achievable

**Given** the reference parameters and standard air properties (ν = 1.56×10⁻⁵ m²/s)
**When** computing Re = U_tip × chord / ν
**Then** Re is in the range 100–300 for typical tip velocities
