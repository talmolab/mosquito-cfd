# ML Surrogate Architecture: Decisions and Open Questions

*Summary of design discussion, February 25, 2026*

---

## Context

Planning the ML surrogate component (WP4a) for the APEX allocation proposal. The surrogate bridges a ~10⁷× speed gap between IAMReX CFD (~4.2 s/step on A40) and RL training requirements. Questions arose from reviewing the WP4a architecture candidates and a prior consultation with Harpreet Sethi (NVIDIA PhysicsNeMo team, email January 5, 2026).

The broader goal: RL controllers for mosquito flight, with future extensions to swarm dynamics and acoustic interactions.

---

## WP2 Resource Estimates

### Confirmed numbers (from `benchmarks/results/tables/resource_projection.csv`)

- Per-simulation cost: **201 A100 GPU-hours**
  - 10M cells, 1.45 s/step (A100, 2.9× bandwidth-limited speedup from measured A40 1.89 s/step)
  - 500,000 total timesteps (5,000 steps/wingbeat × 100 wingbeats)
- WP2 total: **~5,026 GPU-hours** (5 baseline + 20 pilot simulations)
- Typo in earlier draft: 5,006 → correct value is 5,026

### ⚠️ UNRESOLVED: Timestep inconsistency

Two conflicting values in project docs:

| Source | Δt | Steps/wingbeat | Implication |
|---|---|---|---|
| `design.md` line 214 (van Veen et al. 2022) | 1×10⁻⁷ s | ~14,000 | 564 GPU-hr/sim |
| `resource_projection.csv` | ~2.8×10⁻⁷ s | 5,000 | 201 GPU-hr/sim |

If van Veen's timestep is the correct CFL-constrained value, WP2 cost is ~3× higher than estimated. The actual constraint must be computed from:

```
Δt_CFL = CFL × Δx_min / U_max
```

where `Δx_min` is the finest AMR level spacing and `U_max` is the maximum wing tip velocity. **This needs a test run to resolve before submission.**

Note: van Veen et al. used IBAMR on a different geometry — their timestep may not transfer directly to your setup.

---

## WP4a Architecture Decisions

### Architectures to remove from WP4a

Three originally proposed architectures are inappropriate for this problem:

**FNO** (Li et al. 2020, arXiv:2010.08895) — Designed for operator learning: mapping one function space to another (e.g., 64×64 initial condition → 64×64 solution field). Our surrogate maps a fixed-size kinematics vector to a force vector. That is standard regression, not operator learning. Citing FNO for this problem would raise red flags with ML reviewers.

**MeshGraphNet** (Pfaff et al. 2021, ICLR) — Requires mesh connectivity as input and full spatial field values at each node as training labels. Without storing full field snapshots AND their mesh topology, this architecture cannot be trained on integrated force outputs alone.

**True PINN** — Physics-Informed Neural Networks with NS residuals require the network to predict full velocity/pressure fields at collocation points to compute the PDE residual ∂u/∂t + (u·∇)u = −∇p + ν∆u. With only integrated forces as training labels, this is not feasible. Calling the surrogate a "PINN" in the proposal without clarifying this would be misleading.

### Recommended target architecture: Latent dynamics model

A world-model approach (cf. Hafner et al. 2023, DreamerV3, arXiv:2301.04104):

1. **Encoder**: Trained on stored CFD field snapshots. Compresses flow field → small latent vector z (e.g., 64–256 numbers).
2. **Latent dynamics model**: (z_t, wing kinematics command) → (z_{t+1}, forces). This is the surrogate proper, used at RL inference time.
3. **Probe decoder** (optional, for future acoustic work): z → near-field velocity at antenna probe locations.

At RL inference: only the latent dynamics model runs. Full flow fields are never reconstructed. One step = (z_t, kinematics_t) → (z_{t+1}, forces_t).

### Candidate architectures (from Harpreet Sethi, NVIDIA)

Source: Email from Harpreet Sethi (hasethi@nvidia.com), January 5, 2026.

