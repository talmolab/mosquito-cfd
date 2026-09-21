## MODIFIED Requirements

### Requirement: LEV vorticity / Q-criterion diagnostic (reported, not gated)

The analysis SHALL provide **pure** functions computing the **vorticity magnitude** (`‖∇×u‖`) and the
**Q-criterion** (`Q = ½(‖Ω‖² − ‖S‖²)`, the half-difference convention, where Ω/S are the antisymmetric/
symmetric parts of ∇**u**) from a 3-D velocity field on a uniform grid, for the leading-edge-vortex (LEV)
"resolved/present" diagnostic. They SHALL accept **per-axis grid spacing** (`dx` as a scalar for an
isotropic grid **or** a `(dx, dy, dz)` triple), passing per-axis spacing to the gradient so an anisotropic
grid is not silently mis-differentiated. These SHALL be **reported**, never a magic-number pass/fail gate.
They SHALL be verified against **known analytic** answers on synthetic fields (cluster-free).

The yt plotfile→velocity-field extraction and the actual "LEV present at medium, weak/absent at coarse"
call — deferred to T3b in T3a — SHALL now be delivered by **reusing** the existing yt Eulerian-box adapter
`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` (which reads the level-0 covering grid into
FP64 `u, v, w` arrays indexed `[ix, iy, iz]` plus per-axis `dx`), composed with the LEV pure functions
(no *second* plotfile reader, no re-derivation — `extract_eulerian_box` remains the LEV wiring's entry
point and delegates to the single shared implementation in
`mosquito_cfd.field_surrogate.snapshot.read_field_snapshot`). A thin composition
`wing_lev_report(plotfile_path, *, lo, hi)`
SHALL extract the field over a **required, pinned wing near-field sub-box** (`lo/hi`; a domain-wide
reduction is forbidden — dominated by far-field noise and the grid-tied IB marker shell), evaluate the LEV
functions over the box **interior** (`[1:-1,…]`; boundary planes are one-sided lower-order), and report a
**resolution-fair** primary descriptor — the integrated positive Q over the box
(`q_pos_vol = Σ max(Q, 0)·dx·dy·dz`) and the positive-Q volume fraction `q_pos_frac` — alongside the peak
`‖ω‖` / peak `Q` reported **secondarily with an explicit resolution caveat**. The analysis SHALL be at
**mid-stroke `t ≈ 0.5`** (maximum stroke velocity `φ̇`, `plt01000`) — the most LEV-discriminating phase;
`t = 0.25` (stroke reversal, wing momentarily stopped) is **not** used. The plotfile SHALL be selected **by
physical time** (`current_time ≈ 0.5`), not by the `plt01000` name (a run-time `dt` reduction moves the
name↔time mapping). The near-field box SHALL be **derived from the plotfile's wing-marker bounding box**
(`particle_position_{x,y,z}`) + a fixed physical margin (a hard-pinned literal is forbidden — it is
phase-specific and would clip the mid-stroke wing, whose tip reaches `y ≈ 3.475`; an illustrative box is
`lo = (2.5, 0, 3)`, `hi = (5.5, 4, 5)`), **recorded verbatim in RESULTS**, **fixed** and identical on both
grids at the same phase, and the test SHALL **assert the marker bbox fits inside `lo/hi`**. **Honest scope:**
the box trims the far-field so the reduction is wing-region-defined and reproducible, but it does **not**
fully exclude the IB-regularization shell co-located with the wing (contamination **phase-amplified at
mid-stroke**), so `peak_q`/`peak_vorticity` remain shell-contaminated (secondary) and a **downstream-offset
box** is also reported to isolate shed vorticity; even `q_pos_vol` is **not resolution-invariant** (a
marginally-resolved coarse core under-estimates it) —
so a coarse→medium `q_pos_vol` **increase is a lower bound on LEV growth, not proof of present-vs-absent**;
RESULTS states this for both `q_pos_vol` and peak `Q`. It SHALL return a plain dict carrying **no**
`*_pass`/`converged`/`present` verdict key — the coarse↔medium contrast is **reported** (interpreted in
RESULTS prose), never a thresholded gate or a directional assertion. The two plotfiles SHALL be compared at
the **same phase**, guarded by asserting their `current_time` agree to within `0.5·min(dt_coarse, dt_medium)`.
The wiring SHALL be covered **both** by a `@pytest.mark.requires_plotfile` test against the real coarse ↔
medium plotfiles (auto-skipped in CI when `MOSQUITO_CFD_PLOTFILE_ROOT` is absent) **and** by a **committed
synthetic single-level AMReX/boxlib plotfile fixture** carrying an analytic field, so the
`extract_eulerian_box → lev` yt-read path is exercised cluster-free in CI.

