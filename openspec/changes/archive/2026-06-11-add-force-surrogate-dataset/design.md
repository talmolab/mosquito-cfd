# Design — add-force-surrogate-dataset

**Roadmap:** `docs/force_surrogate/roadmap.md` row #4 (PR4). **Branch/change-id:** `add-force-surrogate-dataset`. **Issue:** [#6](https://github.com/talmolab/mosquito-cfd/issues/6). Builds on PR1's published `force-surrogate` foundation (normalization, sidecar, provenance, fixtures) and PR2's committed `examples/prelim_sweep/` corpus + manifest.

## API surface

```python
# src/mosquito_cfd/force_surrogate/normalization.py  (extend — CC-3 single source)
@dataclass(frozen=True)
class MomentReference:
    u_tip_max: float; q_tip: float; area: float; length: float; m_ref: float

@dataclass(frozen=True, eq=False)
class MomentCoefficients:
    cf_mx: ...; cf_my: ...; cf_mz: ...

def compute_moment_reference(f_star, phi_amp_deg, r_tip, span, chord, rho=1.0) -> MomentReference:
    """m_ref = q_tip * area * chord  (L = chord, decision D1). q_tip/area as in compute_force_reference."""

def compute_moment_coefficient(mx, my, mz, m_ref) -> MomentCoefficients:
    """cf_m* = M*/m_ref. Raise ValueError on m_ref<=0 or mismatched shapes; empty->empty; NaN propagates."""

# src/mosquito_cfd/force_surrogate/dataset.py  (new — pure, cluster-free)
def build_dataset(manifest_path, csv_paths, *, allow_missing=False) -> tuple[pandas.DataFrame, list[str]]:
    """Returns (frame, dropped_configs). dropped_configs is [] unless allow_missing skipped configs
    (the frame alone has no channel to surface the dropped names to the driver/metadata — D6)."""
def write_dataset(df, parquet_path, units_path) -> None: ...

# scripts/extract_forces.py  (thin driver — no logic)
#   --manifest examples/prelim_sweep/sweep_manifest.json
#   --input-dir <dir>  --csv-name IB_Particle_1.csv  (per-config subdir named by manifest `name`)
#   --out examples/prelim_sweep/dataset.parquet  --units examples/prelim_sweep/dataset.units.json
#   --docker-digest sha256:...  --timestamp <iso>  [--allow-missing]
```

`csv_paths` is an explicit mapping `{config_name -> Path}` (or `{index -> Path}`); the driver builds it from `--input-dir`/template. Tests point one or more configs at the committed `synthetic_ib_particle.csv` (CC-2) — no cluster, GPU, or plotfiles.

## Key decisions

