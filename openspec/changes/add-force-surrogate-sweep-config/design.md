# Design — add-force-surrogate-sweep-config

**Roadmap:** `docs/force_surrogate/roadmap.md` row #2 (PR2). **Branch/change-id:** `add-force-surrogate-sweep-config`. Builds on PR1's published `force-surrogate` capability.

## API surface

```python
# src/mosquito_cfd/force_surrogate/sweep.py
def build_kinematic_grid(
    stroke_amp_deg: Sequence[float] = AEDES_STROKE_AMP_DEG,   # (35, 45, 55)
    frequency_fstar: Sequence[float] = AEDES_FREQUENCY_FSTAR, # (0.85, 1.0, 1.15)
    pitch_amp_deg: Sequence[float] = AEDES_PITCH_AMP_DEG,     # (30, 45, 60)
) -> list[dict]:                # 27 dicts, keys {stroke_amp_deg, frequency_fstar, pitch_amp_deg}
    ...

def compute_reynolds(stroke_amp_deg, frequency_fstar, nu_star, r_mid=R_MID) -> float:
    """Re = 2*pi*frequency_fstar*radians(stroke_amp_deg)*r_mid / nu_star.  (r_mid, NOT r_tip.)"""

def derive_run_duration(frequency_fstar, n_wingbeats=N_WINGBEATS, dt=DT) -> tuple[int, float]:
    """stop_time = n_wingbeats/frequency_fstar; max_step = round(stop_time/dt). Returns (max_step, stop_time)."""

def select_holdout(configs, n_holdout=N_HOLDOUT, seed=HOLDOUT_SEED) -> list[int]:
    """Deterministic non-corner holdout indices via numpy.random.default_rng(seed)."""

def render_inputs(base_text, *, stroke_amp_deg, frequency_fstar, pitch_amp_deg,
                  max_step, stop_time, plot_int=-1) -> str:
    """Key-based IAMReX-inputs rewrite: change only the named keys, preserve everything else."""

def generate_sweep(base_inputs_path, output_dir, *, configs=None, n_wingbeats=N_WINGBEATS,
                   nu_star=VALIDATED_NU_STAR, seed=HOLDOUT_SEED, timestamp,
                   dt=DT) -> dict:
    """Write 27 inputs + sweep_manifest.json + sweep_manifest.units.json; return the manifest dict."""
```

`configs=None` ⇒ `build_kinematic_grid()`; passing a list (e.g. the 2-config `micro_sweep.json`) drives a smaller sweep for tests (CC-2).

## Key decisions

### D1. CC-7 — hold ν\* fixed (Re varies), not Re fixed
The roadmap defers the Reynolds policy to PR2. We **hold `ns.vel_visc_coef = 0.115` fixed** for all 27 configs; Re ranges ~43–90 as a deterministic function of the swept φ, f\* (`Re = 2π·f*·rad(φ)·r_mid/ν*`). Reasoning:
- **Well-posed map, no hidden variable.** With ν\* fixed, Re is a pure function of the swept inputs, so the surrogate's `(φ, f*, α) → CF` map stays single-valued. Holding Re fixed would make ν\* a 4th per-config quantity that varies but is invisible to the surrogate inputs — a hidden confounder.
- **Biological fidelity.** In real flight Re co-varies with kinematics; the corpus should sample the regime as it actually occurs.
- **Provenance / testability.** Every generated input file then differs from the base in **only** the swept/derived keys; ν\* is constant, so the "differs-only" guarantee is clean. Holding Re fixed would perturb `vel_visc_coef` in all 26 non-validated configs onto unvalidated viscosities.

Per-config Re is recorded in the manifest either way, so a downstream consumer can see the Re range.