#### Scenario: Solid-body rotation gives the analytic vorticity and Q

- **Given** a uniform grid carrying solid-body rotation `(u, v, w) = (−Ω·y, Ω·x, 0)`
- **When** `vorticity_magnitude` and `q_criterion` are evaluated on the interior
- **Then** `‖∇×u‖ = 2Ω` uniformly and `Q = Ω²` (pure rotation, strain `S = 0`, `Q = ½‖Ω_tensor‖² = ½·2Ω²`),
  matching the analytic values to floating tolerance; a pure-shear field `(γ·y, 0, 0)` gives `|ω| = γ` and
  `Q = 0` (rotation and strain cancel)

#### Scenario: Reported, not gated; anisotropic spacing honored; degenerate input guarded

- **Given** the LEV functions
- **When** they are evaluated
- **Then** on a uniform (zero-gradient) field they return `|ω| = 0` / `Q = 0` as **reported** arrays with no
  pass/fail verdict; on an anisotropic grid a `(dx, dy, dz)` triple yields the correct per-axis-differentiated
  curl (a scalar `dx` on a truly anisotropic grid would be wrong — hence per-axis spacing is accepted); and a
  field with fewer than 3 points on any axis raises a clear `ValueError` (a centred gradient needs ≥ 3
  points), never a silent degenerate result

#### Scenario: LEV wiring reuses the adapter and reports a resolution-fair coarse↔medium contrast (no directional gate)

- **Given** new-convention coarse (Δx = 0.125) and medium (Δx = 0.0625) wing plotfiles at **mid-stroke
  `t ≈ 0.5`** (selected by physical `current_time`, not the `plt01000` name; single-level, carrying the
  `('boxlib', {x,y,z}_velocity)` + `('boxlib', gradp{x,y,z})` fields, `init_iter = 2` so the velocity is
  non-zero) available under `MOSQUITO_CFD_PLOTFILE_ROOT`, and the **pinned** wing near-field box `lo/hi`
- **When** `wing_lev_report` extracts each field via `extract_eulerian_box` (reused, not re-implemented) over
  the near-field box and evaluates `vorticity_magnitude` / `q_criterion` with the adapter's per-axis `dx`
- **Then** for each grid it returns a report-only dict `{peak_vorticity, peak_q, q_pos_vol, q_pos_frac, dx,
  phase_time}` with **no** verdict key; the test (`@pytest.mark.requires_plotfile`, auto-skipping in CI)
  asserts both plotfiles share the same phase (`phase_time` within `0.5·min(dt_coarse, dt_medium)`), both
  grids give **finite, positive** `peak_vorticity`/`peak_q`/`q_pos_vol` (a coherent LEV core exists on both),
  and the pinned per-axis `dx` matches each grid — it does **not** assert `Q_medium > Q_coarse` (a resolution
  artifact, not physics); the "present at medium vs weak/absent at coarse" reading is reported via the
  `q_pos_vol`/`q_pos_frac` contrast (a `q_pos_vol` increase being a *lower bound* on LEV growth) and
  interpreted in RESULTS, not gated

#### Scenario: Committed synthetic plotfile gives the LEV wiring cluster-free CI coverage

- **Given** a committed tiny single-level AMReX/boxlib plotfile fixture (box ≥ 5³ so ≥ 3 interior points per
  axis) carrying an analytic solid-body-rotation velocity field (`(−Ω·y, Ω·x, 0)`) plus constant `gradp`,
  authored by a committed deterministic generator with explicit `<f8` byte order
- **When** the LEV composition reads it via `extract_eulerian_box` and computes the interior descriptors —
  with **no** `MOSQUITO_CFD_PLOTFILE_ROOT` and **no** cluster access
- **Then** the wiring runs in CI and reproduces the known analytic `‖ω‖ = 2Ω`, `Q = Ω²` to floating tolerance
  **and the exact resolution-fair descriptors** `q_pos_frac = 1` and `q_pos_vol = Ω²·N_interior·dx·dy·dz`
  (the exact value pins the volume Jacobian a bare `> 0` would miss; solid-body rotation is linear so
  `np.gradient` is exact on the interior), the adapter returns **bare FP64** arrays (`dtype == np.float64`,
  asserted separately so the fixture proves the FP64 read path rather than tripping the fp32-build guard),
  the returned report dict carries **no** verdict key, and the fixture is regenerable (generator output
  matches the committed bytes) — proving the `extract_eulerian_box → lev` yt-read path (field-tuple access,
  covering grid, FP64 unwrap, `max_level == 0`) end-to-end without a cluster

