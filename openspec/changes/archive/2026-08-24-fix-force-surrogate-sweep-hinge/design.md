# Design: hinge-geometry regression guard + wing-phase diagnostic

## D1. Geometric-consistency guard (replaces trust in byte-identity alone)

**Problem it fixes:** `test_committed_sweep_matches_regeneration` and the pilot's deck-invariance
test both verify a deck is byte-identical to *something else already committed*. Neither test
knows what a *correct* hinge value looks like — a byte-identical wrong value is invisible to them
forever. That's exactly how this bug survived a month plus a full corpus regeneration.

**Approach:** compute the wing's own span extent directly from `wing.vertex` (no hand-maintained
constant — `SPAN`/`R_TIP` in `constants.py` are documented estimates, not the source of truth) and
assert the deck's hinge sits within a small tolerance of one span-axis extreme, translated into the
domain frame by the deck's own `particle_inputs.{x,y,z}` (wing centre).

```python
def assert_hinge_at_span_root(deck_text: str, vertex_path: Path, span_axis: str = "y", tol: float = 0.1):
    markers = read_vertex_file(vertex_path)  # origin-centred, as the solver loads it
    axis_idx = {"x": 0, "y": 1, "z": 2}[span_axis]
    half_span = markers[:, axis_idx].max()  # symmetric about 0 by construction (generate-wing-planform)
    center = [float(_kv(deck_text, f"particle_inputs.{a}")) for a in "xyz"]
    hinge = [float(_kv(deck_text, f"particle_inputs.hinge_{a}")) for a in "xyz"]
    # The hinge must sit at ONE span-axis extreme of the wing (root), not the centre (midspan).
    arm = center[axis_idx] - hinge[axis_idx]
    assert abs(abs(arm) - half_span) < tol, (
        f"hinge_{span_axis} arm {arm} is not within {tol} of the wing's own half-span {half_span} "
        f"(hinge sits near midspan, not the root)"
    )
    # The non-span axes must match the wing centre exactly (no spurious offset).
    for a, idx in {"x": 0, "z": 2}.items() if span_axis == "y" else {"x": 0, "y": 1}.items():
        assert abs(hinge[idx] - center[idx]) < 1e-9, (
            f"hinge_{a} ({hinge[idx]}) has a spurious offset from the wing centre ({center[idx]})"
        )
```

This is deliberately **not** a hardcoded `hinge_y == 0.5` assertion — that would just be a second
frozen constant, no better than byte-identity. Instead it re-derives "root hinge" from the
geometry file every time, so it would have caught the *original* bug (frozen wrong value against
new geometry) **and** would catch a future one (e.g. someone regenerates `wing.vertex` at a
different span without updating any deck's hinge).

Applied to: `examples/prelim_sweep/base_inputs.3d.validation`,
`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`, and (as an existing-passing baseline,
proving the assertion is correctly calibrated and not just tuned to pass on the buggy decks)
`examples/flapping_wing/inputs.3d.validation`.

**Tolerance choice:** `tol=0.1` (chord-lengths) is ~7% of the half-span (`1.475`) — tight enough to
reject a midspan pivot (arm error of `1.475`, 14x the tolerance) but loose enough to tolerate the
vertex file's marker discretization (half-span `1.475` vs the nominal generator span `3.0/2=1.5`,
a `0.025` discretization gap already present in the committed geometry).

**Degenerate input:** an empty/zero-marker vertex file must raise a clear `ValueError` naming the
file, not propagate a bare exception from `markers[:, axis_idx].max()` on an empty array — checked
explicitly before the max/arm computation.

**Why `vertex_path` is a parameter, not read from the deck:** `assert_hinge_at_span_root` takes
`vertex_path` explicitly rather than parsing `particle_inputs.geometry_file` out of `deck_text` and
resolving it itself. This keeps the function a pure geometry check with no filesystem-path
resolution logic of its own (the deck's `geometry_file` value is relative to a runtime working
directory the function has no reason to know about). The caller is responsible for passing the
deck's actual declared geometry file — in every call site in this change, that is the committed
`examples/flapping_wing/wing.vertex`, the single shared geometry file every deck in the repo
references.