### D2. Reynolds uses the midspan arm `r_mid = 1.5`, not `R_TIP = 3.0`
PR1's `constants.py` already warns that `R_TIP=3.0` is the **force-normalization** arm while the midspan arm `r_mid=1.5` is the **viscous/Reynolds** arm (per `RESULTS.md`), and must not be conflated. `compute_reynolds` is therefore a **separate** helper (it does **not** reuse `compute_force_reference`'s `u_tip_max`, which is built on `R_TIP`). Regression check: `compute_reynolds(70, 1.0, 0.115)` ≈ 100, matching the `inputs.3d.validation` header comment (`V_tip*≈11.5, ν*=11.5/100=0.115`). We add `R_MID = 1.5` to `constants.py` so the arm is named, not a magic number — **and update the existing `R_TIP`-vs-`r_mid` comment (constants.py:13–15) to reference the new `R_MID` symbol** so the comment and the constant don't describe the same quantity two ways. `compute_reynolds` raises `ValueError` on `nu_star <= 0` (parity with PR1's `compute_force_coefficients` non-positive-reference guard).

### D3. Run duration scaled to whole wingbeats (N=2)
The base run is 1 wingbeat (2000 steps, `stop_time=1.0`, `dt=5e-4`) at f\*=1.0. At f\*=0.85 a fixed `stop_time=1.0` would cover only **0.85** of a wingbeat — too short to extract a periodic force cycle. We scale per config to cover `N_WINGBEATS=2` complete beats: `stop_time = N/f*`, `max_step = round(stop_time/dt)`, `dt` unchanged. Duration is a deterministic function of the swept f\* (two configs with equal f\* get equal duration), so the "differs-only" guarantee holds with `max_step`/`stop_time` as **derived** keys. CFL is safe: every swept U_tip is below the validated φ=70° point's, so the validated `dt` stays conservative. N is a parameter (default 2) recorded in the manifest.

### D4. Held-out split — seeded, non-corner, label-only (CC-4)
All 27 configs are **generated and (in PR3) run** — the held-out set is the CFD ground truth the figure plots against. Holdout is therefore a **training-exclusion label**, never an exclusion from the corpus. We pick `N_HOLDOUT=6` via `numpy.random.default_rng(seed)` from the **non-corner** eligible set (a corner = stroke∈{35,55} **and** f\*∈{0.85,1.15} **and** pitch∈{30,60}; 8 corners, 19 eligible) so held-out points have at least one param at a mid level and are interpolatable. `numpy.random.default_rng` (PCG64) has a stability guarantee across numpy versions, but the **eligible indices are assembled into a sorted list before sampling** — never a Python `set`/`dict` whose iteration order is hash-seed-dependent — so the selection is reproducible independent of `PYTHONHASHSEED`. `select_holdout` raises `ValueError` when `n_holdout` exceeds the eligible count (e.g. the 2-config micro-sweep with the default 6) rather than sampling with replacement. The seed and the resulting config names are recorded in the manifest; the same seed reproduces the same split.

### D5. Provenance in a separate sidecar, without a docker digest (PR2 runs no container)
The roadmap's `run_metadata.json` (CC-1) — container digest + IAMReX commit + inputs hash + git SHA + caller timestamp — is emitted by the stages that **run** the image (PR3 sweep, PR4 dataset, PR5 training) via PR1's `capture_surrogate_run_metadata`, which **requires** a `sha256:` digest. PR2 only *generates* inputs; it invokes no container and has no digest. Forcing a placeholder digest would record a false provenance, so PR2 deliberately does **not** call `capture_surrogate_run_metadata`.

Provenance is written to a **separate `sweep_provenance.json`** sidecar — not embedded in `sweep_manifest.json` — for a specific reproducibility reason: it records `git_commit` (`get_git_info()["commit"]`), which is **inherently non-reproducible** (the committed corpus is generated at one SHA, but CI regenerates it after checkout at a *different* SHA). If `git_commit` lived in the manifest, the byte-identity regeneration test (CC-1, test 4.1) could never pass cross-commit. Splitting it out keeps `sweep_manifest.json` a **purely deterministic** config description (no git, no `uuid4`, no wall-clock) that *is* byte-reproducible, while `sweep_provenance.json` carries the environmental fields (`tool`, the **caller-supplied** `generated_at`, `git_commit`, `base_inputs{path, sha256}`) and is explicitly **excluded** from the byte-identity guarantee. The per-run digest is PR3's responsibility. (`base_inputs.path` is stored as a POSIX relative path via `Path(...).as_posix()` so the committed sidecar is identical on Windows and Linux.)