| Architecture | Moving boundary | Vortex structures | Deployment speed | Notes |
|---|---|---|---|---|
| XMeshGraphNet | Hard — graph rebuild each step | Good | Moderate | Best if graph rebuild can be amortized |
| DoMINO | Natural — update point positions | Good | Moderate | Best fit for IBM Lagrangian markers |
| Transolver | Flexible via geometry tokens | Moderate | Moderate | Less proven for rapid motion |
| DeepONet | Natural — kinematics in branch net | Lower resolution | Fast | Best for JAX/MJX deployment |

Harpreet's note: "Graph based might be better for small-scale vortex structures, but it is hard to comment unless I see some simulations."

**Working recommendation**: DoMINO for encoder training (handles moving geometry naturally), DeepONet for latent dynamics model (fastest at RL inference). This is not finalized — depends on answers to open questions below.

### PINN vs physics-informed: a critical distinction

These terms are often conflated. For the proposal, use the right one:

**PINN** (Raissi et al. 2019, *J. Comp. Phys.*) is a specific architecture: the network approximates continuous solution fields u(x,t) and p(x,t) as functions of space and time. The NS PDE residual (∂u/∂t + (u·∇)u = −∇p + ν∆u) is computed via automatic differentiation through the network and minimized as part of the training loss. This requires predicting full continuous fields — it is not applicable when your training labels are integrated forces.

**Physics-informed** (general term) means physics knowledge is used somewhere — in architecture design, feature engineering, or soft loss constraints — without necessarily embedding PDE residuals. All of Harpreet's suggested architectures (XMeshGraphNet, DoMINO, Transolver, DeepONet) are data-driven neural operators that can be made *physics-informed* but are not PINNs.

**Correct framing for the proposal**: *"physics-informed neural operator, implemented in PhysicsNeMo"* — not "PINN."

The three-way taxonomy from the slides (Lai et al. 2025, *Annu. Rev. Condens. Matter Phys.*):

| Approach | Method | Data needed | Our use |
|---|---|---|---|
| Data-driven | Neural operator trained on CFD (DoMINO, FNO) | Large dataset | Primary |
| Physics-informed | PDE residual loss, few/no data (PINN) | Small/none | Not applicable |
| Hybrid | Data + soft physics constraints | Moderate | Preferred |

### Physics soft constraints (for the hybrid approach)

The Sane & Dickinson (2002) quasi-steady decomposition provides an analytical baseline for the hovering regime:

```
F_total(t) = F_translational(t) + F_rotational(t) + F_added_mass(t)
```

where:
- F_trans ∝ ρ U² A · CL(α)  (angle-of-attack dependent lift)
- F_rot ∝ ρ U A c · ω  (rotational contribution at stroke reversal)
- F_added ∝ ρ V · a  (inertial/added mass term)

The network can learn corrections to this baseline — more data-efficient and interpretable than predicting the full force from scratch.

Additional soft loss terms:
- **Periodicity**: |F(t) − F(t+T)| → 0 after transients
- **Stroke symmetry**: For symmetric kinematics, upstroke/downstroke forces should mirror
- **Power balance**: Aerodynamic power F·v > 0 (wing does work on fluid)

**Scope limitation**: The quasi-steady baseline is validated for hovering insects only (Sane & Dickinson 2002). It does not apply to forward flight, maneuvering, or highly unsteady regimes. For those cases the surrogate must learn the full force signal from data.

---

## Data Requirements

### What to store from each CFD simulation

| Data type | Needed for | Storage (20 sims) | Status |
|---|---|---|---|
| Flow field snapshots (subsampled) | Train encoder | 6–32 TB | Not yet collected |
| Integrated forces (CL, CD, CM) | RL reward, surrogate output labels | ~72 MB | Collected |
| Surface pressure at Lagrangian markers | Future acoustic surrogate | ~70 GB | Easy to add |
| Near-field velocity at probe points | Future acoustic surrogate | ~few GB | Easy to add |
| Key-phase volume snapshots (~16/wingbeat) | Scientific validation, figures | ~6 GB | Partial |