## D2. Wing-phase diagnostic visualization

**Why cluster-free is the right first check, not a lesser one:** the bug was purely geometric — a
mis-specified pivot point — and is fully determined by the deck's kinematics + hinge +
`wing.vertex`, none of which require running the solver. A CFD-based check (flow-field
visualization) is strictly more expensive and can only ever be a *second* line of defense once
field capture exists (follow-on change). This diagnostic is deliberately the cluster-free
first line, generalized so it runs against every corrected config, not just one hand-picked example.

**Generalizing `plot_k2_wing_phases`:** the existing function in
`examples/flapping_wing/generate_all_figures.py` hardcodes `HINGE`/`CENTER`/kinematics as
module constants for one example. The new function takes them as parameters:

```python
def build_wing_phase_figure(
    *, vertex_path: Path, center: tuple[float, float, float], hinge: tuple[float, float, float],
    stroke_amp_deg: float, pitch_amp_deg: float, frequency_fstar: float, config_name: str,
) -> tuple[plt.Figure, dict]:
    """4-phase marker-position scatter (t=0, T/4, T/2, 3T/4) in the stroke plane, mirroring
    generate_all_figures.py's fig_wing_phases but parameterized per sweep config.
    Returns (figure, metrics) where metrics carries the same hinge/span-arm numbers D1's guard
    computes, so the figure and the automated check are provably checking the same thing."""
```

Imports `rotation_matrix`/`euler_angles` from `mosquito_cfd.benchmarks.wing_kinematics` (the
canonical source — `test_no_duplicate_rotation_matrix_in_figure_scripts` /
`test_no_legacy_rotation_composition_anywhere` guard against a re-derived copy) rather than
reimplementing them, unlike the existing per-example script.

**Artifact convention (mirrors `evidence_figure.py`, per the repo's established pattern):**
`<output_dir>/<config_name>_wing_phases.png` + `<config_name>_wing_phases_metrics.json` (the span
arm, hinge coordinates, and D1's pass/fail, in numeric form — auditable independent of the PNG) +
a shared `run_metadata.json` via `capture_surrogate_run_metadata`.

**Sample, not exhaustive, by default:** running this for all 54 (27 coarse + 27 fine) configs adds
little marginal signal over a handful — the kinematics only vary in amplitude/frequency, not in
hinge, so a hinge bug is either present in *every* config or none. Default to one representative
config per corner-vs-center split (e.g. the validated point plus 2-3 sweep extremes) with a
`--config all` escape hatch. Document this sampling choice in the script's `--help` and the
figures README (no silent caps — CC-4 convention).

## D4. Automated NFS provisioning (`submit_workflow.sh provision`, closes #62)

**Why this belongs in code, not a manual task:** this session found the coarse corpus's NFS
`wing.vertex` doesn't match any git-committed version at all (SHA256 `ca4996e5...`, span along the
old z-axis) — a real, currently-live consequence of the exact gap issue #62 already describes. A
manual "remember to copy the files" task is precisely what already failed twice (the 22-hour
incident, and this newly-discovered stale coarse geometry). Automating it is the only fix that
generalizes to every future submission, not just this one.

**Two bugs found in the first draft of this design, both fixed below (round-2 review):**

**Bug A — WSL vs. cluster path confusion.** `submit_workflow.sh` runs *inside WSL* (this repo's
documented invocation convention); `WORKSPACE_HOSTPATH`'s default,
`/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep`, is the **cluster-node** hostPath
string — correct as an opaque value passed through to `argo submit --parameter workspace-hostpath=...`
(kubelet resolves it on the remote node), but **not a path WSL's own filesystem can `cp`/`mkdir`
into**. `openspec/project.md`'s own path-mapping table gives the WSL-visible equivalent:
`/mnt/hpi_dev/users/eberrigan/...`. A first draft that ran `cp`/`mkdir` directly against
`$WORKSPACE_HOSTPATH` would either fail outright or silently create a throwaway directory inside
the WSL VM that has nothing to do with the real share — while its own hash-verification step
would still report success (comparing WSL-local source against WSL-local, wrong destination). That
is a worse failure mode than the original manual-copy incident, not a better one: automated and
confidently wrong. Fix: translate the cluster-prefix to the local WSL mount prefix before any
filesystem operation, configurable (so tests can substitute `tmp_path`-rooted prefixes) but
defaulting to the real `/hpi/hpi_dev` → `/mnt/hpi_dev` mapping, and add a dedicated static test
asserting that default mapping is exactly right (no real filesystem needed for that one).

**Bug B — independent `--corpus-dir`/`--workspace-hostpath` overrides can silently mismatch.** If
an operator overrides `--workspace-hostpath` for the fine corpus (as the prior fine-corpus
submission already did) but forgets to also override `--corpus-dir`, provisioning would copy the
**coarse** corpus's decks onto the **fine** corpus's workspace — hash-verified, "successful," and
exactly the silent-wrong-geometry defect this whole change exists to eliminate, now baked into the
step meant to prevent it. Fix: assert the two paths' basenames match (`prelim_sweep` vs
`prelim_sweep_fine` vs `prelim_sweep_fine_pilot`) before provisioning, dying clearly on mismatch
rather than silently proceeding.