### D1. Moment length scale `L = chord = 1.0` (M_ref = q_tip·S·c)
PR1 defined only the **force** reference (`F_ref = q_tip·S`). A moment coefficient needs an additional length scale: `M_ref = q_tip·S·L`. We choose **`L = chord = 1.0`** (the `CHORD` constant), the standard pitch/aerodynamic-moment normalization (Sane & Dickinson and fixed-wing convention both normalize the pitching-moment coefficient by chord), and the natural partner to `S = π/4·span·chord` (which already carries the chord factor). At the validated point `M_ref = q_tip·S·c = 265.17·2.3562·1.0 ≈ 624.79` — **numerically equal to `F_ref`** because `c=1.0`, but the helper is **parameterized on chord**, so the two are conceptually distinct and a future non-unit chord keeps `M_ref ≠ F_ref` correct. Regression-locked at `rtol=1e-3` (parity with PR1's `F_ref` lock). `q_tip`/`area`/`u_tip_max` are computed by the **same formulas** as `compute_force_reference` (not a second copy) — the helper lives in the same module and is the single source for moment normalization (CC-3).

**Rejected alternatives:** `L = span (3.0)` — suits a roll-type moment about the stroke axis, not the pitch/feathering moment the coefficient is meant to non-dimensionalize; **mean aerodynamic chord of the ellipse (≈0.85·c)** — most rigorous for a fixed wing but introduces a new derived geometric quantity needing its own justification, deferred unless PR6 shows it matters.

**Note (discovered during TDD): `m_ref` scales as chord², not linearly.** Because `area = π/4·span·chord` *already* carries a chord factor, and `L = chord` adds a second, `m_ref = q_tip·area·chord ∝ chord²`. The regression test therefore asserts `m_ref(chord=2) == 4·m_ref(chord=1)` (not 2×), and the robust single-source check is the chord-agnostic equality `m_ref == compute_force_reference(same args).f_ref · chord`. The spec scenario *"Moment reference scales with the chord length scale…"* was corrected from an initial "doubles linearly" wording to this quadratic reality.

### D2. Carry all three moment coefficients `CF_mx/CF_my/CF_mz`; defer the single `CF_m` to PR6
IAMReX computes the moment as **`M = Σ_markers (r − P) × (F·dv)` about the body center `P = kernel.location`**, in the **lab frame** ([`DiffusedIB.cpp:798–801`, `1258`](https://github.com/talmolab/IAMReX) — the `ib_moment[0..2]` written to `Mx/My/Mz`). So `Mx/My/Mz` are **lab-frame** moment components about the body center, **not** a body-frame pitch (feathering) moment about the instantaneous spanwise axis. Designating one as "the pitch moment `CF_m`" requires resolving the wing's axis convention — which the repo's own documentation is inconsistent about (RESULTS.md says "span runs in z" while the figure labels `CF_z` the lift axis) and which issue [#1](https://github.com/talmolab/mosquito-cfd/issues/1) explicitly tracks as an open refactor. The **scientifically honest** choice is therefore to carry **all three** normalized moment coefficients (`CF_mx = Mx/M_ref`, etc.) — zero information loss — and **defer** the single headline `CF_m` designation to PR6, where the predicted-vs-CFD figure makes the physically correct axis unambiguous. The dataset is a superset; PR6 selects.

### D3. Keep all timesteps; tag `phase ∈ [0,1)` and integer `wingbeat`
PR2 runs `N_WINGBEATS = 2` complete beats per config, so the **first** beat may be a startup transient. Two options: (a) drop the startup beat in the extractor, or (b) keep everything and tag each row so downstream can filter. We choose **(b)**. Rationale:
- **No silent truncation.** Dropping data in the extractor is exactly the trap behind issue [#4](https://github.com/talmolab/mosquito-cfd/issues/4): the figure script prints a `(t>0.1)` label while actually masking `t≥0.05` — an undocumented window that misrepresents what was plotted. Keeping every row and exposing `phase`/`wingbeat` makes any later filtering **explicit and visible** in PR5/PR6 (honors the roadmap "no silent caps" standard).
- **Diagnostics.** The transient is useful for sanity checks (e.g. confirming periodicity) and is cheap to keep.
- **Definitions.** `phase = (time · frequency_fstar) mod 1` ∈ [0,1) (fraction through the current wingbeat); `wingbeat = floor(time · frequency_fstar)` (integer cycle index, 0 = first/startup beat). Both are deterministic functions of `time` and the config's `f*`.

### D4. Parquet engine — add `pyarrow`
`dataset.parquet` is the roadmap's named deliverable and the natural Arrow-ecosystem input for PR5 training. pandas 3.0 does **not** vendor a parquet engine (verified: `import pyarrow` and `import fastparquet` both fail in the current env). We add **`pyarrow`** (the standard, best-supported pandas engine) to `[project.dependencies]` and run `uv sync` so `uv.lock` regenerates; CI's `uv sync --frozen` then still holds. `fastparquet` (less universal) and CSV (loses dtype/columnar fidelity and deviates from the named deliverable) were rejected.

### D5. CSV input contract — explicit paths in the library, layout in the driver
PR3's real per-config output layout does not exist yet. To keep the library **pure and testable now**, `build_dataset` takes an **explicit mapping** `{config -> CSV path}` (or DataFrames). The **driver** owns the filesystem convention: `--input-dir/<config_name>/IB_Particle_1.csv` (IAMReX's actual per-run CSV name, per RESULTS.md), overridable via `--csv-name`. PR3 aligns its output directory layout to this convention. This keeps the pure/​I-O split identical to PR2 (`render_inputs` pure text; `generate_sweep` owns disk).

### D6. Missing corpus — hard-fail by default, opt-in `allow_missing`
A manifest config whose CSV is absent (PR3 partially complete, or a 2-config micro-sweep subset run against the 27-config manifest) is a **reproducibility hazard**: a short dataset can masquerade as complete. Default behavior: **raise `ValueError` naming the missing config(s)**. Opt-in `allow_missing=True`: skip the missing configs with a logged `warning` and **return their names** as the second element of `build_dataset`'s `(frame, dropped_configs)` tuple. The driver passes that list into `capture_surrogate_run_metadata(..., extra={"dropped_configs": [...]})`, which merges `extra` via `dict.update` — so the names land at the **top level** of `run_metadata.json` under `dropped_configs` (NOT nested under `extra`; verified at [`metadata.py:211-212`](../../../src/mosquito_cfd/benchmarks/metadata.py#L211-L212)). The truncation is therefore durable and auditable — never silent. (Parity with PR2's `_validate_configs` fail-before-write rigor and the roadmap "no silent caps" standard.) **Why the tuple return:** a bare `-> DataFrame` gives the caller no channel to learn which configs were dropped; the dropped list must be a first-class return value, not buried in a log line.

### D7. Per-config normalization (not a global constant)
`F_ref`/`M_ref` are computed **per config** from that config's kinematics: `compute_force_reference(f_star=frequency_fstar, phi_amp_deg=stroke_amp_deg, r_tip=R_TIP, span=SPAN, chord=CHORD, rho=RHO)` (the helper takes **positional/keyword kinematics+geometry args — there is no `compute_force_reference(config)` overload**; the prose shorthand `compute_force_reference(config).f_ref` used in scenarios is sugar for this full call, and tests must write the full call). So `CF_*` is each config's force divided by **its own** reference — the physically correct non-dimensionalization across a kinematic sweep, and the reason the helper is parameterized (CC-3) rather than a baked-in 624.79. The fixture's round forces/moments (multiples of 100) give exact-decimal coefficients **in the helper unit tests** (where `F_ref=M_ref=100` is passed directly); the **dataset** test asserts the extractor wired the per-config reference correctly — `df.CF_x == Fx / compute_force_reference(...).f_ref` — rather than re-asserting round literals, since a real Aedes config's `F_ref` is not 100. A numeric anchor (`f_ref == pytest.approx(624.79, rel=1e-3)` for the f*=1.0/φ=70 case) is asserted alongside so a regression in the helper cannot pass by recomputing through the same code path.

### D8. Units sidecar — no vocabulary extension (CC-5)
Every measured dataset column is **dimensionless** (`CF_*`, `phase`, `time`, raw `Fx..Mz`, `reynolds`), in **deg** (`stroke_amp_deg`, `pitch_amp_deg`), or **`dimensionless (f*)`** (`frequency_fstar`) — all already in `UNITS_VOCABULARY`. So **no new unit is added** (CC-5: extend only for a genuinely new unit). String columns (`config_name`, `split`) and bookkeeping counts (`index`, `wingbeat`) are **omitted** from the sidecar, mirroring PR2's manifest-units convention (it declares only measured columns).

### D9. CI lint scope — add `scripts/` (ordering trap)
CI currently lints `src/ tests/ examples/prelim_sweep/` only. The new `scripts/extract_forces.py` would otherwise be unlinted. Widen **both** ruff `run` lines (`ruff check` **and** `ruff format --check`) to include `scripts/`. **Ordering hazard (verified):** git does not track empty directories, so on a fresh CI checkout `scripts/` exists **only** once a `.py` file is committed under it; `ruff check` on a *missing* path is `E902` → exit 1 (red CI), while on an *empty* path it is exit 0. A local `ruff check scripts/` against the locally-present-but-empty dir is therefore a **false green**. The CI-widening change MUST land in the same commit as (or a later commit than) the committed `scripts/extract_forces.py`. Scoped deliberately to `scripts/` (created clean here), not the rest of `examples/` — that carries 32 pre-existing ruff violations tracked as a separate follow-up (PR2 tasks.md §7.2). Extend the load-bearing-path comment at `ci.yml:19-20` to name `scripts/` too.

### D10. Commit the units-contract sidecar only; defer the fixture-derived data (scientific honesty)
PR3's real corpus does not exist yet, so the only data PR4 could extract is the **synthetic** `tests/fixtures/synthetic_ib_particle.csv` (round forces, *not physics*). Committing a `dataset.parquet` + `run_metadata.json` built from it into `examples/prelim_sweep/` would plant an artifact that **looks** like real CFD output (plausible `reynolds`/`CF_*` columns, a `sha256:` digest in the metadata) — a scientific-honesty hazard, and `capture_surrogate_run_metadata` *requires* a real container digest that a fixture build never legitimately has (it would manufacture false provenance). **Decision (option b):**
- **Commit `examples/prelim_sweep/dataset.units.json`** — the column→unit map. This is **pure schema metadata** (defined from a static `_DATASET_UNITS` constant, like PR2's `_MANIFEST_UNITS`): it carries **no fabricated physics** (no `reynolds`/`CF_*` values, no digest), so it cannot masquerade as CFD output, yet it gives PR5 a **committed, machine-readable, `read_units_sidecar`-validatable contract** to develop against — making the "schema/units contract" the proposal promises actually real rather than prose-only.
- **Do NOT commit** `dataset.parquet` or `run_metadata.json` — these are the data + its provenance, which only become honest once PR3's real corpus is run through the committed driver (with the genuine `:fp64` digest).
- The full schema lives in the spec (normative) + a `examples/prelim_sweep/README.md` dataset section (columns via the units sidecar + spec pointer, the `phase`/`wingbeat` semantics, and the one-line regenerate command). Tests exercise `write_dataset`/the driver by generating the parquet into `tmp_path` and validating round-trip — never committed.

This honors CC-4/scientific-honesty and the "no silent caps" standard. *(This is a deviation from the literal roadmap/issue wording "OUTPUT: dataset.parquet" — see proposal `### Why no committed dataset artifact (decision D10)`; the roadmap row #4 + Output bullet are updated to "data + provenance committed when PR3's corpus lands; PR4 commits the extractor + units contract" for traceability. User-confirmed at approval.)*

### D11. `pyarrow` ships into the `:python` post-processing image (acknowledged, intended)
Adding `pyarrow` to `[project.dependencies]` means `docker/Dockerfile.python` (which runs `uv sync --frozen`) installs it into the `:python` post-processing image automatically — no Dockerfile edit, and **desirable** (that image can read the parquet). The `:fp64`/`:fp32` solver images do not `uv sync` the project deps and are unaffected (no FP64/pin regression; this PR touches no Dockerfile). The `:python` image grows ~100 MB (Arrow C++); acceptable. `uv.lock` **must** be regenerated and committed in the same change or `uv sync --frozen` breaks in **all three** places that run it: CI's test job (`ci.yml:37`), the `:python` image build (`Dockerfile.python:38`), **and** the `:fp64` solver image build (`Dockerfile.fp64:127`) — `--frozen` rejects any pyproject/lock mismatch *before* resolving, so even the FP64 image (which never imports pyarrow at runtime) fails to build on a stale lock. Prove consistency with `uv lock --check` before committing, not a same-machine `uv sync --frozen` (which trivially passes right after `uv sync` regenerated the lock).

## Test strategy (TDD, cluster-free — CC-2)

All tests run against the committed `tests/fixtures/synthetic_ib_particle.csv` (extended with round moments) and a manifest (the committed `sweep_manifest.json` and/or a tiny temp manifest pointing configs at the fixture CSV). No cluster, GPU, or plotfiles.

1. **Moment normalization** (`test_force_surrogate_normalization.py` additions): `m_ref ≈ 624.79` at the validated point (`rtol=1e-3`); `cf_m* = M*/m_ref` element-wise, shape-preserving; `m_ref<=0` raises; mismatched moment shapes raise; empty→empty; NaN propagates; `compute_moment_coefficient(fixture moments, 100.0)` gives the exact decimals.
2. **Dataset extraction** (`test_force_surrogate_dataset.py`): one row per (config×timestep); columns exactly the documented schema; `CF_x == Fx / compute_force_reference(...).f_ref` and `CF_mx == Mx / compute_moment_reference(...).m_ref` (extractor reused the single source, full positional call) with a numeric anchor on `f_ref`; **exact** `phase`/`wingbeat` arrays for the f*=1.0 fixture (`phase = [0, .25, .5, .75, 0.0]`, `wingbeat = [0,0,0,0,1]`) — pinning the `time·f*=1.0 → phase=0.0, wingbeat=1` boundary; empty-CSV config → zero rows; held-out `split` carried through; name-based parse (column-reordered CSV still maps); missing CSV raises by default; `allow_missing=True` returns `(df, dropped)` and emits the present configs.
3. **Sidecar + provenance**: `dataset.units.json` round-trips via `read_units_sidecar`, maps each measured column correctly, and includes **all** measured columns (inverse check); `run_metadata.json` records the digest + caller timestamp and the **top-level** `dropped_configs` (passed via `extra=`); a mutable tag / missing digest raises (inherited from `capture_surrogate_run_metadata`).
4. **Parquet round-trip** (into `tmp_path`, never committed — D10): `write_dataset` then `pandas.read_parquet` returns an **equal frame**. **No byte-equality test** on the parquet — pyarrow output is not byte-reproducible across versions/platforms (`created_by`/statistics metadata); reproducibility is asserted at the schema+value level only. **Cross-platform/pandas-3.0 dtype discipline** (the real flakiness, not float64): assert float64 **explicitly** on coefficient/raw columns and **int64** on `wingbeat`; the string columns (`config_name`/`split`) can round-trip as `object` ↔ `string[pyarrow]` under pandas 3.0, so compare them with `check_dtype=False` (or pin them to `object` on build) and `reset_index(drop=True)` both frames before `assert_frame_equal` so a non-default index can't break equality.
5. **Driver smoke test**: load `scripts/extract_forces.py` via `importlib.util.spec_from_file_location` (mirroring PR2's `test_driver_smoke`), run `main()` into `tmp_path` with `--input-dir` pointing at a fixture-derived tree + a `sha256:` digest, assert exit 0 and that the parquet/units/metadata are written and re-read.

**Cross-platform artifacts:** add `*.parquet binary` to `.gitattributes` (currently absent; the existing `* text=auto` would otherwise heuristically normalize a committed binary) so any *future* committed parquet (PR3+) is never EOL-munged. The `.json` sidecars are covered by the existing `*.json text eol=lf` rule.

**Docs touched (anti-drift):** the 22-column schema is normative **only** in the spec's *"Columns are the documented schema"* scenario; `proposal.md`/`design.md`/the `prelim_sweep` README reference it rather than re-listing (the README leans on the `dataset.units.json` contract + a spec pointer). `openspec/project.md`'s `src/` tree is refreshed to add `force_surrogate/` (PR1/PR2, currently missing) + `scripts/`, and the examples list to add `prelim_sweep/` — stopping the 2-PR drift rather than compounding it. The root `README.md` Directory Structure gains a `scripts/` line.
