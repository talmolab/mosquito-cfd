## Context

Issue: the fine-grid 27-config force-surrogate corpus is force-only (`amr.plot_int=-1`) and its
decks have never actually been CFD-run against the corrected wing-hinge geometry. Stage 2
(`docs/field_surrogate/roadmap.md`) needs plotfiles the current corpus never produces. The archived
`fix-force-surrogate-sweep-hinge` change explicitly deferred exactly this work to "the follow-on
field-capture change" and pre-decided to bundle field capture with the corpus's real CFD re-run
rather than pay for two full ~2.55-day regenerations.

## Decisions

### Decision 1: `ns.init_iter` as a new optional targeted key, not a base-deck edit

`amr.plot_int` is already rewritten per-config via `render_inputs()`'s targeted-key replacement
mechanism, regardless of the base deck's own value — proven, tested code path. `ns.init_iter` could
either follow the same pattern (a new targeted key, default `None` = pass-through) or be set once by
editing the shared `base_inputs.3d.fine` deck file directly.

Chose the targeted-key approach (confirmed with the user during clarifying questions): it reuses an
already-proven mechanism, requires no change to the shared base deck, and — critically — leaves
`tests/test_fine_pilot_deck.py::test_fine_pilot_deck_matches_coarse_base_except_n_cell`'s exact
diff-set pinning (`{amr.n_cell}` only, between the fine and coarse base decks) completely untouched.
Editing the base deck directly would have required updating that test's expected diff set in lockstep
(the same pattern `fix-force-surrogate-sweep-hinge` had to follow for its own base-deck hinge edit),
for no benefit — the targeted-key mechanism already exists and is exactly the tool for this job.

### Decision 2: `plot_int=100`, explicitly unvalidated

No storage-measurement tooling exists in this repo yet (checked: no `du`-wrapping script, no CC-F3
implementation). `100` is the one informal precedent (the abandoned single-config preview deck) —
not a CC-F3-validated value. Per the hinge-fix change's own already-recorded deviation, CC-F3's real
measurement happens from the actual cluster run, not a preceding pilot — so this proposal commits to
a defensible starting value rather than blocking on a measurement this proposal's own scope
(cluster-free deck generation) cannot produce. If the real run's storage turns out to be
unaffordable, the fix is to adjust `--plot-int` and regenerate — cheap, since regeneration is
cluster-free.

### Decision 3: splitting code/decks from the live cluster submission

`fix-force-surrogate-sweep-hinge`'s own proposal anticipated its follow-on change would include
*"Submitting the actual fine-grid CFD cluster run."* This proposal deliberately narrows that: the
code change (generator parameters, CLI flags, regenerated decks, CC-F1 script) lands here, reviewed
and merged through the normal code-review path; the live cluster submission is a separate, later
action through `/submit-cluster-sweep`, which this same session already built specifically to gate
real GPU spend behind the user's own explicit go-ahead at submission time.

**Why the split, not the original bundling:** merging a code change and triggering a multi-day,
shared-quota cluster job in the same step conflates two very different risk profiles — a code
review can be reverted for free; ~61 GPU-hours cannot. Keeping them separate means a code-review
finding doesn't block/entangle with an already-running cluster job, and the cluster submission gets
the full benefit of `/submit-cluster-sweep`'s own review-tested safety gates (mid-sweep check, human
checkpoints) regardless of how the code change was reviewed.

### Decision 4: CC-F1 check as a new reusable script, not a one-off manual step

Confirmed with the user: build a small, reusable script now rather than defer to a manual "eyeball
the smoke plotfile" step. Rationale: this exact check (assert a plotfile's velocity field is
non-zero) will be needed again for every future field-capture run (F4's full corpus, any future
pilot), not just this one; a script is cheap to build once `extract_eulerian_box` already exists
(CC-F2's own point — reuse, don't rebuild a reader), and a scripted assertion is more reliable than
a human eyeballing a range each time.

### Decision 5: `dt=5e-4` stability re-confirmation stays operational, not code

The pilot's own stability result doesn't transfer to the corrected geometry (measured at roughly
half the true tip speed). Confirmed with the user: this proposal does not add a CFL/dt fallback
mechanism to the generator — decks are generated at the existing `dt=5e-4` default, unchanged, and
the real re-confirmation happens naturally when `/submit-cluster-sweep`'s smoke step runs for real
and its `run_metadata.json`'s `stability` field is inspected. Building an auto-CFL-fallback mechanism
into the generator would be genuinely new scope (predicting stability without running the solver) —
not something to add speculatively when the existing smoke-run-based mechanism already surfaces the
answer directly.

### Decision 6: CC-F1 check lives in `mosquito_cfd.benchmarks.stress_integral`, not a new module