**Design, mirroring the existing `--parallelism` pattern (self-contained, testable via a stub
`argo`, never mutates a committed file):**

```bash
# New in submit_workflow.sh. Configurable so tests substitute tmp_path-rooted prefixes; defaults
# are the real cluster-hostPath / WSL-mount-point pair from openspec/project.md's path table.
CLUSTER_NFS_PREFIX="${CLUSTER_NFS_PREFIX:-/hpi/hpi_dev}"
LOCAL_NFS_PREFIX="${LOCAL_NFS_PREFIX:-/mnt/hpi_dev}"

# Translate a cluster-hostPath string (the value handed to `argo submit`) to the path WSL's own
# filesystem can actually read/write. A pure string substitution -- no filesystem access itself,
# so it's trivially unit-testable without any real mount.
to_local_path() {
  local p="$1"
  case "$p" in
    "$CLUSTER_NFS_PREFIX"*) echo "${LOCAL_NFS_PREFIX}${p#$CLUSTER_NFS_PREFIX}" ;;
    *) echo "$p" ;;   # already a local/relative path (e.g. a tmp_path fixture in tests)
  esac
}

# Run automatically at the top of `full` (manifest required) and `smoke` (manifest NOT required --
# smoke runs a single named deck, never reads sweep_manifest.json; see force-surrogate-smoke.yaml).
provision() {
  local corpus_dir="$1" workspace_hostpath="$2" require_manifest="$3"
  local local_workspace; local_workspace="$(to_local_path "$workspace_hostpath")"

  [[ -d "$corpus_dir" ]] || die "corpus dir $corpus_dir does not exist"
  [[ -d "$corpus_dir/inputs" ]] || die "corpus dir $corpus_dir has no inputs/ -- generate it first"
  if [[ "$require_manifest" == "true" ]]; then
    [[ -f "$corpus_dir/sweep_manifest.json" ]] || die "corpus dir $corpus_dir has no sweep_manifest.json"
  fi
  # The exact defect this step exists to prevent: a coarse corpus-dir silently provisioned onto a
  # fine workspace-hostpath (or vice versa) because the two flags were overridden independently.
  [[ "$(basename "$corpus_dir")" == "$(basename "$workspace_hostpath")" ]] \
    || die "corpus-dir '$corpus_dir' and workspace-hostpath '$workspace_hostpath' name different corpora -- pass matching --corpus-dir/--workspace-hostpath"

  mkdir -p "$local_workspace" || die "cannot create/access local workspace path $local_workspace (resolved from $workspace_hostpath)"
  cp -r "$corpus_dir/inputs" "$local_workspace/"
  [[ "$require_manifest" == "true" ]] && cp "$corpus_dir"/sweep_manifest*.json "$local_workspace/"
  cp "$WING_VERTEX_SOURCE" "$local_workspace/wing.vertex"   # always the canonical file
  # Verify by hash immediately -- fail loudly here, not hours later in a pod's mount retry loop.
  local expected actual
  expected="$(sha256sum "$WING_VERTEX_SOURCE" | cut -d' ' -f1)"
  actual="$(sha256sum "$local_workspace/wing.vertex" | cut -d' ' -f1)"
  [[ "$expected" == "$actual" ]] || die "provisioned wing.vertex hash mismatch after copy"
}
```

