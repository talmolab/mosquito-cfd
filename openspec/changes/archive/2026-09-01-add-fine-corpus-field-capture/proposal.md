# Add field-capture support to the fine-grid force-surrogate corpus — **BREAKING** (frozen-corpus exception, second instance)

**BREAKING:** this regenerates the fine corpus's committed decks/manifest/provenance a second time
in a row (after `fix-force-surrogate-sweep-hinge`'s hinge-only regeneration) — invoking the same
"frozen corpus, not routinely regenerated" exception language
(`openspec/specs/force-surrogate/spec.md`'s re-normalization requirement) that change already used
for the same category of fine-corpus deck-only regeneration, for consistency, even though this
change's actual content is narrower than what that guarantee literally protects: the cited
requirement's "SHALL NOT be regenerated" language is scoped to already-**committed real force
data** (raw force/moment columns, IB-particle CSVs) — the fine corpus has none (its only real
cluster runs are recorded as superseded; nothing downstream was ever built from them on `main`).
This change only touches cluster-free **decks** — no committed force data is at stake. Flagged here
explicitly, not to lower the review bar, but so a reviewer isn't left wondering why "BREAKING" is
invoked for a change with no committed force data in its diff.

## Why

`docs/field_surrogate/roadmap.md` ("Stage 2," the field-based surrogate: CFD flow-field snapshot →
latent state → dynamics model → forces) is a real, planned next stage beyond the already-complete
Track B force-only surrogate (kinematics → force coefficients, R²≈0.999 on the coarse corpus). Stage
2 genuinely needs AMReX plotfiles — something Track B's force-only corpora (`amr.plot_int = -1` in
every deck) never produce.

The archived `fix-force-surrogate-sweep-hinge` change explicitly anticipated and deferred exactly
this work, verbatim: *"Extending `render_inputs`/`generate_sweep` to support field-capture flags
(`amr.plot_int > 0`, `ns.init_iter = 2`)... Submitting the actual fine-grid CFD cluster run... CC-F1
verification (non-zero velocity field) and CC-F3 storage measurement"* — deferred "to the follow-on
field-capture change." That change also recorded a deliberate scoping decision, made with the user:
bundle the fine corpus's real CFD re-run with full 27-config field capture in this one follow-on
change, rather than paying for the ~2.55-day, GPU-expensive 27-config regeneration twice (once
force-only, once again for field capture) — *"so the expensive fine-grid submission happens exactly
once, combined with field capture, rather than once here and again there."*

**This is that follow-on change.** The currently committed fine corpus (`examples/prelim_sweep_fine/`)
has the corrected wing-hinge geometry already (from `fix-force-surrogate-sweep-hinge`), but its 27
decks have **never actually been CFD-run** — the only real cluster runs against this corpus
(`force-surrogate-sweep-vb8t5`, `force-surrogate-retry-failed-trz9k`, ~54 A40-GPU-hours) used the
old, buggy hinge and are recorded as superseded in `sweep_provenance.json`. Submitting the current
force-only decks now (via the newly-built `/submit-cluster-sweep` skill) would be the first real
execution of the corrected geometry — but also exactly the "once here" the hinge-fix change's own
bundling decision was written to avoid, since Stage 2 would then need a second full regeneration
later.

## What Changes

1. **`render_inputs()`/`generate_sweep()` gain field-capture parameters**
   (`src/mosquito_cfd/force_surrogate/sweep.py`). Correction to the hinge-fix proposal's own framing
   of the code today: `amr.plot_int` **is** currently an actively-forced targeted key — but the
   forcing happens at **two separate sites**, not one: (a) `generate_sweep()`'s per-config call to
   `render_inputs()` hardcodes `plot_int=-1` (ignoring `render_inputs()`'s own already-existing
   `plot_int: int = -1` default parameter — `render_inputs()` itself already accepts and correctly
   applies an override today, it's just never called with one), and (b) `generate_sweep()`'s
   manifest-building `config_records` dict separately hardcodes a literal `"plot_int": -1` for the
   manifest, independent of whatever `render_inputs()` actually wrote to the deck. Both sites must
   be un-hardcoded together, or a fix touching only site (a) would produce decks with the real
   override but a manifest that still (wrongly) records `-1`. `ns.init_iter` is **not** currently
   touched by the generator at all, at either the `render_inputs()` layer or the manifest layer — it
   is silently inherited unchanged from the base deck (which happens to be `0`). This change:
   - Un-hardcodes both `plot_int=-1` sites, threading a new `plot_int: int = -1` keyword parameter
     through `generate_sweep()` to both the `render_inputs()` call and the manifest record. Default
     unchanged (`-1`, force-only) — every existing caller (the coarse corpus, any other
     `generate_sweep()` use) is byte-for-byte unaffected unless it explicitly opts in.
   - Adds `ns.init_iter` as a new, optional targeted key in `render_inputs()`'s replacement dict,
     via a new `init_iter: int | None = None` keyword parameter, threaded through `generate_sweep()`
     to both the deck and a new manifest field. When `None` (default), `ns.init_iter` is left
     untouched exactly as today (pass-through from the base deck) — this is a genuinely new targeted
     key, not a change to existing behavior, so it cannot regress anything that doesn't ask for it.
     Neither override is bounds-validated (e.g. `plot_int=0` or a negative value other than `-1` is
     accepted and written verbatim) — out of scope for this change.
2. **`generate_full_corpus.py` gains `--plot-int`/`--init-iter` CLI flags** (both optional, defaulting
   to today's force-only values), threaded through to the `generate_sweep()` call. Running the driver
   with neither flag reproduces today's exact output.
3. **The fine corpus is regenerated a second time**, now with `--plot-int 100 --init-iter 2`:
   - `amr.plot_int = 100` — a starting subsampling interval (matching the one informal precedent,
     `duncan-meeting-prep`'s abandoned single-config preview deck), explicitly **not** a
     CC-F3-validated value — CC-F3's own storage measurement happens from the real cluster run
     (per the hinge-fix change's already-recorded deviation from CC-F3's "measure on a pilot first"
     default), which is outside this proposal's scope (see "Not in scope").
   - `ns.init_iter = 2` — mandatory per `docs/field_surrogate/roadmap.md`'s CC-F1: with `init_iter=0`,
     IAMReX silently writes `x_velocity = 0` to every plotfile (a known, already-hit defect;
     `examples/flapping_wing/RESULTS.md`'s "Note on the velocity field"). Forces are unaffected
     (marker-velocity-derived, not plotfile-derived) — this is exactly why Track B's force-only decks
     never needed to notice this bug.
4. **Manifest/provenance schema extension.** `sweep_manifest.json`'s per-config records gain a new
   `init_iter` field (mirroring the existing `plot_int` field, which now records `100` instead of
   `-1` for this corpus). `sweep_provenance.json` gains a new `field_capture` block recording the
   policy (`plot_int`, `init_iter`, a one-line rationale, a pointer to CC-F1/CC-F3).
5. **New reusable CC-F1 verification check**, built into the existing
   `mosquito_cfd.benchmarks.stress_integral` module (not a new `src/` module — reusing this
   session's already-decided module boundary, per the existing yt-based `extract_eulerian_box`
   reader it builds on; CC-F2 already flags that a new reader would be redundant), plus a thin
   `scripts/check_plotfile_velocity.py` CLI driver, matching this repo's established thin-driver
   convention. Asserts a given plotfile's `x_velocity` field specifically (not every velocity
   component — a legitimately-zero component, e.g. in a 2D flow, must not cause a false rejection)
   is non-zero before it's trusted as training data. Reusable for every future field-capture run,
   not a one-off check.
6. **Spec delta — four MODIFIED requirements, not one.** Correction to an earlier draft of this
   proposal, which undercounted this: the delta touches
   `openspec/specs/force-surrogate/spec.md`'s "Force-only input generation with minimal diff"
   requirement (`amr.plot_int` SHALL **default** to `-1` but is overridable via an explicit
   parameter; `ns.init_iter` added as a new, optionally-targeted key defaulting to pass-through);
   "Reproducible sweep manifest with units sidecar" (the new optional `init_iter` manifest field
   and `field_capture` provenance block from item 4 above); "Cluster-free injected executor seam
   (force-only)" (a scoping clarification: this coarse-corpus-scoped runner's own force-only
   behavior is unchanged, but the requirement now says explicitly that it doesn't constrain what
   the separate cluster-side Argo orchestration submits for a different corpus); and "Cluster-side
   Argo orchestration of the corpus" (its "Dataset extraction is not in scope" scenario is reworded
   to be workflow-agnostic about `amr.plot_int`/`ns.init_iter`, rather than asserting the
   force-only value as a universal invariant). Of the four requirements this proposal's own
   codebase-exploration step originally flagged as "Force-only ... scope guard" candidates, three —
   the dataset-extractor, training, and evidence-figure scope guards — are genuinely **UNCHANGED**:
   they govern what downstream consumers read, not what the generator writes, and are not weakened
   by plotfiles merely existing on disk (each explicitly says the consumer "neither accepts nor
   requires" a plotfile/field path, which stays true either way). The **fourth** ("cluster-free
   executor seam") is not actually unchanged, per the correction above.

## Not in Scope (explicitly deferred, not silently assumed)

- **The actual cluster submission** (smoke + full, via the already-built `.claude/commands/submit-cluster-sweep.md`
  skill). **This is a deliberate scoping refinement from what `fix-force-surrogate-sweep-hinge`'s own
  proposal anticipated** — that proposal's "Deferred to the follow-on field-capture change" list
  included *"Submitting the actual fine-grid CFD cluster run"* as part of this follow-on's scope.
  This proposal splits that out: code/decks/tooling land here, reviewed and merged like any other
  code change; the live, multi-day, shared-GPU-quota cluster execution is a separate, later action
  requiring the user's own explicit go-ahead at submission time, matching this session's established
  discipline (`/submit-cluster-sweep`'s own "Human Checkpoints" section) of never bundling a code
  merge with an irreversible live-cluster action in the same step.
- **CC-F3 storage measurement** — happens from the real cluster run once submitted (per the
  hinge-fix change's own already-recorded deviation from CC-F3's "pilot first" default), not from
  this proposal's local, cluster-free deck regeneration.
- **`dt=5e-4` numerical-stability re-confirmation** against the corrected hinge geometry — this
  proposal generates decks at the existing `dt=5e-4` default, unchanged. Re-confirmation is an
  operational step during `/submit-cluster-sweep`'s smoke run (inspecting the resulting
  `run_metadata.json`'s `stability` field for a `_fallback` suffix), not a code change here.
- **Stage 2's F2 (field reader)/F3 (DoMINO encoder)/F4-F6** — this proposal only enables field
  *output*; nothing downstream reads it yet. `extract_eulerian_box` is reused by this proposal's CC-F1
  check script but not extended into a general training-data reader (that's F2's own scope).
- **The coarse corpus** (`examples/prelim_sweep/`) — stays force-only/untouched.
  `docs/field_surrogate/roadmap.md`'s own "Inputs and outputs" section names the fine corpus
  specifically as Stage 2's input.

## Impact

- **Affected code:** `src/mosquito_cfd/force_surrogate/sweep.py` (`render_inputs`/`generate_sweep`
  gain `plot_int`/`init_iter` parameters), `examples/prelim_sweep_fine/generate_full_corpus.py` (new
  `--plot-int`/`--init-iter` CLI flags), a new CC-F1 check script under `scripts/`.
- **Affected data:** `examples/prelim_sweep_fine/inputs/*.3d.*` (27 decks regenerated),
  `sweep_manifest.json`, `sweep_provenance.json`.
- **Affected tests:** `tests/test_force_surrogate_sweep.py` (extend/rename
  `test_render_inputs_forces_plot_int_minus_one`, new tests for the `init_iter` parameter, the
  already-existing-but-never-exercised `plot_int` override path, and a byte-identity regression
  test — mirroring the coarse corpus's existing `test_committed_sweep_matches_regeneration` — that
  every default-argument `generate_sweep()` call remains byte-for-byte unaffected),
  `tests/test_full_corpus_deck.py` (new assertions for the regenerated fine corpus's `plot_int`/
  `init_iter` values and the new manifest/provenance fields; the existing
  `test_fine_corpus_provenance_flags_superseded_runs` needs no changes — its `superseded_by` block
  is a separate, coexisting key this change doesn't touch), `tests/test_fine_pilot_deck.py`
  (no code changes expected — Decision 1 in `design.md` specifically avoids touching the base deck
  this test pins — but re-run explicitly to confirm), a new test module for the CC-F1 check
  (cluster-free, using the existing committed synthetic plotfile fixture per issue #33, scoped to
  `x_velocity` specifically — see "What Changes" item 5).
- **Affected specs:** `force-surrogate` — MODIFIED delta to four requirements ("Force-only input
  generation with minimal diff", "Reproducible sweep manifest with units sidecar", "Cluster-free
  injected executor seam (force-only)", "Cluster-side Argo orchestration of the corpus"); the
  dataset-extractor, training, and evidence-figure scope-guard requirements explicitly noted
  UNCHANGED, no delta (see item 6 above for the corrected count).
- **Not touched:** `examples/prelim_sweep/` (coarse corpus), `openspec/specs/force-surrogate/spec.md`'s
  dataset-extractor/training/evidence-figure scope-guard requirements, IAMReX solver source,
  Docker/CI infrastructure.
- **Docker image:** a rebuild is expected (this change adds no new `src/` modules requiring one —
  the CC-F1 check extends the existing `mosquito_cfd.benchmarks.stress_integral` module rather than
  adding a new one, per `design.md`'s Decision 6 — though independently, `Dockerfile.fp64` `COPY`s
  the whole `src/` tree before `uv sync --frozen`, so any `src/` edit invalidates that layer
  regardless; `docker.yml` also triggers unconditionally on every push to `main` either way) — the
  eventual cluster submission must pin the digest published by ***PR A's*** merge commit's
  `docker.yml` run specifically, not PR B's (PR B's own merge also triggers a `docker.yml` run and
  publishes a digest, but the CC-F1 check runs host-side and never enters the image, so PR B's
  digest is irrelevant to what the cluster actually executes) — and not any earlier digest.
- **Cluster:** none, from this change itself. The eventual smoke/full submission is a separate,
  later, explicit-go-ahead action per "Not in Scope" above.
- **PR split:** per `design.md`'s Decision 7 and the git-workflow review, this change lands as two
  PRs, not one — **PR A** (generator code, CLI flags, the real fine-corpus regeneration,
  manifest/provenance schema, module docstring, spec delta) and **PR B** (the CC-F1 check plus the
  one `submit-cluster-sweep.md` doc row that's specifically about the check script), each reviewed
  independently via `/review-pr`. PR B's own code (the check) has no dependency on PR A, but one of
  PR B's doc-update tasks does — see `design.md` Decision 7's "ordering caveat" and `tasks.md` for
  the exact task-to-PR assignment and sequencing note.
