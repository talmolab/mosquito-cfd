# Timestep Analysis and GPU-Hour Projections (Interim Estimates)

**Date**: 2026-02-25
**Status**: Interim — based on ellipsoid benchmark data pending wing test run
**Purpose**: Document CFL-constrained timestep calculation and transferable GPU-hour projections for APEX proposal

---

## Summary

The ellipsoid benchmark provides a valid basis for **per-step wall time** projections, but the number of steps per wingbeat must be derived from the CFL stability condition — not from the ellipsoid (which used a manually specified, dimensionless timestep). At the planned finest AMR resolution of 0.01 mm, the CFL condition gives **~2,570 steps/wingbeat**, which is about **2× fewer** than the 5,000 assumed in `resource_projection.csv`. The per-step wall time (~4.2 s/step at 10M cells on A40) is transferable.

---

## 1. Wing Tip Velocity (Maximum)

The dominant velocity in the domain is the wing tip at peak stroke velocity.

**Kinematics** (Bomphrey et al. 2017, *Aedes aegypti*):

| Parameter | Symbol | Value | Unit |
|-----------|--------|-------|------|
| Wing span | R | 3.0 | mm |
| Stroke amplitude (half) | φ₀ | 39 | degrees |
| Flap frequency | f | 717 | Hz |

Stroke angle: φ(t) = φ₀ sin(2πft)

Tip velocity: U_tip(t) = R · dφ/dt = R · φ₀ · 2πf · cos(2πft)

**Maximum tip velocity** (at mid-stroke, cos = 1):

```
U_tip_max = R · φ₀ · 2πf
           = 3.0×10⁻³ m × (39 × π/180 rad) × 2π × 717 s⁻¹
           = 3.0×10⁻³ × 0.6807 × 4,506
           = 9.20 m/s
```

This is the maximum fluid velocity in the domain and the binding velocity for the CFL condition.

---

## 2. CFL-Constrained Timestep

The explicit advection stability condition (CFL condition):

```
Δt_CFL = CFL × Δx_min / U_max
```

IAMReX uses CFL = 0.5 by default (design.md). The finest AMR cell size Δx_min controls Δt because adaptive mesh refinement concentrates the smallest cells near the wing surface.

**Physical units** (air at 25°C, ν = 1.56×10⁻⁵ m²/s):

| Finest Δx | Δx_min (m) | Δt_CFL (s) | Δt_CFL scientific |
|-----------|-----------|------------|-------------------|
| 0.05 mm | 5.0×10⁻⁵ | 2.72×10⁻⁶ | 2.7 μs |
| 0.02 mm | 2.0×10⁻⁵ | 1.09×10⁻⁶ | 1.1 μs |
| 0.01 mm | 1.0×10⁻⁵ | **5.43×10⁻⁷** | **0.54 μs** |
| 0.005 mm | 5.0×10⁻⁶ | 2.72×10⁻⁷ | 0.27 μs |
| 1.84 μm* | 1.84×10⁻⁶ | **1.00×10⁻⁷** | **0.10 μs** |

*Van Veen et al. (2022) used Δt = 10⁻⁷ s; back-calculating the implied Δx_min:
```
Δx_min = Δt × U_max / CFL = 1.0×10⁻⁷ × 9.20 / 0.5 = 1.84×10⁻⁶ m = 1.84 μm
```
Van Veen's IBAMR grid is ~5.4× finer than our planned finest level (0.01 mm = 10 μm).

**Note on viscous stability**: IAMReX uses a projection method where viscous terms are treated
implicitly (Crank-Nicolson). The advective CFL condition is therefore the only explicit
stability constraint. For reference, the explicit viscous stability limit at Δx = 0.01 mm is:
```
Δt_visc = Δx² / (6ν) = (1.0×10⁻⁵)² / (6 × 1.56×10⁻⁵) = 1.07×10⁻⁶ s
```
The viscous limit is 2× less restrictive than CFL at Δx = 0.01 mm — CFL is the binding constraint
at our planned resolution.

---

## 3. Steps per Wingbeat

Wingbeat period: T = 1/f = 1/717 = 1.395×10⁻³ s

```
N_steps = T / Δt_CFL
```

| Finest Δx | Δt_CFL (s) | Steps/wingbeat | Source |
|-----------|-----------|----------------|--------|
| 0.05 mm | 2.72×10⁻⁶ | 513 | CFL formula |
| 0.02 mm | 1.09×10⁻⁶ | 1,280 | CFL formula |
| 0.01 mm | 5.43×10⁻⁷ | **2,570** | CFL formula (planned fine grid) |
| 0.005 mm | 2.72×10⁻⁷ | 5,130 | CFL formula |
| 1.84 μm | 1.00×10⁻⁷ | **13,950** | Van Veen et al. (2022) (measured) |

### Reconciling Document Inconsistencies