**Hash-verification scope, clarified (round-3 review found the spec text over-promised relative to
this pseudocode):** `provision()` itself hash-checks only `wing.vertex` — the one file with a known
history of silently drifting. `inputs/` and `sweep_manifest*.json` are copied under `set -euo
pipefail` (already in effect at the top of `submit_workflow.sh`), so a `cp` failure aborts the
script; there is no *silent* corruption path for those to hash-check against, unlike `wing.vertex`
which can be silently *wrong content* even when the copy itself succeeds perfectly (exactly what
happened on NFS). The test suite (task 14) independently verifies the copied `inputs/`/manifest
content matches the source byte-for-byte, mirroring `test_submit_workflow_parallelism.py`'s own
hashlib-based test-level verification convention — the test proves correctness, the script itself
only needs to prove it didn't silently drift on the one file with a documented history of doing so.

**Call-site wiring** (the actual integration into the script's existing structure, so no
implementer discretion remains — rounds 1 and 2 both found bugs specifically in *wiring*, not in
isolated logic):

```bash
# Alongside the script's existing "${VAR:-default}" declarations (near WORKSPACE_HOSTPATH, line 37):
CORPUS_DIR="${CORPUS_DIR:-examples/prelim_sweep}"
WING_VERTEX_SOURCE="${WING_VERTEX_SOURCE:-examples/flapping_wing/wing.vertex}"
NO_PROVISION=""   # empty = provision (default); set by --no-provision

# In the existing arg-parsing `while` loop (line 65 of the real script), alongside the other arms:
    --corpus-dir) CORPUS_DIR="$2"; shift 2;;
    --no-provision) NO_PROVISION="true"; shift 1;;   # the first value-less flag in this script

# In `smoke)` (before its existing `argo submit`, real script line ~90):
  smoke)
    require_image
    [[ -n "$NO_PROVISION" ]] || provision "$CORPUS_DIR" "$WORKSPACE_HOSTPATH" false
    echo "1-config smoke pre-flight ..."
    argo submit "$SMOKE_WORKFLOW" ...   # unchanged below this line

# In `full)` (before the existing --parallelism sed-patch block, real script line ~107):
  full)
    require_image
    [[ -n "$NO_PROVISION" ]] || provision "$CORPUS_DIR" "$WORKSPACE_HOSTPATH" true
    workflow_file="$SWEEP_WORKFLOW_FILE"
    if [[ -n "$PARALLELISM" ]]; then ...   # unchanged below this line
```