### Why a separate provenance file instead of an in-manifest `provenance` block (deviation from the pre-implementation design)?
The pre-implementation design put a `provenance` block (including `git_commit`) inside `sweep_manifest.json` and asserted the whole manifest was byte-reproducible. Those two are contradictory: `git_commit` changes between the authoring checkout and the CI checkout, so an in-manifest git SHA defeats `test_committed_sweep_matches_regeneration`. The split (manifest = deterministic config; `sweep_provenance.json` = environmental, not byte-compared) resolves the contradiction while preserving every field. This was caught while wiring the byte-identity test.

### D6. Key-based inputs rewrite (minimal diff) — exact-key, LF, deterministic formatting
`render_inputs` operates on the base file's text line-by-line: for each line whose **full key** (the token left of `=`, stripped) **exactly equals** a targeted key, it substitutes the new value while preserving the left-hand text up to and including the `=`-and-alignment and any trailing inline comment; all other lines (comments, blanks, unrelated keys) pass through unchanged. **Exact-key match, not prefix:** the base contains `particle_inputs.kinematics_deviation_amp` alongside the swept `..._stroke_amp`/`..._pitch_amp`/`..._frequency`, so a `startswith("particle_inputs.kinematics_")` matcher would corrupt `deviation_amp` — the matcher compares the whole key. Keys touched: `particle_inputs.kinematics_stroke_amp`, `particle_inputs.kinematics_frequency`, `particle_inputs.kinematics_pitch_amp`, `max_step`, `stop_time`, `amr.plot_int`. If a targeted key is absent from the base, `render_inputs` raises rather than silently no-op'ing (guards against base-file drift).

