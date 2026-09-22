# Design — moment reference point at the wing hinge

## Context

IAMReX takes the moment arm from the immersed-boundary particle's own origin
(`ForceSpreading_cic`, `DiffusedIB.cpp:804` at pinned commit `f93dc794`):

```cpp
RealVect moment = RealVect((p.pos(0) - Px), (p.pos(1) - Py), (p.pos(2) - Pz))
                  .crossProduct(RealVect(fxP, fyP, fzP));
```

with `(Px,Py,Pz) = kernel.location`, written verbatim to the CSV's `X,Y,Z` columns (`:1260`). So
**the raw CSV records its own moment origin** — the correction need not be inferred from the deck.

The shift is exact through the solver's accumulation: per-marker force and moment are reduced over
the same marker set (`:866-871`), and `ib_force`/`ib_moment` are cleared and accumulated in
lockstep across the `loop_ns` sub-iterations (`:363-364`, `:393-394`). Since the shift is linear,
`Σ_iters Σ_markers (r − P′) × f = M_accum + (P − P′) × F_accum`.

## Decisions

### D1 — Apply the shift at extraction, not post-hoc on the parquet

`normalization.py` converts a moment into a coefficient; it knows nothing about reference points or
geometry files. A change of reference frame applies to the raw measurement, upstream of
normalization, beside where the CSV columns are read.

**Rejected:** transforming the committed parquet in place. It would work numerically (the parquet
carries raw `M` and `F`), but `dataset.py` would keep producing mid-span coefficients, so
re-running `extract_forces.py` on the same inputs would no longer reproduce the committed parquet.
A dataset the current code cannot regenerate is its own reproducibility defect.

### D2 — Derive the offset per configuration; never hardcode `(0, 1.5, 0)`

`r_origin` comes from the run's `X,Y,Z` columns, `r_hinge` from the configuration's deck. Every
committed run gives `(0, 1.5, 0)`, but hardcoding it would silently produce wrong moments for any
future deck whose particle origin and hinge differ — a two-wing or body-in-the-loop case.

Guards that fall out of deriving it:

- The origin must be **constant** across the run, under exact equality. IAMReX advances
  `kernel.location` for a freely-moving particle; our wing is prescribed-motion. If `X,Y,Z` ever
  varies, the constant-offset assumption is void and extraction MUST fail loudly.
- A NaN origin must be rejected rather than producing a NaN offset that silently NaNs every
  coefficient. **The hazard is pandas, not numpy.** An earlier draft of this design claimed
  `np.ptp(...) == 0` admits NaN where exact equality rejects it; that is false — both reject it
  (`np.ptp([nan, nan]) == 0` is `False`, as is `all(x == x[0])`). The idiom that actually swallows
  NaN is pandas, which is what `_extract_config` uses via `pd.read_csv`:
  `pd.Series([4.0, nan, 4.0]).max() - .min()` is `0.0` and `.nunique()` is `1` — both *pass* a
  naive constancy check. The guard must therefore assert finiteness explicitly, not infer it.
- `X`, `Y`, `Z` become required CSV columns — today's extractor does not read them at all.

**The deck is mutable; the CSV is not.** `r_hinge` is read from a working-tree file while
`r_origin` comes from a CSV the cluster wrote months ago — two epochs of the same fact. This repo
has already had exactly that divergence once (the deck comment in
`examples/prelim_sweep_fine/inputs/inputs.3d.s35_f085_p30` records a previously frozen
`hinge_y = 2.0`). A deck edited without re-running the CFD would silently shift about a hinge the
solver never used, and every gate would stay green. The fine corpus's per-config
`run_metadata_<name>.json` records a **`deck_sha256`**; extraction MUST hash the deck it reads and
reconcile against it. The coarse corpus has no per-config metadata and therefore no such anchor —
state that asymmetry as a known limitation rather than leaving it unmentioned.

### D3 — Locate the deck through the manifest's existing `input_file`

`build_dataset` currently takes `(manifest_path, csv_paths, *, allow_missing)` and never opens a
deck. Rather than add a `--deck-dir` CLI flag, resolve each configuration's existing manifest
`input_file` entry (verified present, e.g. `inputs/inputs.3d.s35_f085_p30`) against the manifest's
own directory. The hinge is read with `geometry_guard.read_deck_value`, which already implements
last-assignment-wins ParmParse semantics and rejects non-finite values — a second deck parser would
be a divergent copy.

`read_deck_value`'s error names neither the config nor the deck path, so extraction wraps it to
satisfy the "names the configuration" requirement.

This is a **public API change**, and larger than "two callers". Three signatures move:

1. `build_dataset` gains the deck source. Because `acceptance_gate.py:64` already passes
   `manifest_path` itself, `Path(manifest_path).parent` is available *inside* `build_dataset` — so
   if resolution is internal, neither production call site changes for the directory.
