# Test fixtures (force-surrogate)

Synthetic, committed test data so force-surrogate tests run with **no RunAI cluster, GPU, or
AMReX plotfiles** (roadmap CC-2).

- `synthetic_ib_particle.csv` — **synthetic, not a real simulation run.** Mirrors the real
  IAMReX IB-particle CSV schema (29 columns, identical order). All columns are zero except the
  body center (`X,Y,Z = 4,2,4`) and the forces `Fx,Fy,Fz`, which are exact multiples of a round
  reference `F_ref = 100.0` so force coefficients are exact decimals. Load name-based (never
  positional).
- `micro_sweep.json` — a 2-config kinematic micro-sweep (stroke/frequency/pitch); consumed by
  later PRs (PR2+).
