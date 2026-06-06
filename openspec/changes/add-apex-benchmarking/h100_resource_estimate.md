# H100 GPU-Hour Estimate — NVIDIA Academic Grant (Simulation & Modeling)

**Date**: 2026-06-04
**Target**: NVIDIA Academic Grant Program, Q2 close **June 30, 2026** (decision ~Sep 2026)
**Award cap**: up to **30,000 H100-80GB cloud GPU-hours**
**Supersedes**: the A100/Polaris framing in `timestep_cfl_analysis.md` §6–8 and `proposal.md`
(written for the denied ALCF APEX allocation). The CFD measurements and CFL step counts
are unchanged; only the target hardware and request ceiling differ.

---

## 1. Method (unchanged from APEX analysis)

IAMReX advance is **memory-bandwidth-limited**, so per-step wall time scales with HBM
bandwidth, not FP64 throughput. Per-step wall time is extrapolated linearly from the
measured A40 heaving-ellipsoid throughput (the closest analog to the wing: moving body +
IB force computation):

- Measured A40 throughput: **2.22 M cells/s** (ellipsoid, `ghcr.io/talmolab/mosquito-cfd:fp64`, 2026-02-24)
- 10M-cell production step on A40: 10M / 2.22M = **4.50 s/step**
- Steps/wingbeat from CFL (Δt = 0.5·Δx_min/U_tip_max, U_tip_max = 9.20 m/s): **2,570** at the
  planned 0.01 mm finest grid (see `timestep_cfl_analysis.md` §2–3)
- 100 wingbeats/sim for statistics

## 2. Bandwidth scaling — the SXM vs PCIe fork

| GPU | HBM bandwidth | × A40 | × A100-80 | 10M-cell step | Source |
|-----|---------------|-------|-----------|---------------|--------|
| A40 (measured) | 696 GB/s | 1.00 | 0.34 | 4.50 s | measured |
| A100-80 SXM | 2039 GB/s | 2.93 | 1.00 | 1.55 s | APEX estimate |
| **H100-80 SXM5 (HBM3)** | **3350 GB/s** | **4.81** | **1.64** | **0.94 s** | grant primary |
| H100-80 PCIe (HBM2e) | 2000 GB/s | 2.87 | 0.98 | 1.57 s | grant fallback |

**Cloud H100 is normally SXM/HGX (3.35 TB/s)** — that is the primary assumption. If the
awarded instances are PCIe H100 (2.0 TB/s), there is effectively **no speedup over the A100
estimate** and the program must be trimmed (§4).

## 3. Per-sim cost on H100-SXM (CFL-derived)

| Finest Δx | Active cells | Steps/WB | Step (H100-SXM) | Hours/sim (100 WB) |
|-----------|-------------|----------|-----------------|--------------------|
| 0.05 mm | ~1M | 513 | 0.094 s | ~1.3 |
| 0.02 mm | ~5M | 1,280 | 0.47 s | **~17** (sweep grid) |
| 0.01 mm | ~10M | 2,570 | 0.94 s | **~67** (production grid) |
| 0.005 mm | ~50M | 5,130 | 4.68 s | ~667 (selective hi-fi) |

## 4. Request against the 30K cap

**Primary (H100-SXM, CFL step counts):**

| Milestone | Sims | hr/sim | H100-hr |
|-----------|------|--------|---------|
| Code validation (sphere, ellipsoid) | 10 | ~3 | 30 |
| Single-wing baseline (0.01 mm) | 5 | 67 | 335 |
| Kinematic parameter sweep (0.02 mm) | 50 | 17 | 850 |
| Reynolds sensitivity (0.01 mm) | 50 | 67 | 3,350 |
| Production dataset (0.01 mm) | 250 | 67 | 16,750 |
| **Subtotal** | **365** | | **21,315** |
| +20% contingency | | | **~25,600** |

→ **Fits the 30K cap with ~4.4K-hr (15%) margin.** Request the full **30,000 H100-hr**:
on SXM this funds the entire program plus warm-up transients and selective 0.005 mm runs.

**Fallback (H100-PCIe ≈ A100):** the same program is ~42,000 H100-hr — **over the cap.** To
fit 30K, trim the production dataset from 250 → ~150 sims (or shift the Re study to 0.02 mm).
State this contingency in the proposal so the request is robust to instance type.

## 5. Open validations (carried from APEX action items)

- Short flapping-wing run (100–200 steps) to confirm the AMReX-selected Δt vs the CFL estimate
  of 2,570 steps/WB — directly sets the production per-sim cost.
- A measured H100 (or A100) benchmark would replace the bandwidth-ratio projection with data;
  until then the SXM figure is a projection, flagged as such.

## 6. Provenance

A40 throughput, CFL derivation, and kinematics (Bomphrey et al. 2017: f=717 Hz, φ₀=39°, R=3.0 mm)
as documented in `timestep_cfl_analysis.md` §9. Bandwidth specs: A40 696 GB/s; A100-80 2.04 TB/s;
H100-80 SXM5 3.35 TB/s (HBM3); H100-80 PCIe 2.0 TB/s (HBM2e).
