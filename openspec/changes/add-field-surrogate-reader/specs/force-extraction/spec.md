## MODIFIED Requirements

### Requirement: Committed synthetic plotfile gives the yt Eulerian-box adapter cluster-free CI coverage

The test suite SHALL commit a **tiny synthetic single-level AMReX/boxlib plotfile** under `tests/fixtures/`
carrying the **eight components the real wing plotfiles write** (`x/y/z_velocity`, `density`, `tracer`,
`gradpx/gradpy/gradpz`) — so it exercises the same Header-parse path as a real plotfile — of which
`extract_eulerian_box` reads the six it requires; and a CI test SHALL read it through the yt Eulerian-box
adapter `extract_eulerian_box` so the yt-read path is covered **cluster-free**. `extract_eulerian_box` reads
an AMReX plotfile via `yt.load` + `covering_grid(level=0)` + `('boxlib', <name>)` field-tuple access + FP64
unwrap + `max_level == 0` assertion — those calls live in the single shared implementation
`mosquito_cfd.field_surrogate.snapshot.read_field_snapshot`, which `extract_eulerian_box` delegates to
while preserving its signature and returned keys unchanged; prior to this change that actual yt read was exercised **only** by
`requires_plotfile`-marked tests that auto-skip in CI (the real plotfiles live on the cluster Z: drive), so a
regression in the yt-reading layer would not be caught by CI. The fixture SHALL be authored by a committed
deterministic generator (explicit `<f8` byte order; FAB file `Cell_D_00000`) and protected by a
`.gitattributes` **binary** rule (the repo's `core.autocrlf = true` + `* text=auto` would otherwise
CRLF-corrupt the binary FAB), and its velocity field SHALL be analytic (solid-body rotation) so the same
fixture doubles as the LEV wiring's known-answer CI check (`‖ω‖ = 2Ω`, `Q = Ω²`).

#### Scenario: The committed fixture exercises the yt read path in CI

- **Given** the committed synthetic single-level boxlib plotfile fixture and **no** `MOSQUITO_CFD_PLOTFILE_ROOT`
  (CI / off-cluster)
- **When** `extract_eulerian_box` reads it
- **Then** the yt read succeeds cluster-free — `max_level == 0` passes, all six `('boxlib', …)` fields are
  found, and every field array is returned as **bare FP64 numpy** (`dtype == np.float64`, asserted so the
  fixture proves the FP64 read path rather than tripping the adapter's fp32-build guard) indexed
  `[ix, iy, iz]` with the correct per-axis `dx` — so a regression in the field-tuple access, covering-grid
  slice, FP64 unwrap, or level assertion is caught in CI without a cluster (closing the #33 coverage gap)