New flags: `--corpus-dir` (default `examples/prelim_sweep`, mirroring `WORKSPACE_HOSTPATH`'s own
existing default target) and a `WING_VERTEX_SOURCE` default of `examples/flapping_wing/wing.vertex`
(the single canonical source every deck's `particle_inputs.geometry_file` ultimately refers to).
`--no-provision` escape hatch for the rare case an operator has already staged NFS by hand and
wants to skip the copy (e.g. re-submitting after a transient cluster error with nothing changed) —
default is **provision on**, not opt-in, since opt-in is exactly how this gap went unnoticed twice.
`smoke` calls `provision` with `require_manifest=false` (it needs only `wing.vertex` + its one
named input file, never the manifest) so an ad hoc single-deck smoke test isn't blocked by a
manifest requirement it never needed; `full` calls it with `require_manifest=true`.

**Testing convention** (mirrors `tests/test_submit_workflow_parallelism.py` exactly): a
`tmp_path`-based fake `corpus_dir` and fake `workspace_hostpath` (never the real NFS path, and with
`CLUSTER_NFS_PREFIX`/`LOCAL_NFS_PREFIX` left at their defaults so `to_local_path` is a no-op on a
plain `tmp_path` string — already outside the `/hpi/hpi_dev` prefix), a stub `argo` executable
capturing invocation, and hash-based assertions that the provisioned files match the source.
Covers: successful provision + hash match, for both `full` (manifest required) and `smoke`
(manifest not required); missing `inputs/` fails before `argo` is ever invoked; a nonexistent
`--corpus-dir` fails with a distinct message from "inputs/ missing"; a `corpus_dir`/
`workspace_hostpath` basename mismatch fails before any copy; `--no-provision` skips the copy but
still submits; `to_local_path`'s default `/hpi/hpi_dev` → `/mnt/hpi_dev` substitution is asserted
directly as a pure string test (the one piece of this design real WSL/NFS access can't be exercised
in CI, so it gets a standalone, no-filesystem-needed regression test instead).

**Known, accepted, documented risk (not fixed by this design): concurrent resubmission.** If
`provision` runs while a previous submission against the *same* `--workspace-hostpath` still has
pods retrying (`retryStrategy`, up to 30 min backoff), its non-atomic `cp -r` could overwrite a
deck a still-running pod is about to read. This is a pre-existing risk of the shared-NFS design
(not introduced by this change) and out of scope to fix here — noted so a future operator doesn't
resubmit into a workspace with runs still in flight, which the checkpoint step (`tasks.md` task 34)
should visually confirm via `runai`/`kubectl` before submitting.

## D5. Required, not defaulted, `--timestamp`

`generate_sweep.py` and `generate_full_corpus.py` both currently default `--timestamp` to a literal
ISO string from their original authoring session. This is fine for their **library** function
(`generate_sweep()` itself always requires a caller-supplied `timestamp` — CC-1 is already honored
at that layer); the bug is narrowly in each **CLI driver's** `argparse` default, which lets a real
invocation silently reuse a stale date. Fix: drop `default=DEFAULT_TIMESTAMP` from `add_argument`,
making `--timestamp` a required flag (argparse's own `required=True` on a non-positional, or simply
omitting a default — either raises a clear "the following arguments are required" error rather
than silently proceeding). `DEFAULT_TIMESTAMP` module constants are removed only if nothing else
references them; if a test fixture wants a fixed value it should define its own local constant
rather than import a "default" that no longer represents anything real. `generate_pilot.py` carries
an identical pattern and is intentionally left alone (out of scope, not re-run by this change) —
but left alone is not left unmarked: add a one-line comment next to its own `DEFAULT_TIMESTAMP`
pointing at this change's id, so a future reader doesn't assume all three sibling scripts were
fixed just because the proposal's narrative discusses the pattern generically across all three.

## D6. Spec delta shape for the "frozen corpus" exception

The existing requirement's normative sentence — "The frozen corpus's raw force/moment columns and
IB-particle CSVs SHALL NOT be regenerated" — is scoped narrowly to the *re-normalization
scale-invariance* argument (changing the coefficient convention needs no re-run because the raw
columns don't change). It is not, on its own text, a blanket "never touch the corpus" rule for all
time, but the rest of the spec (and the tests) treat "frozen"/"byte-identical" as a load-bearing
invariant pervasively. Rather than weaken the general guarantee, the delta adds a narrow, explicit
exception clause naming this change, so a future reader of the spec sees the exception as
documented policy, not as a rule that silently stopped being true.
