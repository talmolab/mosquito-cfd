# Fix wing hinge geometry in the force-surrogate sweep corpus — **BREAKING** (frozen-corpus exception)

**BREAKING:** this regenerates the Track B coarse corpus's committed raw force data (previously
governed by an explicit "frozen, never regenerated" spec guarantee) and the fine corpus's decks —
a documented, one-time exception to that guarantee, not a precedent for routine re-runs.

## Why

Every Track B force-surrogate sweep config — all 27 coarse (`examples/prelim_sweep/`) and all 27
fine (`examples/prelim_sweep_fine/`, plus the 3-config `examples/prelim_sweep_fine_pilot/`) — has
pivoted the wing at the wrong point since the 2026-07-02 axis-convention refactor
(`refactor-wing-axis-convention`, commit `4783acd`). Independently re-verified this session against
the live deck and the committed `wing.vertex` marker geometry (908 markers, span `y ∈ [-1.475,
1.475]`, flat in `z=0`):

- The sweep base decks (`examples/prelim_sweep/base_inputs.3d.validation`,
  `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`) carry `particle_inputs.hinge_y = 2.0`,
  `hinge_z = 2.5` — exactly the **wing centre** in y (`particle_inputs.y = 2.0`, i.e. **zero
  span-arm**, a midspan pivot, not a root hinge) plus a spurious `-1.5` offset in z (vertical),
  left over from the *old* span-along-z convention where `z = 2.5` correctly sat at the span root.