The check reuses `extract_eulerian_box` (already in this module) as its only plotfile reader —
CC-F2 already flags a second reader as redundant. Adding the check as a new function in the same
module (rather than a new `src/` module) keeps the reader and its one real consumer co-located,
and matches this proposal's own Docker-impact claim that no new `src/` modules are introduced. A
thin `scripts/check_plotfile_velocity.py` CLI driver wraps it for direct operator use during
`/submit-cluster-sweep`'s Step 2, mirroring the repo's existing thin-driver convention (e.g.
`scripts/extract_forces.py` around `force_surrogate` library code).

### Decision 7: Split implementation into two PRs — PR A (generator/regen/spec) and PR B (CC-F1 check)

Distinct from Decision 3 (which separates this *change* from the live cluster submission) and
Decision 6 (which only decides the CC-F1 check's module home) — this decision is about splitting
*this change's own implementation* into two independently-reviewed pull requests, recommended by
this change's own git-workflow review round.

**PR A**: `render_inputs()`/`generate_sweep()` parameter threading (Sections 1-3), the
`generate_full_corpus.py` CLI flags and the real fine-corpus regeneration (Section 4), the module
docstring update, and the spec delta's four MODIFIED requirements. **PR B**: the CC-F1
non-zero-velocity check (Section 5), which is genuinely independent of PR A's code — it only reads
the already-existing `tests/fixtures/lev_boxlib_plt` fixture through the already-existing
`extract_eulerian_box` reader — plus the one documentation row that's specifically about the check
script itself (wiring it into `/submit-cluster-sweep`'s Step 2).

**Why split:** a review comment on the check script (a small, self-contained addition) shouldn't
block the deck-regeneration PR (the larger, higher-stakes change — it touches 27 committed decks
and the manifest/provenance schema), and vice versa. Each PR gets its own focused `/review-pr` pass
rather than one review trying to hold both concerns in mind at once.

**Ordering caveat, not full independence:** PR B is independent in the sense that its own code and
tests (tasks 17-19) have zero dependency on PR A landing first. But one PR-B task (updating
`submit-cluster-sweep.md`'s Step 0 framing to say "the fine corpus is no longer force-only") is
only true once PR A has actually merged — that specific doc edit is sequenced after PR A, even
though the check script itself isn't. `tasks.md` states this explicitly rather than implying full
bidirectional independence.

## Risks / Trade-offs

- `plot_int=100`'s storage cost is unmeasured until the real run. If it proves too expensive, the
  fix is a cheap re-generation (cluster-free) with a different value — not a re-run of anything
  already-completed, since nothing downstream consumes plotfiles yet.
- This is the fine corpus's **second** regeneration in a row. Both regenerations are individually
  justified and documented (hinge correctness, then field-capture bundling) — but a reader should not
  interpret two regenerations close together as evidence this corpus is now "routinely regenerated."
  It remains an exception, twice, for two independently-justified reasons, not a new precedent.
- `ns.init_iter=2` changes the CFD run's own internal iteration count — confirmed (per
  `examples/flapping_wing/RESULTS.md`) that this does not affect the force output IB-particle CSVs
  use (marker-velocity-derived), so Track B's existing force-surrogate results/tests are unaffected
  by this change to the fine corpus specifically. No corresponding change is made to the coarse
  corpus, which stays at `init_iter=0` (inherited, untouched) — force-only and field-capture-enabled
  corpora can coexist with different `ns.init_iter` values with no cross-contamination, since neither
  corpus's downstream pipeline (dataset extraction, training) ever reads plotfiles.
- **`sweep_provenance.json`'s `field_capture.rationale` describes AMReX's *periodic* plot-write
  gate (`plot_int > 0`), not necessarily every plotfile IAMReX could ever write.** A self-review
  round traced IAMReX's `main.cpp` and found an unconditional final `writePlotFile()` call after
  the time-stepping loop exits (gated by a separate, always-on `amr.plot_files_output` flag, not
  by `plot_int`) — so a force-only run (`plot_int=-1`) that completes naturally could still emit
  one final plotfile, in principle. Unverified in practice for this corpus: sweep configs are run
  under Argo with an `activeDeadlineSeconds` wall-time kill, and it's not confirmed whether any
  config actually reaches natural completion rather than being killed first. Flagged here as an
  operational caveat for whoever reviews the real cluster run's output, not a code change — this
  proposal's rationale text is accurate about the *periodic* gate, which is the property it's
  actually describing.

## Migration Plan

None required for downstream consumers — `generate_sweep()`'s new parameters are additive and
default to today's exact behavior; every existing caller (the coarse corpus especially) is
unaffected unless it explicitly opts in. The fine corpus's own regeneration is a one-time,
documented, cluster-free deck/manifest/provenance update in this same change.