**Recommendation**: Add surface pressure at markers and near-field velocity at antenna-range probe points to CFD output now. Cost is negligible; enables future acoustic work without re-running CFD.

### Training paradigm: snapshot-to-snapshot

Each training sample is one timestep transition:

```
(flow_state_t, kinematics_command_t) → (flow_state_{t+1}, forces_t)
```

From 20 simulations × 500k steps = up to 10M training pairs (use a subsampled stride in practice). This is far more data-efficient than full-trajectory training, which would yield only 20 training samples.

The "flow state" between snapshots is represented as latent vector z, not a full field — see encoder above.

---

## Inference Requirements

### Sub-millisecond is not a hard constraint for offline RL training

The real requirement is **GPU-batchable inference across thousands of parallel environments in JAX/MJX**.

With 1,000 parallel environments at 1 ms/step, effective throughput = 1 μs/step equivalent — sufficient for iterative RL research. Example training timelines:

| Surrogate speed | 10⁸ RL steps | Practical? |
|---|---|---|
| CFD (4.2 s/step) | ~13,000 years | No |
| 100 ms/step | ~115 days | No |
| 1 ms/step | ~28 hours | Yes (1 run/day) |
| 100 μs/step | ~2.8 hours | Ideal |

Hard real-time control on physical hardware IS a strict constraint: inference must complete within one wingbeat period (1.4 ms at 717 Hz). That is future scope.

### JAX/MJX deployment

PhysicsNeMo models are PyTorch-based. The deployment path into the MIMIC-MJX RL pipeline (Zakka et al. 2025, arXiv:2502.08844; Macklin 2024, github.com/NVIDIA/warp):

```
PhysicsNeMo (training) → ONNX export → MJX (XLA backend)     ─┐
                       → DLPack/Warp  → MJX-Warp backend      ─┘ → RL training
```

**Recommended hybrid** (from mujoco-warp-integration.md): PhysicsNeMo handles the aerodynamic surrogate; MJX-Warp handles rigid body physics and contacts. They communicate via DLPack zero-copy array transfer (`wp.from_jax()` / `wp.to_jax()`). MJX-Warp is a drop-in backend for MJX — same JAX API, `impl='warp'` flag.

| Metric | MJX (XLA) | MJX-Warp |
|---|---|---|
| Throughput | Baseline | 1.5–2× faster |
| Contact scaling | Fixed shapes (SIMD) | Dynamic contacts (SIMT) |
| Multi-agent scenes | Limited | Much larger |
| Differentiability | Yes | Not yet |

MJX-Warp's dynamic contact handling is important for multi-agent swarm simulation (VNM-Swarm phase). The lack of differentiability is a current limitation — relevant if gradient-based policy optimization through physics is needed.

**Open question for Harpreet**: What is the recommended export path specifically for DoMINO or XMeshGraphNet models into JAX/Warp for batched inference?

---

## Moving Boundary Handling

IAMReX's immersed boundary method naturally separates the problem:

- **Wing surface**: Lagrangian marker point cloud (908 markers for current flat plate; more for realistic wing planform). Positions and forces tracked each timestep by IAMReX.
- **Fluid domain**: Fixed Eulerian AMR grid.

This structure maps directly onto DoMINO's point cloud approach. The `phi_nodal` signed-distance field computed by IAMReX (see `fix-external-geometry-crash` proposal) also provides a geometry encoding on the Eulerian grid that can be used as surrogate input.

**Key unverified claim**: DoMINO handles moving boundaries naturally. This reasoning is based on its point-cloud architecture and Harpreet's recommendation — confirm with him whether it has been benchmarked on *continuously and rapidly moving* geometry (not just parameterized shape variations at rest).

---

## Open Questions (Prioritized)

### Before next Harpreet conversation

