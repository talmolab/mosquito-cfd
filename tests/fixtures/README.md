# Test fixtures

Synthetic, committed test data so tests run with **no RunAI cluster, GPU, or real AMReX
plotfiles** (roadmap CC-2 / CC-F4).

- `synthetic_ib_particle.csv` — **synthetic, not a real simulation run.** Mirrors the real
  IAMReX IB-particle CSV schema (29 columns, identical order). All columns are zero except the
  body center (`X,Y,Z = 4,2,4`), the forces `Fx,Fy,Fz`, and the moments `Mx,My,Mz` — both of
  which are exact multiples of a round reference (`F_ref = M_ref = 100.0`) so force and moment
  coefficients are exact decimals. Load name-based (never positional).
- `micro_sweep.json` — a 2-config kinematic micro-sweep (stroke/frequency/pitch); consumed by
  later PRs (PR2+).
- `lev_boxlib_plt/` — a tiny synthetic **single-level AMReX/boxlib plotfile**: 6³ cells,
  `dx = 1`, domain `[0, 6]³`, `current_time = 0.5`, `max_level = 0`. Carries the eight
  `('boxlib', …)` components a real wing plotfile writes (`x/y/z_velocity`, `density`, `tracer`,
  `gradpx/gradpy/gradpz`), so it exercises the same Header-parse path. Velocity is analytic
  solid-body rotation `(-Ωy, Ωx, 0)` with `Ω = 1.3`, giving the LEV reduction a known answer
  (`‖ω‖ = 2Ω`, `Q = Ω²`). This is the cluster-free backing for the repository's single
  Eulerian-box covering-grid read path
  (`mosquito_cfd.field_surrogate.snapshot.read_field_snapshot`, reached by
  `benchmarks.stress_integral.extract_eulerian_box`) — roadmap CC-F4. Closes issue #33.
- `make_lev_boxlib_fixture.py` — the committed deterministic generator for the above.
  Regenerate with `uv run python tests/fixtures/make_lev_boxlib_fixture.py`; it is byte-identical
  across platforms (text files written with explicit LF), and `test_fixture_is_regenerable`
  enforces that. Its `fields=` argument writes a deliberately incomplete plotfile, which is how
  the reader's absent-field error path is tested. The binary FAB is protected from CRLF
  corruption by a `tests/fixtures/lev_boxlib_plt/** -text` rule in `.gitattributes`; a **new**
  committed plotfile fixture would need its own rule.