| Document | Steps/wingbeat | Implied Δt (s) | Implied Δx_min |
|----------|---------------|----------------|----------------|
| `design.md` (line 214) | 14,000 | 1.0×10⁻⁷ | 1.84 μm (Van Veen grid, not our grid) |
| `resource_projection.csv` | 5,000 | 2.79×10⁻⁷ | 5.1 μm |
| **CFL at planned 0.01 mm** | **2,570** | **5.43×10⁻⁷** | 0.01 mm (our planned fine grid) |

The 14,000 figure in `design.md` is attributed to Van Veen et al. and is correct for their
grid — but their grid is ~5.4× finer than what we plan to use. The 5,000 in `resource_projection.csv`
is an intermediate round number with no documented basis. Neither applies directly to our
planned resolution.

**Recommendation**: A short test run (100–200 steps with flapping wing input file) will give
the actual AMReX-selected Δt for our specific AMR configuration. Use that to replace these estimates.

---

## 4. Ellipsoid Data: What Transfers and What Doesn't

### What transfers to the wing case

| Quantity | Ellipsoid value | Wing applicability |
|----------|----------------|-------------------|
| Per-step wall time at N cells | 1.89 s/step @ 4.2M cells | ✓ Yes — IB penalty included |
| Throughput (M cells/s) | 2.22 M cells/s | ✓ Yes — scales with cell count |
| Memory scaling with AMR | Measured | ✓ Yes — same code path |
| A40→A100 bandwidth speedup | 2.9× (estimated) | ✓ Yes — hardware ratio |

### What does NOT transfer

| Quantity | Reason |
|----------|--------|
| Number of steps/wingbeat | Ellipsoid used dimensionless Δt=0.01 (manually set, not CFL-limited) |
| Actual Δt value | Different physical setup, different dimensional mapping |
| Physics adequacy (LEV resolution) | Ellipsoid is a smooth body; mosquito wing has sharp edges, LEV at different Re |

**Ellipsoid was run in dimensionless units** with Δt=0.01 (dimensionless), which is not related
to the CFL constraint of the wing in physical units. The per-step **wall time** is transferable;
the per-step **simulation time** is not.

---

## 5. Wall-Time Extrapolation from Ellipsoid

### Measured A40 throughput

| Case | Cells | Time/step (s) | Throughput (M cells/s) |
|------|-------|--------------|----------------------|
| Flow past sphere (medium) | 4,194,304 | 1.76 | 2.38 |
| Heaving ellipsoid | 4,194,304 | 1.89 | 2.22 |

The ellipsoid is more relevant for the wing (both use IBM with moving bodies and IB force
computation). The sphere throughput is slightly faster (fixed body, simpler IB).

**Conservative choice**: Use ellipsoid throughput (2.22 M cells/s) for wing projections.

### Extrapolated per-step wall time for wing

Using linear scaling (valid for memory-bandwidth-limited workloads):

```
Wall time/step ≈ N_cells / throughput
```

| Active cells | Wall time/step — A40 (s) | Wall time/step — A100 (s, 2.9× speedup) |
|-------------|--------------------------|----------------------------------------|
| 1M (coarse wing) | 1M / 2.22M = 0.45 | 0.16 |
| 5M | 5M / 2.22M = 2.25 | 0.78 |
| 10M (planned production) | 10M / 2.22M = **4.50** | **1.55** |
| 50M (fine wing) | 50M / 2.22M = 22.5 | 7.8 |

Note: `resource_projection.csv` uses sphere throughput (2.38 M cells/s) → 4.20 s/step at 10M.
The ellipsoid-based estimate (4.50 s/step) is ~7% more conservative and is preferred here.

---

## 6. GPU-Hour Projections by Refinement Level

Scenario: 100 wingbeats per simulation (for statistics), single A100 GPU.

```
GPU-hours/sim = N_steps/WB × wall_time/step (A100) × 100 wingbeats / 3600 s/hr
```

| Finest Δx | Active cells | Steps/WB | Time/step (A100, s) | Hours/sim (A100) | Notes |
|-----------|-------------|----------|---------------------|-----------------|-------|
| 0.05 mm | ~1M | 513 | 0.16 | **2.3** | Very coarse; LEV unlikely resolved |
| 0.02 mm | ~5M | 1,280 | 0.78 | **28** | Intermediate; suitable for parameter sweeps |
| 0.01 mm | ~10M | 2,570 | 1.55 | **110** | Planned production resolution |
| 0.005 mm | ~50M | 5,130 | 7.8 | **1,100** | High-fidelity; limited number feasible |

### Comparison to resource_projection.csv

`resource_projection.csv` assumes 5,000 steps/wingbeat and uses sphere throughput (4.20 s/step A40 → 1.45 s/step A100):

```
resource_projection.csv: 1.45 s/step × 5,000 steps × 100 wingbeats / 3600 = 201 hours/sim
```

CFL-based estimate with ellipsoid throughput at 0.01 mm finest:

```
CFL-based: 1.55 s/step × 2,570 steps × 100 wingbeats / 3600 = 110 hours/sim
```

The resource_projection.csv estimate is **~1.8× more conservative** than the CFL-based estimate.
This conservatism is appropriate for a proposal; the true cost will be between these values.

---

## 7. Does Ellipsoid Data Help Choose Mesh Refinement?

**Short answer**: Partially — it constrains feasibility, not physics fidelity.

The ellipsoid benchmark lets us estimate GPU-hours at each refinement level (Section 6).
This tells us which resolutions are **computationally feasible** within the proposed allocation.

However, it does NOT tell us which resolution is **physically adequate** to resolve:
- The leading-edge vortex (LEV) on the mosquito wing
- Force production during stroke reversal (rotational mechanisms)
- Wake structure evolution

For physical adequacy, we need a **grid convergence study** on the actual wing geometry:
Cases 1 (sphere) and 2 (heaving plate) in `design.md` build toward this methodology,
but the wing itself (Case 3) is the definitive test.

**Practical guidance from ellipsoid data**:
- 0.01 mm finest (10M cells, 110 GPU-hours/sim): feasible at the proposed allocation scale
- 0.005 mm finest (50M cells, 1,100 GPU-hours/sim): reserve for selective high-fidelity runs
- 0.02 mm (5M cells, 28 GPU-hours/sim): suitable for large kinematic parameter sweeps
- The grid convergence slope from Cases 1–2 will indicate whether 0.01 mm is adequate

---

## 8. Revised APEX Resource Estimates (CFL-Corrected)

Using CFL-based steps/wingbeat (2,570 at 0.01 mm) and ellipsoid throughput:

| Milestone | Sims | Hours/sim (A100) | A100 GPU-hours |
|-----------|------|-----------------|---------------|
| Code validation | 10 | 5 | 50 |
| Single wing baseline | 5 | 110 | 550 |
| Kinematic parameter sweep (0.02 mm) | 50 | 28 | 1,400 |
| Re sensitivity study | 50 | 110 | 5,500 |
| Production dataset (0.01 mm) | 250 | 110 | 27,500 |
| **Subtotal** | | | **35,000** |
| Contingency (20%) | | | 7,000 |
| **Total (CFL-corrected)** | | | **~42,000** |

Compared to `resource_projection.csv` total of 85,784 GPU-hours — the CFL-corrected estimate
is about **2× lower**. The discrepancy comes primarily from steps/wingbeat (2,570 vs 5,000)
and choice of throughput (ellipsoid vs sphere).

**Recommendation for proposal**: Use the more conservative `resource_projection.csv` figure
(~86,000 GPU-hours) as the request. The CFL analysis confirms this is upper-bounded and
provides margin for:
- Multi-wingbeat transients before statistics (50+ wingbeats warm-up)
- Higher mesh refinement for selected cases
- Post-processing and checkpoint storage I/O overhead
- Uncertainty in the A40→A100 speedup estimate

---

## 9. Data Provenance

### Wing parameters
- Bomphrey et al. (2017): f = 717 ± 59 Hz, φ₀ = 39 ± 4°, R ≈ 3.0 mm
  - *Nature Communications* 8:1213. doi:10.1038/s41467-017-01248-8

### Van Veen timestep
- Van Veen et al. (2022): Δt = 10⁻⁷ s in IBAMR at unstated grid resolution
  - *Journal of Experimental Biology* 225:jeb243232. doi:10.1242/jeb.243232
  - Note: Van Veen et al. used these IBAMR simulations to calibrate an analytical
    quasi-steady model — not an ML surrogate.

### Ellipsoid benchmark
- Measured: 2026-02-24, Docker image `ghcr.io/talmolab/mosquito-cfd:fp64`
- IAMReX commit: c5f8e2a, AMReX 24.11, CUDA 12.4
- GPU: NVIDIA A40 (48 GB VRAM, 696 GB/s bandwidth, 0.585 TFLOPS FP64)
- Run file: `benchmarks/results/tables/resource_projection.csv`

### A100 speedup estimate
- Bandwidth ratio: 2039 / 696 = 2.93× (primary estimate, CFD is bandwidth-limited)
- Compute ratio: 9.7 / 0.585 = 16.6× (upper bound, compute-limited)
- Used: 2.9× (bandwidth-limited, conservative)

---

## 10. Action Items

| Item | Priority | Who |
|------|----------|-----|
| Run 100–200 steps with flapping wing input file, record AMReX-selected Δt | High | CFD team |
| Update `resource_projection.csv` with CFL-verified steps/wingbeat | High | CFD team |
| Reconcile `design.md` timestep comment (currently implies Van Veen grid) | Medium | CFD team |
| Conduct grid convergence study (Cases 1–2) to determine required Δx for wing | Medium | CFD team |
| Verify A40→A100 speedup with actual A100 benchmark (if accessible) | Medium | CFD team |