1. **Training sample structure**: Does one training sample = (field_t, kinematics_t) → field_{t+1}? What spatial resolution does he expect as input to these architectures? This determines storage requirements.

2. **DoMINO for rapid motion**: Has DoMINO been validated for geometry moving continuously at high speed (wing tip velocity ~3 m/s), or only for parameterized shape changes?

3. **Latent dynamics model in PhysicsNeMo**: Does PhysicsNeMo have existing infrastructure for encoder + latent dynamics models, or does this need custom implementation?

4. **JAX/MJX deployment path**: What is the recommended export path for PhysicsNeMo models into JAX for batched RL inference?

### Before finalizing WP2 cost

5. **Actual CFL-constrained Δt**: Run a short flapping wing test to measure the timestep the solver actually uses. Resolves the 5,000 vs 14,000 steps/wingbeat inconsistency. This could 3× the WP2 cost estimate.

### Before finalizing acoustic surrogate design

6. **Antenna probe placement**: For the acoustic surrogate, probe points for near-field velocity should be placed at antenna-range distances from the wing/body. The relevant quantity for Johnston's organ stimulation is oscillatory particle velocity at the flagellum tip — confirm placement with biology collaborators before committing probe locations in CFD output.

---

## References

### Mosquito biology and aerodynamics

- Bomphrey et al. (2017). Smart wing rotation and trailing-edge vortices enable high frequency mosquito flight. *Nature*, 544, 92–95. [doi:10.1038/nature21727](https://doi.org/10.1038/nature21727) — Source for 717 ± 59 Hz wingbeat frequency, 39° ± 4° stroke amplitude (*C. quinquefasciatus*), Re 50–300, smallest stroke amplitude of any hovering animal.
- Sane & Dickinson (2002). The aerodynamic effects of wing rotation and a revised quasi-steady model of flapping flight. *J. Exp. Biol.*, 205, 1087–1096. [doi:10.1242/jeb.205.8.1087](https://doi.org/10.1242/jeb.205.8.1087) — Quasi-steady force decomposition (F_trans + F_rot + F_added_mass). Validated for hovering only.
- Van Veen et al. (2022). Unsteady aerodynamics of insect wings with rotational stroke accelerations. *J. Fluid Mech.*, 936, A3. [doi:10.1017/jfm.2022.31](https://doi.org/10.1017/jfm.2022.31) — 721 IBAMR CFD simulations used to calibrate an analytical quasi-steady model. They did not train an ML surrogate.
- Somers et al. (2022). Circadian control of audibility in *Anopheles* mating swarms. *Sci. Adv.*, 8(2). [doi:10.1126/sciadv.abl4844](https://doi.org/10.1126/sciadv.abl4844) — *Anopheles gambiae* acoustic mating: males tune wingbeat to ~1.5× female frequency so that quadratic and cubic distortion products in Johnston's organ superimpose ("super distortion"), maximizing female audibility. Male swarm: ~844 Hz, female swarm: ~556 Hz, ratio ~1.53. Johnston's organ detects near-field particle velocity (oscillatory air displacement), not far-field pressure.
- Su et al. (2018). Sex and species specific hearing mechanisms in mosquito flagellar ears. *Nat. Commun.*, 9, 3911. [doi:10.1038/s41467-018-06388-7](https://doi.org/10.1038/s41467-018-06388-7) — Johnston's organ biophysics.

### ML architectures

- Li et al. (2020). Fourier Neural Operator for Parametric PDEs. *arXiv:2010.08895*. [arxiv.org/abs/2010.08895](https://arxiv.org/abs/2010.08895) — FNO. Maps function spaces to function spaces (e.g., spatial field → spatial field). Not appropriate for vector-to-vector regression.
- Pfaff et al. (2020). Learning Mesh-Based Simulation with Graph Networks. *ICLR 2021*. [arxiv.org/abs/2010.03409](https://arxiv.org/abs/2010.03409) — Original MeshGraphNet. XMeshGraphNet is NVIDIA's extension.
- Raissi et al. (2019). Physics-informed neural networks: A deep learning framework for solving forward and inverse problems involving nonlinear PDEs. *J. Comp. Phys.*, 378, 686–707. [doi:10.1016/j.jcp.2018.10.045](https://doi.org/10.1016/j.jcp.2018.10.045) — Defines PINN: network predicts continuous solution fields, PDE residual in training loss. Not the same as "physics-informed" in general.
- Hafner et al. (2023). Mastering Diverse Domains through World Models (DreamerV3). *arXiv:2301.04104*. [arxiv.org/abs/2301.04104](https://arxiv.org/abs/2301.04104) — Latent dynamics model approach for RL.
- Lai et al. (2025). Machine learning for physics: a short primer. *Annu. Rev. Condens. Matter Phys.* [doi:10.1146/annurev-conmatphys-043024-114758](https://doi.org/10.1146/annurev-conmatphys-043024-114758) — Taxonomy of data-driven / physics-informed / hybrid approaches.
- Transolver: ⚠️ *Full citation to be verified* — Transformer-based physics solver, believed 2024.

### Hardware, software, and deployment

- NVIDIA PhysicsNeMo: https://github.com/NVIDIA/physicsnemo
- IAMReX: https://github.com/ruohai0925/IAMReX
- AMReX: https://amrex-codes.github.io/amrex/
- Zakka et al. (2025). MuJoCo Playground. *arXiv:2502.08844*. [arxiv.org/abs/2502.08844](https://arxiv.org/abs/2502.08844) — MJX-Warp drop-in backend for MJX; same JAX API, 1.5–2× faster, dynamic contacts.
- Macklin (2024). NVIDIA Warp. [github.com/NVIDIA/warp](https://github.com/NVIDIA/warp) — DLPack interop with JAX (`wp.from_jax()` / `wp.to_jax()`).
- Zhang et al. (2025). MIMIC-MJX. *arXiv:2511.20532*. [arxiv.org/abs/2511.20532](https://arxiv.org/abs/2511.20532) — Our RL pipeline; the deployment target for the surrogate.

### Personal communications

- Harpreet Sethi (NVIDIA PhysicsNeMo team), email January 5, 2026. Suggested architectures: XMeshGraphNet, DoMINO, Transolver, DeepONet. Raised the larger-timestep question for ML surrogates.

---

## Scientific Validity Flags

*These flag claims in this document that are inferred, estimated, or not yet confirmed by a primary source. Do not use flagged items in the proposal without resolving them first.*

| Claim | Status | Source / Action |
|---|---|---|
| Johnston's organ detects near-field particle velocity | ✅ Verified | Su et al. (2018); Somers et al. (2022) |
| A40→A100 2.9× speedup (memory bandwidth ratio 2039/696) | ✅ Verified | Hardware specs; appropriate for bandwidth-limited CFD |
| Quasi-steady decomposition: F = F_trans + F_rot + F_added | ✅ Verified | Sane & Dickinson (2002) |
| Wagner effect: gradual circulation buildup over chord lengths | ✅ Verified | Classical unsteady aerodynamics |
| Near-field dipole terms decay as 1/r², 1/r³ | ✅ Verified | Acoustic near-field theory |
| Van Veen et al. (2022) calibrated an analytical quasi-steady model (not ML surrogate) | ✅ Verified | Slide deck cites Van Veen et al. (2022) *J. Fluid Mech.* for quasi-steady model training data |
| *Anopheles* males tune to ~1.5× female frequency ("super distortion") | ✅ Verified | Somers et al. (2022) *Sci. Adv.* |
| Quasi-steady model not valid outside hovering regime | ✅ Verified | Sane & Dickinson (2002) explicitly scoped to hovering |
| DoMINO handles rapidly moving boundaries natively | ⚠️ Inferred | Based on point-cloud architecture and Harpreet's recommendation — confirm with Harpreet |
| Transolver full citation | ⚠️ Unverified | Believed 2024 paper — find and verify |