2. `build_dataset`'s **return**. The derived offset is computed inside `_extract_config` and
   currently has no route out: the function returns `(df, dropped)`. The offset must travel with
   the data, not be re-derived by the driver — a second derivation can drift from the applied one,
   and the CI guard would then reconcile the driver's value while the parquet carries another.
3. `build_run_metadata` (`dataset.py:370-400`), whose `extra` is **hardcoded** to
   `{"dropped_configs": ...}`. `scripts/extract_forces.py:92-97` calls it, not
   `capture_surrogate_run_metadata` directly, so there is no passthrough for the frame record today.

An earlier draft of this design named only the first, and assumed a provenance channel that does
not exist.

### D4 — Correct both corpora, and refresh the coarse artifacts in the same change

Coarse and fine decks are byte-identical in this geometry. Correcting only fine would put the two
on different moment conventions while `comparison_figure.py` places them side by side.

Because the coarse corpus's committed `surrogate/` and `figures/` derive from its parquet,
re-extracting without retraining would leave committed artifacts disagreeing with their own data.

### D5 — The hinge is the reference point, defined canonically in one place

The hinge matches van Veen et al. (2022) and, for a single-wing prescribed-motion run, *is* the
actuation torque.

`docs/coordinate-convention.md` is the mandated canonical narrative source and already asserts a
hinge origin; it simply has no `## Moments` section. The definition goes there. `force-surrogate`
owns only the extraction mechanism and cross-references. Without this, the canonical page would be
an uncorroborated duplicate of a fact governed elsewhere — exactly the drift the DRY requirement
exists to prevent, and exactly how the `CF_my` "only moment with signal" claim came to be fixed in
`README.md` and `evidence_figure.py` but not in the spec.