- The live, correct deck (`examples/flapping_wing/inputs.3d.validation`, unaffected — it was
  updated by the same refactor) carries `hinge_y = 0.5, hinge_z = 4.0`: `y = 0.5` sits at the span
  root (arm = `2.0 - 0.5 = 1.5`, matching the vertex file's half-span `≈1.475`) with no spurious z
  offset (`z = 4.0` = the wing's own vertical centre).
- Root cause, confirmed from the refactor's own proposal ("Deviation discovered during
  implementation"): re-orienting the live deck's hinge would have broken
  `test_committed_sweep_matches_regeneration` (a byte-identity guard), so the refactor instead froze
  a byte-identical **snapshot of the pre-refactor deck** as the sweep's permanent base — carrying the
  old convention's hinge forward under a geometry file (`wing.vertex`) that had already moved to the
  new convention. The byte-identity guard verified the snapshot was preserved; it could not, and did
  not, verify the snapshot was still *correct* for the new geometry.
- Practical effect **on the git-committed base decks themselves, and on any future regeneration**:
  every sweep config generated from them simulates a wing that pivots near midspan with a spurious
  out-of-plane offset — not a proper root-hinged wingbeat, and a real difference in simulated motion
  (kinematics and, therefore, forces), not a labeling issue. **What each already-completed cluster
  run actually simulated is a separate question, answered by which `wing.vertex` happened to be
  staged on that corpus's cluster NFS share at the time** — a second, independently discovered
  defect detailed immediately below, which turns out to give the fine corpus exactly this
  midspan-pivot motion, but gives the coarse corpus something different and, in its own way, worse.
- Not affected: `examples/flapping_wing/`'s own van Veen validation (T2a/T3b/T3c) — always ran the
  live, corrected deck. `R_GYRATION`/`S_yy` (`src/mosquito_cfd/force_surrogate/constants.py`) are
  re-verified this session to be traced from `wing.vertex` markers alone, independent of hinge
  placement — unaffected. The fine-grid pilot's `dt=5e-4` numerical-stability finding is orthogonal
  to hinge placement (a wrong-but-still-rigid pivot doesn't change solver stability) — not re-run.

**A second, compounding defect: the actual cluster runs used whatever `wing.vertex` happened to be
staged on the cluster NFS share, not the git-committed geometry — and that turned out to differ by
corpus.** `run_one_config.py`'s `DEFAULT_WING_VERTEX = "/workspace/wing.vertex"` resolves to
whatever file sits at each corpus's own `WORKSPACE_HOSTPATH` on NFS; nothing re-stages it when the
git-committed `examples/flapping_wing/wing.vertex` changes (this is exactly **issue #62**, filed
after a prior session's 22-hour incident, still open). Checking the actual files this session:

| Corpus | NFS `wing.vertex` SHA256 | Convention | Consequence |
|---|---|---|---|
| `examples/prelim_sweep/` (coarse, **live on `main`**) | `ca4996e5...` — **not** the canonical file; markers show span along **z** | Pre-T2a (old) | The committed `dataset.parquet`/`surrogate/*`/`figures/*` were generated under the **pre-T2a motion convention entirely** — the hinge `(4, 2.0, 2.5)` is actually the *correct* root-hinge **for that old geometry** (`z_center − z_hinge = 4.0 − 2.5 = 1.5`, matching the old geometry's half-span). This is not a hinge-placement defect on this corpus specifically — it is the **whole pre-van-Veen kinematic composition** T2a's own proposal already demonstrated doesn't trace the ±70° stroke arc (`Rz(φ)` about the span axis itself). Worse than a misplaced pivot, and never fixed for Track B because T2a deliberately froze/decoupled it. |
| `examples/prelim_sweep_fine/`, `..._fine_pilot/` (fine) | `9fe1f07c...` — matches the canonical `examples/flapping_wing/wing.vertex` exactly | Current (new) | Correct geometry paired with the stale `(4, 2.0, 2.5)` hinge **is** the midspan-pivot-with-spurious-offset defect described above, simulated faithfully by the already-completed `vb8t5`/`trz9k` cluster run. |

Both corpora share the same root infrastructure gap (#62: nothing provisions NFS from the
git-committed source of truth), manifesting as two different symptoms depending on when each
corpus's NFS directory happened to last be touched by hand. Fixing #62 for real — not just working
around it for this one regeneration — is in scope for this change (see "What Changes" item 4).

**A regeneration is mandatory regardless of any other scope decision.** Cluster forensics this
session (`kubectl get workflows -n runai-talmo-lab`) show the full 27-config fine-grid corpus
*already completed* 2026-08-04→08-07 (`force-surrogate-sweep-vb8t5` 26/29 + retry
`force-surrogate-retry-failed-trz9k` 3/3; all 27 run directories confirmed present on
`Z:\...\prelim_sweep_fine\runs\`) — with the buggy hinge, before this bug was found. That compute
(~54 A40-GPU-hours) is a sunk cost; nothing downstream (`dataset.parquet`/`surrogate/`/`figures/`)
was built from it on `main` yet, so nothing else needs retracting for the fine corpus specifically.
The **coarse** corpus's downstream artifacts (`examples/prelim_sweep/dataset.parquet`,
`surrogate/{holdout_predictions.parquet,metrics.json,surrogate.pt,run_metadata.json}`,
`figures/{evidence_figure.png,evidence_figure_metrics.json,run_metadata.json}`) **are** real,
merged, long-standing artifacts on `main` built entirely on the buggy hinge, and are regenerated by
this change.

Stage 2 (field-based surrogate, `docs/field_surrogate/roadmap.md`) is ready to start, but that
roadmap doc currently exists only on a throwaway pitch-prep branch (`duncan-meeting-prep`) — never
merged to `main`. `docs/force_surrogate/roadmap.md` (on `main`, CC-6 note, 2026-08-07) already links
to it, so that link is currently dangling on `main`. This change brings the roadmap doc onto `main`
as a docs-only import (fixing the dangling link) with its sequencing note updated to reflect the
decision below; it does **not** implement Stage 2 field-capture code — that is explicitly deferred
to a follow-on change (see "Deferred to the follow-on field-capture change").

## Root-cause audit (full sweep, not just the two base decks)

Grepped every `hinge_[xyz]` occurrence in the repo (70 files) and cross-referenced each against
`wing.vertex`'s actual geometry:

| Location | Hinge | Status |
|---|---|---|
| `examples/flapping_wing/inputs.3d.validation` (+ `.convergence_medium`, `.convergence_fine`) | `(4.0, 0.5, 4.0)` | **Correct** — live, van Veen convention |
| `examples/flapping_wing/inputs.3d.validation_v2`, `inputs.3d.production` | `(4.0, 2.0, 2.5)` | Pre-refactor, **old-convention, old-BC, already-deprecated** decks (per `refactor-wing-axis-convention` and `add-wing-grid-convergence` proposals — `production` was explicitly deferred to T3 and never reused, `validation_v2` is an old-BC contrast baseline). Not part of this fix's scope; a documentation banner promised for `production` in T2a's own tasks.md was never actually added — noted as a minor follow-up, not blocking. |
| `examples/prelim_sweep/base_inputs.3d.validation` (+ all 27 generated `inputs/inputs.3d.*`) | `(4.0, 2.0, 2.5)` | **Bug** — fixed here |
| `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` (+ all 3 generated `inputs/inputs.3d.*`) | `(4.0, 2.0, 2.5)` | **Bug** — fixed here |
| `examples/prelim_sweep_fine/inputs/inputs.3d.*` (27 files, generated from the fine base) | `(4.0, 2.0, 2.5)` | **Bug** — decks regenerated here (cluster-free); the corresponding CFD re-run is deferred |
| `tests/fixtures/run_metadata/inputs.3d.s35_f085_p45` | `(4.0, 2.0, 2.5)` | Copy of a real pilot config for deck-key-parsing tests; no test asserts the hinge value itself — regenerated alongside the pilot config it mirrors, for consistency, not because a test requires it |

## What Changes

1. **Hinge fix.** Correct `particle_inputs.hinge_y`/`hinge_z` from `2.0`/`2.5` to `0.5`/`4.0` in
   `examples/prelim_sweep/base_inputs.3d.validation` and
   `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` — the only two hand-authored base decks;
   every other affected file is machine-generated from one of these two via `generate_sweep()`.

2. **Regression guard (TDD-first).** A new geometric-consistency test asserts the sweep base
   deck's hinge lands at/near a span-axis extreme of `wing.vertex`'s actual marker extent — not
   byte-identity to a frozen snapshot, which is exactly the guard that let this bug ship undetected
   for over a month. See `design.md` for the tolerance and axis-detection approach.

3. **Cluster-free wing-phase geometric diagnostic (new, reusable).** A parameterized visualization
   — "does this config's wing actually pivot at its root, tracing the commanded stroke arc, or does
   it wobble around some other point?" — buildable and testable **without any CFD run**, from the
   deck's kinematics + hinge + `wing.vertex` alone (the same category of check that caught this bug
   during unrelated pitch-deck preparation). Generalizes
   `examples/flapping_wing/generate_all_figures.py`'s `plot_k2_wing_phases` (currently hardcoded to
   one example) into a reusable function importable against **any** sweep config, following the
   established evidence-figure provenance convention (`<name>.png` +
   `<name>_metrics.json` + `run_metadata.json` triple, `capture_surrogate_run_metadata`, a README
   `Regenerate` section). Run once as a sanity check against a representative sample of the
   corrected corpus as part of accepting the regeneration (see `design.md`).

4. **Fix issue #62 for real: automate NFS provisioning instead of working around it.** Add a
   `provision` step to `cluster/argo/scripts/submit_workflow.sh` that copies the local, git-committed
   corpus directory (`inputs/`, `sweep_manifest*.json`, and the canonical `examples/flapping_wing/wing.vertex`)
   onto `WORKSPACE_HOSTPATH` and verifies the copy by hash before `argo submit` runs — so a
   stale/missing NFS workspace fails fast and loudly instead of silently retrying for hours (the
   prior incident) or, worse, silently running against stale geometry (this change's own finding).
   Tested cluster-free, mirroring the existing `--parallelism` stub-`argo` test convention
   (`tests/test_submit_workflow_parallelism.py`). Closes #62.

5. **Fix the hardcoded stale-timestamp CLI default.** `examples/prelim_sweep/generate_sweep.py`
   and `examples/prelim_sweep_fine/generate_full_corpus.py` both default `--timestamp` to a literal
   ISO timestamp from their original authoring date; running either "unmodified" for a real
   regeneration (as an earlier draft of this proposal itself suggested) would silently stamp
   `sweep_provenance.json` with a stale date that looks like nothing changed. Make `--timestamp`
   a required CLI argument in both scripts (no default) — callers must be explicit, matching this
   repo's own CC-1 reproducibility convention (caller-supplied timestamp, never wall-clock or a
   frozen literal). `examples/prelim_sweep_fine_pilot/generate_pilot.py` has the identical latent
   pattern but is not touched here (the pilot isn't being re-run by this change) — noted, not fixed,
   to keep this change's diff scoped to what it actually exercises.

6. **Byte-identity tests and docstrings updated, not silently broken.** `BASE_INPUTS`'s "frozen
   snapshot, never regenerated" comment in `tests/test_force_surrogate_sweep.py`,
   `sweep.py`'s docstring, and the spec requirement "Re-normalization preserves surrogate skill
   (scale-invariance)" (`openspec/specs/force-surrogate/spec.md`) all currently assert the raw
   corpus is permanently frozen. This change documents the one-time, geometry-defect-driven
   exception explicitly (spec delta below) rather than letting the tests silently start failing or
   silently rewriting history.

7. **Coarse corpus regenerated end-to-end.** `examples/prelim_sweep/`: regenerate all 27 decks +
   manifest, submit the (cheap, ~5 min/config) cluster re-run, then re-run
   extract → train → evidence-figure so `dataset.parquet`, `surrogate/*`, and
   `figures/evidence_figure.png` on `main` reflect the corrected geometry.

8. **Fine corpus decks regenerated (cluster-free only).** `examples/prelim_sweep_fine/`: regenerate
   all 27 decks + manifest via the existing, unmodified `generate_full_corpus.py` with the corrected
   fine base deck. The actual CFD cluster run is **deferred** to the follow-on field-capture change
   (see below) so the expensive fine-grid submission happens exactly once, combined with field
   capture, rather than once here and again there.

9. **Bring `docs/field_surrogate/roadmap.md` onto `main`** (docs-only), together with the
   `docs/force_surrogate/roadmap.md` CC-6 + "Out of scope" edit that `field_surrogate/roadmap.md`'s
   own header references (that edit exists only on `duncan-meeting-prep` alongside the new file —
   both must land together, or the new file's "see the note there" reference is dangling from the
   moment it's committed). Update the imported doc's sequencing note to record that F1 (the
   standalone field-capture pilot) is superseded by a full-corpus field-capture run bundled with the
   **follow-on change's** fine-corpus CFD re-run (an explicit, user-approved deviation from the
   roadmap's own "pilot before full commit" default — see "Deviation and scoping decisions"). This
   change does not run any fine-corpus CFD itself (see "Deferred to the follow-on field-capture
   change" below) — only the follow-on change bundles field capture with a real cluster submission.

10. **Documentation pointers** (not rewrites): `docs/force_surrogate/roadmap.md`,
   `docs/force_surrogate/fine-grid-pilot-report.md`, and the archived proposals
   `add-fine-grid-corpus-full`, `add-fine-grid-training-pilot` get a one-line pointer to this fix
   where they discuss corpus force accuracy, so a reader lands on the correction.

## Deferred to the follow-on field-capture change

Explicitly **not** in this change (raised as a scoping question and decided with the user this
session, recorded here so the decision isn't silently assumed later):

- Extending `render_inputs`/`generate_sweep` to support field-capture flags (`amr.plot_int > 0`,
  `ns.init_iter = 2`) — currently `render_inputs` unconditionally forces `amr.plot_int = -1`.
- Submitting the actual fine-grid CFD cluster run (this change only regenerates its decks).
- CC-F1 verification (non-zero velocity field) and CC-F3 storage measurement.
- True flow-field visualization (needs plotfiles, which don't exist yet for the sweep corpus).
- Implementing the Stage-2 roadmap's F1–F6 pipeline itself.

## Deviation and scoping decisions (made explicitly with the user this session, not assumed)

1. **Roadmap doc:** bring `docs/field_surrogate/roadmap.md` onto `main` now (this change), rather
   than leaving it on `duncan-meeting-prep`.
2. **Corpus regeneration scope:** the fine corpus's real CFD re-run bundles full 27-config field
   capture in the follow-on change, **explicitly overriding** `docs/field_surrogate/roadmap.md`
   CC-F3's "measure storage on a small pilot before committing to the full corpus" default. Storage
   will be measured from the real run instead of a preceding pilot, and reported before the corpus
   is trusted, per CC-F3's spirit if not its letter — flagged here as a deliberate, informed
   deviation, not a silent skip.
3. **Coarse downstream artifacts:** regenerate (not merely relabel or delete) `dataset.parquet`,
   `surrogate/*`, and `figures/evidence_figure.png` in this change, so `main`'s Track B state stays
   trustworthy end-to-end.

## Impact

- **Affected specs:** `force-surrogate` (modified — frozen-corpus exception documented; added —
  hinge-geometry consistency guard, wing-phase diagnostic visualization, Argo NFS-provisioning
  guard closing #62).
- **Affected code:** `cluster/argo/scripts/submit_workflow.sh` (new `provision` step, `to_local_path`
  WSL/cluster path translation, `--corpus-dir`/`--no-provision` flags) + `cluster/argo/README.md`
  (documents the new flags) + new `tests/test_submit_workflow_provision.py` (mirrors
  `tests/test_submit_workflow_parallelism.py`'s stub-`argo` convention, parametrized across ≥2
  corpus-dir/workspace-hostpath pairs); `examples/prelim_sweep/generate_sweep.py` (new tests added
  to the existing `tests/test_force_surrogate_sweep.py`, which already loads this exact script —
  not a new file) and `examples/prelim_sweep_fine/generate_full_corpus.py`
  (`--timestamp` made required and ISO-8601-validated, no default) +
  `tests/test_full_corpus_deck.py::test_generate_full_corpus_main_rejects_frozen_paths_via_cli`
  (updated to pass an explicit `--timestamp` so it keeps exercising the frozen-path guard rather
  than a now-required-argument error) + a pointer comment in
  `examples/prelim_sweep_fine_pilot/generate_pilot.py` (identical pattern, intentionally left
  functionally unfixed); `examples/prelim_sweep/base_inputs.3d.validation`,
  `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`, both corpora's generated
  `inputs/inputs.3d.*` + `sweep_manifest*.json` (including `examples/prelim_sweep_fine/`, the full
  27-config fine corpus, distinct from the 3-config `_pilot`), `tests/fixtures/run_metadata/inputs.3d.s35_f085_p45`;
  new `tests/test_sweep_hinge_geometry.py` + `src/mosquito_cfd/force_surrogate/geometry_guard.py`
  (the regression guard) and `src/mosquito_cfd/force_surrogate/wing_phase_diagnostic.py` (or
  similarly named, a separate module) + its tests + a `scripts/` CLI driver;
  `tests/test_force_surrogate_sweep.py` (`BASE_INPUTS` docstring,
  `test_committed_sweep_matches_regeneration` expectations),
  `tests/test_force_surrogate_scale_invariance.py` (`_FROZEN_RAW_FORCE_SHA` — this hardcoded hash of
  the raw force columns will fail after Phase 5 regenerates them unless updated in the same change),
  `tests/test_fine_pilot_deck.py` (unaffected in structure — both bases change identically);
  `examples/prelim_sweep/{dataset.parquet,surrogate/*,figures/*,figures/README.md}` (new),
  `examples/prelim_sweep/README.md` (hardcoded R²/speedup numbers refreshed to match the
  regenerated figure); `docs/field_surrogate/roadmap.md` (new on `main`),
  `docs/force_surrogate/{roadmap.md,fine-grid-pilot-report.md}` (the CC-6/"Out of scope" edit that
  makes the new file's cross-reference resolve, plus pointer notes and refreshed result numbers);
  `openspec/project.md` ("Current State" bullet, and the existing "Pending" bullet about the
  now-superseded fine-grid cluster run).
- **Not touched:** `examples/flapping_wing/` (already correct), IAMReX fork source.
- **Docker image: rebuild IS expected, not skippable.** Earlier drafts of this proposal claimed "no
  rebuild needed — same pinned digest"; that was wrong. This change adds new modules under `src/`,
  `docker/Dockerfile.fp64` does `COPY src/ ./src/`, and `docker.yml` triggers unconditionally on
  every push to `main` — merging this change's own commit produces a **new** `:fp64` digest
  regardless of whether the CFD runner actually needs the new modules. The coarse re-run's
  `run_metadata.json` MUST use the digest published by *this change's own* `docker.yml` run (see
  `cluster/argo/README.md`'s Prerequisites for the exact job-summary-copy procedure), not any
  digest noted in an earlier session or in this proposal.
- **Cluster (this change only):** one cheap coarse 27-config re-run (~5 min/config, same pattern as
  the original coarse submission). The expensive fine-grid CFD re-run is explicitly deferred; this
  change only regenerates the fine corpus's decks/manifest (cluster-free), with a fresh generation
  timestamp (not the original corpus's stale `2026-08-03` default, now impossible to silently
  reuse — the CLI itself requires it, per `tasks.md` Phase 4/Phase 6).
- **Reproducibility:** the coarse re-run captures fresh `run_metadata.json` via the existing
  `capture_surrogate_run_metadata`, using the digest this change's own `docker.yml` run publishes
  (see above) — the 2026-08-09 digest noted in the original handoff is superseded twice over
  (once by time, once by this change's own rebuild) and must not be reused.
- **NFS staging is automated, not manual (item 4 above, closes #62):** the coarse re-run's Argo
  pods mount the cluster NFS copy of `examples/prelim_sweep/`, not this git checkout — this session
  confirmed that copy is not just potentially stale but *actually* stale (see the audit table
  above: `ca4996e5...` on NFS vs `9fe1f07c...` canonical). `submit_workflow.sh full` now runs the
  new `provision` step automatically before `argo submit`, so this is a repeatable, tested code
  path, not a one-off manual copy — closing the same class of gap that stalled the fine-grid corpus
  submission for 22 hours in an earlier session ([[fine-corpus-nfs-provisioning-gap]]).
- **Explicitly out of scope:** re-running the fine-grid pilot's stability check (orthogonal,
  already valid); re-authoring `examples/flapping_wing/inputs.3d.production`'s banner (pre-existing,
  unrelated gap, noted not fixed); any change to IAMReX solver source.