**Determinism (CC-1, cross-platform).** Two concerns make the committed corpus reproducible on Windows (dev) and Linux (CI):
- **Newlines:** `render_inputs` joins lines with `"\n"` (it is newline-neutral — it cannot emit `\r` unless its input has one, which the LF base never does). The real translation risk is the **write**: `generate_sweep` writes every file with `open(path, "w", encoding="utf-8", newline="")` (the `newline=""` disables Python's platform translation, so `\n` stays `\n` on Windows instead of becoming `\r\n`). The guard test therefore reads a **written file as bytes** and asserts no `\r` (targeting the write layer, not the string builder). This is paired with a `.gitattributes` rule `examples/**/inputs.3d.* text eol=lf` to make the LF pin **explicit** for the extension-less committed decks: they are already LF today via the catch-all `* text=auto`, but the explicit `eol=lf` removes the dependence on that heuristic. The rule also matches the pre-existing `examples/**/inputs.3d.*` decks (`flapping_wing`, `heaving_ellipsoid`) — a verified no-op on their bytes (they are already LF in the index), so no `git add --renormalize` of existing files is needed.
- **Float→string formatting:** numeric values are written with Python's default `str()` — the shortest round-trippable `repr` for floats (`str(0.85) == "0.85"`, `str(35.0) == "35.0"`, `str(2/0.85) == "2.3529411764705883"`), platform-independent and stable across CPython 3.11+ — and plain `str(int)` for counts (`max_step`, `plot_int`). A test pins the exact rendered substrings for a representative config so byte-identity is intentional, not incidental. The same formatting and `sort_keys=True, indent=2, ensure_ascii=False` apply to the manifest JSON.

### D8. Caller-supplied configs are validated
`generate_sweep` (and the grid builder for custom levels) validate the config list before writing anything: an **empty list**, a dict **missing** a required key (`stroke_amp_deg`/`frequency_fstar`/`pitch_amp_deg`), or a dict with an **unknown** key raises `ValueError` naming the offending config/key. This gives the CC-2 public entry point (the `micro_sweep.json` path) a defined contract, matching the error-path rigor PR1 set for `compute_force_coefficients`/`write_units_sidecar`. The 2-config micro-sweep test drives `generate_sweep` with `n_holdout=0` (its eligible set is too small for the default 6); the `n_holdout > eligible` guard (D4) is exercised separately.

### D7. Manifest + units + provenance schema
`generate_sweep` writes three artifacts (and returns the manifest dict):
- **`sweep_manifest.json`** (deterministic, byte-reproducible): `schema_version`, `reynolds_policy="nu_star_fixed"`, `nu_star`, `r_mid`, `dt`, `n_wingbeats`, `grid{stroke_amp_deg[], frequency_fstar[], pitch_amp_deg[]}`, `holdout{seed, n_holdout, config_names[]}`, and `configs[]` (each: `index, name, input_file, stroke_amp_deg, frequency_fstar, pitch_amp_deg, nu_star, reynolds, max_step, stop_time, plot_int, split`).
- **`sweep_manifest.units.json`** (deterministic, via `write_units_sidecar`): the measured columns `stroke_amp_deg→deg`, `pitch_amp_deg→deg`, `frequency_fstar→"dimensionless (f*)"`, `nu_star→dimensionless`, `reynolds→dimensionless`, `stop_time→dimensionless`. Bookkeeping fields (`index`, `max_step`, `plot_int`) are not measured quantities and are omitted.
- **`sweep_provenance.json`** (environmental, **not** byte-compared — see D5): `tool`, `generated_at` (caller ISO), `git_commit`, `base_inputs{path (POSIX-relative), sha256}`.

See D5 for why provenance is a separate file.

**Canonical ordering & float serialization (cross-PR contract).** `configs[]` is emitted in **`itertools.product(stroke, freq, pitch)` C-order** (stroke outermost, pitch innermost), with `index` = list position. Input files are named `inputs.3d.s{φ:int}_f{f*×100:03d}_p{α:int}` — the **3-digit zero-pad on f\*×100** (`085`/`100`/`115`) makes the lexicographic filename sort *identical* to the `configs[]` order (verified: `s35_f085_p30 … s55_f115_p60`), so PR3 (filename glob) and PR4 (manifest order) agree. `reynolds` is written by plain `json.dump` (Python's canonical shortest-`repr`, e.g. `42.5537291206389`) — never `round()`/`f"{:.Nf}"`, which would silently truncate the value PR4 consumes — and `sort_keys=True, indent=2, ensure_ascii=False` fixes dict-key order; together these make the manifest byte-reproducible *and* canonical (not merely self-consistent).

### D9. CI lint scope — widen to the new surfaces only
CI currently lints `src/` only, so the new driver (`examples/prelim_sweep/generate_sweep.py`) and test file would never be CI-enforced. We widen `ci.yml`'s lint job to `src/ tests/ examples/prelim_sweep/`. We deliberately do **not** widen to all of `examples/`: a `ruff check examples/` today reports **32 errors** and `ruff format --check examples/` flags **7 files** — all in unrelated scripts (3 under `flapping_wing/`, 2 under `flow_past_sphere/`, 2 under `heaving_ellipsoid/`). Linting the whole tree would turn CI red on pre-existing debt outside this PR's scope; cleaning those files is a separate docs/lint PR (task 7.2). `tests/` already passes `ruff check` + `ruff format --check`, so adding it is free. ruff inspects only `.py`, so the 27 `inputs.3d.*` decks and the JSON sidecars under `examples/prelim_sweep/` are not linted. The `ci.yml` edit lands in **commit 2** (the commit that creates `examples/prelim_sweep/`), because `ruff … examples/prelim_sweep/` would error on a missing path if it landed in commit 1.

## Out of scope
Cluster/RunAI runs (PR3), plotfile/velocity-field reading, the forces→parquet extractor (PR4), training (PR5), the evidence figure (PR6), RL, and any Docker image digest in PR2 metadata. Full `examples/` lint cleanup (task 7.2). Force-only (`amr.plot_int=-1` throughout).