**Precision that must survive editing:** the shift relocates the **origin**, not the axes. These
remain lab-frame components about the hinge. Claiming they are now van Veen wing-frame moments
would replace one documentation defect with a subtler one; a wing-frame moment needs `R(t)ᵀM`
(issue #1, out of scope).

**Say "the deck's declared pivot", not "the wing root".** `hinge_y = 0.5` gives an arm of 1.5, but
the geometry's own half-span is 1.475 (`wing_half_span` on the committed vertex file), putting the
wing's actual root at `y = 0.525`. `geometry_guard.assert_hinge_at_span_root` reconciles the two
only to `tol = 0.1`, by design. The shift arm is therefore 1.7% larger than the geometric root arm.
That is defensible — the deck's declared pivot *is* the actuation axis — but the new `## Moments`
section must not assert "the wing root", which the repo's own geometry guard contradicts at that
level.

**Resolve the page-level frame collision.** `docs/coordinate-convention.md:13` heads its axis table
"## Axes (**wing reference frame**)", and the hinge-origin sentence sits under it. Adding a
lab-frame `## Moments` section to the same page leaves it carrying a wing-frame axis table beside
lab-frame moments, with nothing saying the two coincide only at `φ = α = θ = 0`. The new section
must state that explicitly.

The page's existing hinge-origin line is an *unquoted* assertion — its verbatim citation covers
only axis directions. This change adds the verbatim origin quotation, or narrows the claim to what
the source supports. In particular the *world*-frame half of the claim is uncorroborated in-repo
and must be quoted or dropped.

### D6 — Record the frame in `run_metadata.json`, not `dataset.units.json`

The units sidecar is a flat `{column: unit}` map validated on read *and* write against a closed
three-word vocabulary (`sidecar.py:53-72`), and `corpus_guards.py:170` requires its key set to
**equal** the parquet's measured columns. Any frame key would raise on write and break the guard
on both committed corpora — five CI failures.

The reference point is provenance, not a unit. `capture_surrogate_run_metadata` already accepts
free-form `extra` (the fine corpus carries `dropped_configs` this way), so the frame travels beside
the parquet with zero schema churn.

**Rejected:** a reserved `_meta` key exempt from vocabulary validation. That is a real schema change
to a validator with its own committed tests, and it deserves its own proposal rather than a
one-line task here.

### D7 — Raw `Mx/My/Mz` stay as IAMReX wrote them

The parquet keeps the solver's as-written moments and moves only the derived `CF_m*`, keeping the
audit trail intact and making the correction re-derivable from the committed parquet alone. D8
turns that from a prose claim into an enforced property.

### D8 — Verification reconciles externally, and the regression guard is the point

Per the repo's verification principle — a check reconciling an artifact only against itself cannot
detect a wrong artifact — the correction is checked four ways:

1. **Known-answer parallel-axis test.** Hand-computed `M`, `F` and displacement, compared to the
   implementation. This is the only place a sign or cross-product-order error can hide, which is
   why it ships in its own PR.
2. **`M_y` invariance on real corpus data.** A falsifiable prediction from the geometry.
   State the reason precisely: `M_y` is unchanged because **`d_x = d_z = 0`**, not because the
   displacement is "spanwise". The distinction matters — `y` is the span axis only in the rest
   pose, and under `Rz(φ)` the wing's *instantaneous* span axis leaves lab-`y`, so the moment about
   the instantaneous span is **not** invariant. A reader who takes "spanwise displacement leaves
   the parallel component unchanged" and concludes "so the wing's pitching moment is unchanged"
   will be wrong for every `φ ≠ 0`.

   **It does not pin the cross-product order** — `d × F` and `F × d` both give exactly zero in y —
   so it detects a wrong *axis* only. An earlier draft of this design claimed otherwise and was
   wrong. It is also conditional on finite forces: `0.0 · NaN = NaN`, so a non-finite force
   contaminates even the invariant component.
3. **Unchanged-column reconciliation.** Re-extracting coarse must leave `Fx..Fz`, `CF_x/CF_y/CF_z`,
   `My`, `CF_my`, row counts per split and per config, `config_name` and `split` identical. The
   committed `_FROZEN_RAW_FORCE_SHA` tripwire already enforces the raw half of this in CI; the fine
   corpus needs an equivalent, computed from the committed parquet *before* re-extraction.
4. **The CF_mx/CF_mz hinge identity, in CI, against both committed parquets.** This is the guard
   that does not exist today. It must also assert `CF_mx` is *not* `allclose` to `Mx/m_ref`, or a
   zero offset would satisfy it vacuously. **The offset it uses MUST be derived from the committed
   deck** (`particle_inputs.{x,y,z}` minus `particle_inputs.hinge_{x,y,z}`, both present in every
   deck), never read back from the `run_metadata.json` the same extraction wrote. Reading it back
   makes the guard invariant to the offset's sign: an extractor that computed
   `d = r_hinge − r_origin` would record `a = −1.5` and the guard would reconcile the two happily.
   The deck is a different code path and a different artifact, which is what makes this external.

6. **A physical bound that no artifact can talk its way out of.** All five checks above are
   internal to our own convention — they verify that the recorded offset matches the applied one,
   not that either is *right*. The force-weighted spanwise centre-of-pressure arm from the hinge,
   `b = M_hinge_x / F_z` (equivalently `−M_hinge_z / F_x`), must lie within the wing: the hinge is
   at `y = 0.5` and the tip at `y = 3.5`, so `b ∈ (0, 3]`. No free parameters, nothing read back.
   Measured on the committed corpora over settled beats:

   | | correct `M + d×F` | sign-flipped `M − d×F` |
   |---|---|---|
   | coarse | median `+1.599`, 96.8% in bounds | median `−1.401`, **0.9%** |
   | fine | median `+1.586`, 98.1% in bounds | median `−1.414`, **0.5%** |

   A sign flip collapses from ~97% to under 1%, and the medians land near `R_GYRATION = 1.6985`,
   which is independent corroboration. This is the only check in the set that compares a number to
   physics rather than to our own bookkeeping, and it also catches a wrong magnitude, a wrong axis
   and a units error. It is three lines of pandas over the committed parquet.
5. **The derived offset reconciles against the independently-declared span.** For the committed
   corpora the deck places the hinge at `y = 0.5` and the particle at `y = 2.0`, while
   `constants.py` declares `SPAN = 3.0` — authored separately. The identity
   `hinge_y + SPAN/2 == particle_y` holds exactly, confirming the particle origin is the wing's
   mid-span point and, critically, that `particle_inputs.hinge_*` is an **absolute position in the
   same frame** as `particle_inputs.{x,y,z}` rather than a relative offset. Had it been relative,
   the entire shift would be wrong while every self-consistency check still passed. Assert this for
   the committed corpora as a corpus-level reconciliation — not as a general rule, since a future
   multi-wing deck may legitimately break it.

Byte-diffing the parquets is useless — `dataset.py:355-357` documents that pyarrow embeds writer
metadata, so the blobs differ even for unchanged rows. Value-level gates are the only handle a
reviewer has on 26 MiB of unrenderable binary, so each gate ships as a **committed script**, not an
ad-hoc console session whose evidence dies with the terminal.

### D9 — Measure the GPU noise floor before claiming an invariant survived

The retrain is not bit-reproducible even against unchanged data: `set_seeds` calls
`torch.use_deterministic_algorithms(True, warn_only=True)` and `CUBLAS_WORKSPACE_CONFIG` is never
set, so nondeterministic cuBLAS reductions are downgraded to warnings. `metrics.json` records
`reproducibility.bitwise == "cpu_only"` accordingly.

So "`CF_my`'s config-resolved R² is unchanged within training noise" is unfalsifiable until the
noise is measured. Before the corrected retrain, retrain once on the **uncorrected** committed
parquet at the same seed and host, and record the deltas against the committed metrics. That is
the empirical noise floor; the tolerance is stated as a multiple of it.

Record **all six** targets' deltas, not just `CF_my`. The headline finding of this change is what
happens to `CF_mx` (0.993 → ?), and a noise floor for the one target that cannot move is the least
useful of the six. The same run produces all six for free.

### D11 — An algebraic control that a reviewer can reproduce without `Z:` or a GPU

D7 keeps raw `Mx..Mz` and `Fx..Fz` in the parquet precisely so the correction is re-derivable. That
makes a second control available at zero cost: derive corrected `CF_mx`/`CF_mz` from the **old
committed parquet** in four lines of pandas, with no deck, no `Z:` and no re-extraction, and assert
the result is value-identical to the re-extracted parquet's corresponding columns.

This separates two failure modes that D9 alone cannot:

- **Target change vs pipeline change.** If the algebraic and re-extracted columns agree, then any
  metric movement is attributable to the corrected *target* and not to the rewired extraction path
  (deck resolution, the new `X,Y,Z` read, its interaction with the `iStep` dedup at
  `dataset.py:169-180`, column order, dtypes).
- **Reviewability.** A reviewer who cannot open a 26 MiB parquet can regenerate the training target
  from first principles and check it themselves.

Pair it with a **zero-offset end-to-end control**: run the *new* extractor over the real `Z:` CSVs
with the offset forced to zero and assert the emitted parquet is value-identical to the committed
pre-change parquet across all 22 columns. Tasks 18-19 test the shift on synthetic fixtures; nothing
otherwise tests the rewired path against the real corpus at zero offset.

D1 correctly rejects an in-place parquet transform as a *delivery* mechanism. It should not have
been discarded as a *control*.

### D10 — Provenance must not acquire a well-formed lie

Both drivers require a pinned digest, and the correct value is **the digest the CFD ran under**,
per corpus — coarse `sha256:07625ce4…`, fine `sha256:92817878…`. They differ. Extraction is not
containerized, so "the image doing the extraction" is not a meaningful answer, and the `:fp64` tag
moves, so pasting today's digest would stamp both corpora with an image that never produced the
data — and `validate_image_digest` would accept it. Derive both digests programmatically from the
committed `run_metadata.json` rather than by paste, and assert the regenerated digest equals the
committed one.

Related: the **coarse** `sweep_provenance.json`'s `downstream_artifacts_regenerated_from` block
credits the *previous* hinge fix and two cluster workflow IDs for exactly the artifacts this change
regenerates. Left alone it becomes a confident falsehood that the existing presence-only test
cannot catch. Note the **fine** corpus has no such block at all, and is not retrained here — so the
two corpora need different treatment, and the record naming the retrain belongs in PR3, not PR2.
Note also that `tests/test_force_surrogate_sweep.py:1033` asserts `cluster_workflows` is truthy:
this change involves no cluster run, so that assertion and the block's semantics must be reconciled
rather than silently satisfied with stale IDs.

**What extraction records about its inputs is currently too thin to audit.** `extract_forces.py`
passes only `inputs_file=args.manifest`, so the committed `run_metadata.json` names the manifest
and nothing else. The `--input-dir`, the `--csv-name`, and the consumed CSVs themselves go
unrecorded — meaning nobody can later tell which runs directory, which NFS snapshot, or which
per-config CSV produced any row of a 26 MiB binary. A partially-stale mount, a swapped input
directory, or a silently superseded run is invisible. Extraction MUST record the resolved
`--input-dir` and a **per-config sha256 of each consumed IB-particle CSV**. This is the single
highest-leverage addition in the change: it converts "26 MiB nobody can read" into something
re-verifiable after the fact, and the provenance plumbing is already being touched.

## Risks

- **`CF_mx` skill will likely drop sharply.** Corrected per-config means correlate 0.648 with
  today's, and the current 0.993 config-resolved R² is the repo's strongest between-config result.
  The honest outcome may be a materially worse headline number. That is a finding to report, not a
  reason to avoid the correction.
- **Naming collision.** "The corrected hinge" already means the #71 *deck geometry* fix in eight
  places. Prose from this change must say "hinge-referenced moments" or "moment reference point",
  never a bare "hinge fix", and should disambiguate the occurrences it touches.
- **Repo weight.** ~26 MiB of regenerated binaries, roughly +31% on a packfile already ~80%
  corpus binaries, permanently. This does not justify blocking a correctness fix on Git LFS (#102),
  but the PR body should state the figure so #102 accrues evidence, and #102 is worth deciding
  before #110 adds the next round.
- **Brittle substring guards.** `test_force_surrogate_evidence_figure.py:785` asserts `"2.4" not in
  readme`; any regenerated number whose decimals contain `2.4` fails for reasons unrelated to the
  claim it guards. The refreshed prose must be checked against it.
