# Tasks

Every implementation task names the test written **first** and the behaviour it pins. Delivered as
three PRs (proposal "Delivery"); PR boundaries are marked.

## 0. Record the blast radius before touching code

0. [x] Record the exact list of committed tests this change is expected to touch, with file:line
   and what each pins. **Any test outside this list that needs editing halts the change** — it
   would mean the shift leaked beyond `CF_mx`/`CF_mz`.
   - `tests/test_force_surrogate_dataset.py` — 35 `build_dataset(` call sites. Most funnel through
     `_write_manifest:48` / `_validated_point_config:54`, but **four use `COMMITTED_MANIFEST`
     directly** (`:81, :90, :122, :134`) and resolve the **real** decks, and four more
     (`:439, :447, :459, :467`) are malformed-manifest error paths. Fixing the two helpers is not
     sufficient.
   - `tests/test_acceptance_gate.py:76-95` `_make_corpus` (deck-free corpus fixture)
   - `tests/test_force_surrogate_driver.py` — 5 `main(` sites
   - `tests/test_force_surrogate_evidence_figure.py:785` (`"2.4" not in readme`), `:788` (`~468`
     latency literal), `:246/:511/:808` (`batch_size == 12535`), `:780` (`cf_mx`/`cf_mz` substrings
     in the README prose task 41 rewrites)
   - `tests/test_no_false_diffused_ib_claim.py:36-44` (scans the regenerated figure sidecar)
   - `tests/test_force_surrogate_sweep.py:1015` (provenance `reason`), **`:1033`** (asserts
     `cluster_workflows` is truthy — this change involves no cluster run; see task 33)
   - Expected to stay green, and cited as gates: `test_force_surrogate_scale_invariance.py:116-122`
     (frozen raw-force SHA), `test_corpus_guards.py:497-509` (CF_x peak 4.015 / 2.880),
     `test_force_surrogate_evidence_figure.py:793-805`, `test_force_surrogate_scale_invariance.py:63-73`
0a. [x] Record explicitly: **a `_FROZEN_RAW_FORCE_SHA` trip is a HALT for this change, not a
   re-pin.** The test file's own comment (`:79-81`) authorises re-pinning on a pandas upgrade; that
   authorisation does not apply here, because this is the one change that rewrites the parquets and
   the SHA is the only external check on their raw columns.

---

# PR 1 — pure helper, docstring, canonical docs (no binaries)

## 1. Parallel-axis shift helper

1. [x] **Test first** — known-answer case with `d × F ≠ 0` (nonzero `d`, nonzero `Fx` and `Fz`):
   hand-computed `M + d × F`. Pins cross-product **order** and sign. The only place a sign error
   can hide.
2. [x] **Test first** — spanwise invariance with **`a ≠ 0`** and nonzero `Fx`/`Fz`, all-finite:
   `M_y` compares equal (`==`, accepting `-0.0 == 0.0`); `M_x`/`M_z` change by `+a·F_z` / `−a·F_x`.
   State in the test that this does **not** pin cross-product order.
3. [x] **Test first** — non-finite forces: with `Fx` or `Fz` NaN/inf, `M_y` becomes NaN
   (`0.0 · NaN = NaN`). Use `np.errstate(invalid="ignore")` rather than relying on pytest's
   warning config. Also pin the **zero-displacement** non-finite case, so the zero path is
   *computed*, not short-circuited by an `if offset == 0: return` fast path.
4. [x] **Test first** — degenerate inputs: zero displacement leaves all-finite inputs **comparing
   equal** (`==`, not "bitwise"/"exact" — `−0.0 + 0.0 = +0.0`); empty arrays yield empty output;
   mismatched `M`/`F` shapes raise `ValueError`.
5. [x] Implement `shift_moment_reference(mx, my, mz, fx, fy, fz, offset)` in `normalization.py`,
   computing the full three-component cross product with no special-casing.

## 2. Canonical documentation of the reference point

6. [x] **Test first** — `MomentCoefficients.__doc__` names the wing hinge, points at
   `docs/coordinate-convention.md`, does not contain "body center", and states the axes remain lab
   axes. Pin the exact phrase so the assertion is not an arbitrary substring.
7. [x] Add a `## Moments` section to `docs/coordinate-convention.md`, sibling to `## Forces`:
   lab-frame components about **the deck's declared pivot** (not "the wing root" — the geometry's
   own half-span is 1.475, putting the root at `y = 0.525`, 1.7% off the declared `hinge_y = 0.5`);
   axes **not** rotated (a wing-frame moment needs `R(t)ᵀM`, issue #1); raw solver columns about the
   particle origin vs derived coefficients about the hinge; centre-of-mass deferral.
7a. [x] In the same section, resolve the **page-level frame collision**: the page's axis table is
   headed "wing reference frame" while the new section declares lab-frame moments. State that the
   axis table is the rest-pose-aligned frame, in which lab and wing axes coincide only at
   `φ = α = θ = 0`, and that forces are reported body-frame while moments are lab-frame.
8. [x] Supply a **verbatim** van Veen quotation for the origin claim, matching the form of the
   existing axis-direction quote. Drop the *world*-frame half of the claim unless it can be quoted —
   no in-repo source corroborates it. Do not repeat the species framing (issue #79).

   **Done in full.** Initially landed as the narrowed variant (paper not in the repo); the passage
   was then retrieved from the open-access article and both halves are now quoted verbatim:
   - wing frame — "a right-handed coordinate frame with the origin at the wing hinge location"
   - world frame — "a right-handed world reference frame with its origin at the root of the wing"

   Both are §2.4 ("Reference frames"). The world-frame half, dropped earlier as uncorroborated, is
   restored — it was correct.

   **Two corrections this surfaced in the existing page**, both now fixed:
   - The pre-existing "verbatim" axis quote was not verbatim: it rendered "the y-axis parallel to
     the wing tip" where the paper says "the y-axis parallel to the **surface pointing towards** the
     wing tip".
   - The page cited "the fig 2 caption"; the definition is in §2.4 and both sentences cite
     "(figure 1f)", which is what the axis table's own column header already said.

   Quotes were subsequently checked against the source passage supplied by the user and match
   exactly.

   **Resolved from the PDF: root and hinge are the same point in van Veen.** §2.2 states the wing
   "was placed with its root in the centre of a domain" — a single rigid plate, no body, no
   articulation — and §2.4 makes that root the world frame's origin. The hinge lands there too:
   stroke rotation is about `z_world` through the origin, pitch rotation about the wing's spanwise
   axis through its root, and the two axes intersect at the root, which is the only thing "the wing
   hinge location" can denote in a model with no joint.

   This question took three positions in one session — claimed, withdrawn, re-established. The
   withdrawal was correct on its own terms: the first argument inferred coincidence from the
   frames being related by Euler rotations "with no offset term", which proves nothing, since an
   orientation description never carries origin information. The conclusion is now grounded in the
   numerical set-up instead. Two traps are recorded in `docs/coordinate-convention.md` so the next
   reader does not repeat either: the Euler-angle non-argument, and figure 1f drawing the two
   triads apart for legibility.

   What this does and does not affect:
   - **Not** this change. Our moments stay lab-frame about our own deck's declared pivot throughout;
     the offset is derived from our decks, not from van Veen's frame definitions.
   - **Yes** the issue-#1 body-frame work, now favourably: `R(t)ᵀ` alone suffices, with no
     parallel-axis shift.
   - Our 0.025 hinge-vs-root gap is ours alone (deck `hinge_y = 0.5` vs blade root `y = 0.525`),
     where van Veen's root and hinge coincide exactly. Hence "the deck's declared pivot".
9. [x] Update the `MomentCoefficients` docstring to cross-reference rather than restate.

**PR1 ships a helper with no caller** — say so in the PR body.

---

# PR 2 — wire into extraction, guard, re-extract both corpora

## 3. Deck source and the three signature changes

10. [x] **Test first** — a config with no locatable deck raises `ValueError` naming the config and
    the resolved path — never a bare `TypeError`.
11. [x] **Test first** — a deck missing `particle_inputs.hinge_*`, or with a non-finite hinge,
    raises `ValueError` naming **both** config and deck path. (`read_deck_value` rejects non-finite
    but names neither, so a wrapping layer is required.)
12. [x] Update `_write_manifest` and `_validated_point_config` to emit `input_file` plus a minimal
    deck — **and** handle the four `COMMITTED_MANIFEST` sites from task 0 separately, since they
    resolve real decks and will see a real `(0, 1.5, 0)` shift.
13. [x] Implement deck resolution inside `build_dataset` (manifest `input_file` resolved against
    `Path(manifest_path).parent`, hinge via `geometry_guard.read_deck_value`). Because
    `acceptance_gate.py:64` already passes `manifest_path`, neither production call site changes for
    the directory.
13a. [x] Add the **offset return channel**: the derived per-config offsets must travel out of
    `build_dataset` with the data. Do **not** let the driver re-derive them — a second derivation
    can drift from the applied one, and the CI guard would then reconcile the driver's value while
    the parquet carries another.
13b. [x] Add an `extra` passthrough to `build_run_metadata` (`dataset.py:370-400`), whose `extra` is
    currently hardcoded to `{"dropped_configs": ...}`. `scripts/extract_forces.py:92-97` calls it,
    not `capture_surrogate_run_metadata`, so there is no channel for the frame record today.
13c. [x] **Test first** — `run_acceptance_gate` still returns `GateResult(passed, failures)` rather
    than raising, when a deck is missing / `X,Y,Z` absent / the origin moves. The new `ValueError`s
    would otherwise convert an enumerating gate into a traceback.

## 4. Origin columns and the shift

14. [x] **Test first** — `X,Y,Z` added to `_REQUIRED_CSV_COLUMNS`; a CSV lacking them raises the
    existing missing-column `ValueError` naming config and absent columns.
15. [x] **Test first** — a CSV whose `X,Y,Z` **varies** raises `ValueError` naming the config.
    Exact equality, no tolerance.
16. [x] **Test first** — constant-but-**NaN** `X,Y,Z` is rejected. Note the hazard is **pandas**,
    not numpy: `pd.Series([4.0, nan, 4.0]).max() - .min() == 0` is `True` and `.nunique()` is `1`,
    both of which *pass* a naive constancy check, while `np.ptp(...) == 0` and `all(x == x[0])`
    both correctly reject NaN. The guard must assert finiteness explicitly.
    **Implementation note (13c).** The gate catches a narrow `ConfigExtractionError(ValueError)`
    raised only by the per-config extraction checks, not `ValueError` in general. The extractor
    now also reads `run_metadata_<name>.json` for `deck_sha256`, and a blanket catch would have
    swallowed the malformed-JSON error that
    `test_acceptance_gate.py::test_malformed_run_metadata_json_raises_clear_file_identified_error`
    requires to raise. That test is outside the task-0 list and is unedited.
17. [x] **Test first** — a header-only CSV contributes zero rows without the origin guard raising
    on an empty array (both `np.ptp` and `x == x[0]` raise on empty, so an explicit length guard is
    needed either way).
18. [x] **Test first** — end-to-end through `build_dataset` with a **non-`(0,1.5,0)`** offset so a
    hardcoded constant fails: `CF_mx`/`CF_mz` equal `(Mx + a·Fz)/m_ref` and `(Mz − a·Fx)/m_ref`,
    `CF_my` unchanged.
19. [x] **Test first** — a two-config manifest whose decks differ in **`hinge_y`** (with nonzero
    `Fz`) emits correspondingly different `CF_mx`. Note decks differing only in `hinge_x` would
    leave `CF_mx` identical, so the fixture must vary the component that enters it.
20. [x] **Test first** — raw `Mx/My/Mz` stay bitwise equal to the CSV values.
21. [x] Implement the wiring in `dataset.py` at the raw-column read (`:186-193`).
22. [x] **Test first** — the corpus `run_metadata.json` records, under named keys, the moment
    reference point, the **per-configuration** offsets, the resolved `--input-dir`, and a
    **per-config sha256 of each consumed IB-particle CSV**; and `dataset.units.json` is unchanged in
    shape. Name the keys in the spec so writer and guard are not specified independently.
23. [x] Implement the provenance record through the task-13b passthrough.
23a. [x] **Test first** — extraction reconciles the deck it read against the run's recorded
    `deck_sha256` (present in every fine per-config `run_metadata_<name>.json`) and fails loudly on
    mismatch. This closes the mutable-deck/immutable-CSV gap. The coarse corpus has no per-config
    metadata and therefore no anchor — record that asymmetry as a known limitation.

## 5. Guards that land BEFORE re-extraction

24. [x] **Test first** — extend `tests/test_force_surrogate_scale_invariance.py`: for **both**
    committed parquets, derive the offset **from the committed deck**
    (`particle_inputs.{x,y,z} − particle_inputs.hinge_{x,y,z}`) — *not* from the `run_metadata.json`
    the same extraction wrote, which would make the guard blind to a sign flip — and assert
    **per config** (not per (stroke, freq) key, which groups 3 configs and can mask one):
    `CF_mx == (Mx + a·Fz)/m_ref`, `CF_mz == (Mz − a·Fx)/m_ref`, `CF_my == My/m_ref`, and that
    `CF_mx` is **not** `allclose` to `Mx/m_ref`.
    **Expected to fail against the not-yet-regenerated parquets — that is the point.** Commit before
    task 28 and paste the failure output in the PR body.
24a. [x] **Test first — the empirical sign discriminator (design D8.6).** Assert that the
    force-weighted spanwise arm `b = M_hinge_x / F_z` falls inside the physically sensible band
    `(0, 2.975]` (hinge `y = 0.5`, tip `y = 3.475`) for a **calibrated fraction** of settled-beat
    rows on both corpora — threshold ≥ 0.90 against a measured 96.8% (coarse) / 98.1% (fine).
    A sign flip gives 0.9% / 0.5%, so the 97%-vs-1% gap survives any reasonable threshold.

    Do **not** assert every row is in band. `b` is a mixed-sign-weighted mean (`f_z` changes sign
    across the wing), so it is not mathematically bounded by the wing's extent, and it omits the
    `−(z_i − z_h)·F_y` term of `M_x`. A hard bound would risk spurious failure on a corpus with
    different kinematics while adding nothing. Name in the test docstring that `F`/`M` are the
    spread IB force and moment only, so `b` is the IB-part arm rather than the true centre of
    pressure.
24b. [x] **Test first** — extend `tests/test_sweep_hinge_geometry.py` to parametrize
    `assert_hinge_at_span_root` over `glob("examples/prelim_sweep*/inputs/inputs.3d.*")`. It
    currently covers **2 base decks and zero of the 57 per-config decks** — one of those two being
    the *pilot* directory, not the fine corpus. This change makes all 57 numerically load-bearing.

    **Corrected in implementation: 54, not 57.** The glob as written fails on the pilot's three
    per-config decks, which carry `hinge_y = 2.0, hinge_z = 2.5`. That is the pre-#71 midspan pivot
    the pilot actually ran with. Only the pilot's *base* deck was corrected afterwards, and the
    pilot report is test-pinned to flag the defect (`test_fine_pilot_deck.py`). Those decks are a
    historical record and no dataset is extracted from them, so they are not load-bearing here, and
    "fixing" them would falsify the record. The guard covers the 54 decks of the two extracted
    corpora, and a separate test pins the three pilot decks *as* the known defect, so a later edit
    or glob widening cannot turn them silently green.
25. [x] Mint a `_FROZEN_RAW_FORCE_SHA` equivalent for `examples/prelim_sweep_fine` from the
    **committed** parquet. Land it in a commit that touches **no parquet**, before the
    re-extraction commit, with its own green CI run — otherwise a SHA minted from the *new* parquet
    is indistinguishable from one minted from the old and launders any raw-column corruption.
26. [x] Commit the task-30 gate as a script under `scripts/`. It MUST read its baseline from
    `git show HEAD:<path>` into a temp file and print the baseline blob SHA in its output, so the
    pasted stdout proves which side it compared against. Comparing the re-extracted file to itself
    would pass every item vacuously.

## 6. Re-extract both corpora — OPERATOR-RUN, NOT CI-GATED

> Requires the `Z:` NFS mount. Extraction runs on **Windows**. Evidence: gate script committed, full
> stdout in the PR body, regenerated `run_metadata.json` committed.

27. [x] *(Read-only half done 2026-09-28: `Z:/users/eberrigan/mosquito-cfd/examples/{prelim_sweep,
    prelim_sweep_fine}/runs/` each hold 27 `IB_Particle_1.csv`. The zero-offset control, run in
    memory with nothing written, reproduces all 22 columns of both committed parquets, including
    raw digests `02b04f46…` / `26663019…`, and all 27 fine decks reconcile against their runs'
    `deck_sha256`. Beware the sibling `prelim_sweep_fine_runs_pr91_snapshot_20260918/`: that is
    the superseded #91 run and the wrong `--input-dir`.)*
    Precheck `Z:` is mounted and non-stale. Run under the locked environment
    (`git diff --exit-code uv.lock` afterwards) — the parquet's `str` dtype is pandas-version-coupled.
28. [x] Re-extract `examples/prelim_sweep/dataset.parquet` (+ sidecar + metadata) from its runs
    directory, deriving `--docker-digest` programmatically from the committed `run_metadata.json`
    (`sha256:07625ce4…`).
29. [x] Re-extract `examples/prelim_sweep_fine/dataset.parquet` (+ sidecar + metadata) with its
    **own, different** digest (`sha256:92817878…`).
30. [x] **Verification gate**, per corpus, against the `git show HEAD:` baseline: `Fx..Fz`,
    `CF_x/CF_y/CF_z`, `My`, `CF_my`, `config_name`, `split`, and row counts **per config** all
    unchanged; exactly `CF_mx`/`CF_mz` differ; `dropped_configs == []`; regenerated `docker_image`
    equals the committed one. Note row counts **cannot** discriminate the corpora — both have
    identical per-config `max_step` maps summing to 109,656 — so only the raw-force SHA tripwires
    distinguish a swapped `--input-dir`.
30a. [x] **Zero-offset end-to-end control (design D11)** — run the new extractor over the real `Z:`
    CSVs with the offset forced to zero; the emitted parquet must be value-identical to the
    committed pre-change parquet across all 22 columns. Isolates "the rewired pipeline changed
    something" from "the shift changed something".
30b. [x] **Algebraic control (design D11)** — derive corrected `CF_mx`/`CF_mz` from the *old*
    committed parquet in pandas and assert value-equality with the re-extracted columns. Gives a
    reviewer without `Z:` a way to regenerate the target from first principles.
31. [x] Tasks 24/24a/25 now pass. Paste all outputs in the PR body.
32. [x] Run the corpus acceptance gate on the fine corpus. Note honestly that it is **near-vacuous
    for this change** — its symmetry and tripwire checks operate on `CF_x` only; the moment-relevant
    part is `check_no_nan_or_inf` over `CF_m*`.

> **Do not push a corpus regeneration you have not already gated.** Before the push the blobs are
> unreferenced and `git reset` prunes them for free.

## 6a. PR2 review round 1 (5-reviewer team on #118) — addressed in PR2

32a. [x] **BLOCKING — the PR1 "not yet applied" markers outlived the gap.** Both
    `docs/coordinate-convention.md` `## Moments` and the `MomentCoefficients` docstring still said
    the committed corpora satisfy `CF_mx == Mx / m_ref`, which became false once PR2 re-extracted them.
    The coordinate-convention spec requires the marker to be removed "in the increment that wires
    the shift into extraction", and this task list had no task for it. Both are removed.
    **Task-0 exception, recorded:** the two tests pinning the marker,
    `test_force_surrogate_normalization.py::test_moment_coefficients_docstring_flags_the_shift_as_not_yet_applied`
    and `test_new_convention_deck_and_docs.py::test_coordinate_convention_doc_flags_the_shift_as_not_yet_applied`,
    were not on task 0's list. Their own docstrings said to remove them in this increment. Each is
    inverted to assert the marker is **absent**, which enforces the spec's removal clause. This is
    not the shift leaking beyond `CF_mx`/`CF_mz`: neither test pins a number.
32b. [x] `extraction_inputs.input_dir` is recorded as given (posix separators) instead of
    `Path.resolve()`d. Resolving `Z:` had recorded a machine-specific UNC path naming internal
    infrastructure. The spec delta is amended accordingly.
32c. [x] `extract_forces.py` captures provenance **before** writing outputs, so `git` records the
    tree extraction ran from rather than one its own parquet had already dirtied, and a provenance
    failure leaves no new parquet. Both corpora are re-extracted from a clean committed tree. The
    parquet writer was verified byte-deterministic (same sha256 on rewrite), so this adds no blobs.
32d. [x] `build_dataset(..., run_metadata_paths=)` lets the acceptance gate reconcile decks against
    the metadata files it was given, instead of silently finding none beside the manifest.
32e. [x] A non-UTF-8 deck, a run-metadata file that is not a JSON object, a non-string
    `deck_sha256`, and non-numeric `X,Y,Z` cells now raise `ConfigExtractionError` naming the config
    and file. Previously they escaped as `UnicodeDecodeError`, `AttributeError` or a bare
    `ValueError`. `deck_sha256` compares case-insensitively.
32f. [x] CI guards tightened:
    - `CF_my` compares **equal** to `My/m_ref` on committed data (D8.2).
    - A new guard reconciles each committed `run_metadata.json`'s `moment_reference` against the
      decks and its `docker_image` against the CFD runs' own digest records.
    - The CoP test is renamed `..._ib_part_arm_...` (D8.6: not the centre of pressure).
    - "mid-span" wording is removed (D8.5).
    - The non-finite-origin, hash-message and driver-key assertions cover the gaps mutation found.
32g. [x] The gate script refuses non-spanwise offsets outright (its unchanged-column set assumes
    `d_x = d_z = 0`), reports `git` failures with git's message, resolves the repo root before
    `relative_to`, re-hashes CSVs against the recorded `csv_sha256` under `--zero-offset-control`,
    and documents that post-merge re-verification needs `--baseline-ref fea817a`.
32h. [x] `examples/prelim_sweep/README.md` carries a staleness banner for `surrogate/` and
    `figures/`. A test ties the banner to the actual state: it must be present exactly while
    `holdout_predictions.parquet`'s `CF_m*_true` disagree with the dataset. PR3's retrain therefore
    has to remove it. A BREAKING `### Changed` entry is added to `docs/CHANGELOG.md` now (task 45
    extends it in PR3).
32i. Deferred to #119: the acceptance gate stops at the first `ConfigExtractionError` instead of
    enumerating; `input_file`/config-name path escaping; the posix form of `inputs.file`.

## 6b. PR2 review round 2 (5-reviewer team on #118, head `29e69ce`) — addressed in PR2

Round 2 found no blocking issue and no regression. Each item below is test-first where it changes
behaviour.

32j. [x] **Staleness banner scope.**
    - Problem: the banner said "`CF_my` and the forces are unchanged". That is true of the dataset
      columns, but the surrogate is one shared-trunk model selected on an aggregate over all six
      targets, so **every** metric and evidence-figure number comes from the old training run.
      `figures/` also holds wing-phase geometry plots that the moment change does not touch.
    - Fix: reword the banner to name `surrogate/` and the evidence figure.
    - Test first: the banner test also ties `metrics.json`'s `CF_mx`/`CF_mz` R² to
      `holdout_predictions.parquet`. With the existing
      `test_committed_figure_metrics_matches_committed_inputs`, that chains dataset →
      predictions → metrics → evidence figure, so the figure cannot go stale unseen.
32k. [x] **Anchor the coarse decks.**
    - Problem: every coarse run's own `<runs>/<name>/run_metadata.json` on `Z:` records a
      `deck_sha256` (27/27 match the committed decks). `extract_forces.py` had no way to point at
      it, so the coarse record said "unverified" for a check that passes.
    - Fix: add `--run-metadata-name` to `extract_forces.py`, resolved as
      `<input-dir>/<name>/<run-metadata-name>`; the default stays the files beside the manifest.
      `deck_sha256_verified_against` records the anchoring file's path as given (posix), not its
      basename.
    - Test first: the driver honours the flag; a stale anchor in the runs directory fails
      extraction.
32l. [x] **Non-numeric and boolean CSV values, and undecodable metadata, are named `ConfigExtractionError`s.** (Retitled in round 3: empty, `NaN` and `inf` cells still pass this check; deferred to #119, see 32x.)
    - Problem: a non-UTF-8 run-metadata file escaped as a bare `UnicodeDecodeError`. Non-numeric
      `iStep`/`time`/`Fx..Mz` cells escaped as a bare `ValueError`/`TypeError` with no config
      name. A boolean `X` column was silently read as 1.0.
    - Fix: validate every required CSV column as non-boolean numeric up front, which supersedes
      32e's origin-only conversion check.
    - Test first: one case per column, plus the undecodable metadata.
32m. [x] **Outputs are all-or-nothing.**
    - Problem: `extract_forces.py`'s comment claimed a failure leaves no new parquet beside stale
      metadata, which held only for a provenance failure. A failed units or metadata write still
      left a new parquet.
    - Fix: write all three outputs to temporaries beside their targets, and move them into place
      only after every write succeeded.
    - Test first: a failing units write leaves a pre-existing parquet byte-unchanged and no
      temporary behind.
32n. [x] **Close the mutation survivors on the round-1 guard surface:**
    - `input_dir` recorded verbatim: test with a non-canonical path (M8/M8b); the committed guard
      rejects a UNC-style value.
    - The committed-provenance guard checks:
      - each `deck_sha256` against the committed deck;
      - each fine `deck_sha256_verified_against` file's own `deck_sha256`;
      - `origin` against the deck's particle position and `hinge` against its hinge;
      - `applies_to`, `raw_moments_about`, `definition` and `offset`.
    - The gate script's CSV re-hash is tested through `main()` (N13), with missing and extra keys
      (N11/N12).
    - The non-spanwise refusal is tested for `d_z ≠ 0` (N9).
    - A config absent from `run_metadata_paths`, and an empty mapping, are each tested as
      unverified (N1/N2).
    - The non-string-`deck_sha256` and git-stderr tests match text only the intended path
      produces (N4/N10).
    - The write-ordering test matches the mutable-tag message.
32o. [x] **Docstrings and comments current:**
    - one canonical list of `ConfigExtractionError` causes (class docstring), which the gate
      comment and `Raises:` reference;
    - the verify script's docstring covers the CSV re-hash and post-merge use;
    - the `acceptance_gate.py` module docstring mentions `deck_sha256`;
    - drop `extract_forces.py`'s stale "once PR3's real corpus exists";
    - describe the coarse CFD digest source accurately (an operator record for #71,
      cross-checked against the NFS run metadata);
    - `write_dataset`'s "not byte-reproducible" becomes "not guaranteed across pyarrow/pandas
      versions" (it was byte-identical on rewrite under the locked environment);
    - task 39's "Expect `dirty: true`" is stale.
32p. [x] Re-record both corpora's `run_metadata.json` from a clean tree: coarse with
    `--run-metadata-name run_metadata.json`, fine with its committed per-config files. Re-run the
    gate against `fea817a`. The parquets must stay byte-identical, so no new blobs.
32q. Deferred to #119, with the round-1 deferrals:
    - a metadata path that is a directory is treated differently by `build_dataset` and the gate;
    - `deck_sha256` format validation;
    - a UTF-8 BOM hiding a deck's first key;
    - LFS-aware baseline reads in the verify script;
    - cwd-independent test paths;
    - two PR1-era wording items: `tests/fixtures/README.md` calls `(4,2,4)` the mid-span point,
      and `docs/coordinate-convention.md` equates the IB hinge moment with the actuation torque.

## 6c. PR2 review round 3 (scoped to the round-2 delta `44241c1..3d5833d`) — addressed in PR2

Two reviewers (testing, edge cases) found no blocking issue and re-verified the data from `Z:`
byte-for-byte. Both found independently that 32m overclaimed.

32r. [x] **Output writes: say what is true, and narrow the window.**
    - Problem: 32m claimed "a failure leaves the previous outputs unchanged". That holds only while
      writing. The temporaries were moved in the order parquet, units, metadata, so a later move
      failure (on Windows, any open handle or a read-only attribute) left a new parquet beside
      stale metadata, and `finally` then deleted the new metadata's temporary.
    - Fix: three renames cannot be atomic.
      - Move the parquet **last**, so the provenance is in place before the data changes.
      - On a move failure, raise an error naming which outputs were already replaced, and keep
        the unmoved temporaries so the operator can finish or discard them.
      - Make cleanup of a stale temporary tolerate an `OSError`.
      - Reject duplicate output paths, which previously succeeded and silently lost an output.
    - Narrow the spec scenario and the docstring to match.
    - Test first: inject an `os.replace` failure on the second move, and assert the parquet is
      unchanged, the error names what was replaced, and the remaining temporary survives. Run the
      directory-target test over all three outputs (M10). Detect leftovers by comparing directory
      snapshots, not by name (M17). Add a duplicate-path test.
32s. [x] **The coarse deck anchors are actually checked.**
    - Problem: the CI guard accepted any coarse anchor ending in `/<name>/run_metadata.json`,
      including one pointing into the fine corpus, a `nowhere/` path and a UNC path. Its
      docstring claimed the gate script re-checked the anchor, which it did not.
    - Fix:
      - The CI guard requires each coarse anchor to equal
        `<recorded input_dir>/<name>/run_metadata.json`.
      - It rejects a network-path anchor for both corpora.
      - Under `--zero-offset-control`, the gate script re-extracts with the recorded anchors as
        `run_metadata_paths` and reports whether each deck re-verifies against the same file.
    - Test first: a pure comparison of anchors, plus the wiring through `main()`.
32t. [x] **`--run-metadata-name` fails closed.**
    - Problem: a misspelled or empty name silently left every deck "unverified" with exit code 0,
      although the flag is an explicit opt-in to verification.
    - Fix:
      - With the flag given, every extracted config must be anchored, otherwise extraction fails
        before anything is written.
      - A name containing a path separator, `..`, or an absolute path is rejected.
      - Combined with `--allow-missing`, dropped configs need no anchor (M15).
    - Test first.
32u. [x] **The anchor-as-recorded test uses a non-canonical input directory (M09)**, so that
    recording a resolved path would be caught.
32v. [x] **Wording:**
    - the `_verify_deck_sha256` docstring;
    - the README banner names the evidence figure's own provenance files too;
    - the spec's "path as given" becomes "posix form";
    - the stubbed `--zero-offset-control` `main()` test says its zero-offset line is a placeholder.
32w. [x] **Re-record both corpora's `run_metadata.json`** at the new commit, so the recorded commit
    is again exactly the extractor that ran. Re-gate against `fea817a`. The parquets must stay
    byte-identical.
32x. **Deferred to #119:**
    - empty, `NaN` and `inf` CSV cells pass the numeric check (pre-existing, absent from the real
      data);
    - an empty `iStep` cell is misreported as "non-monotonic";
    - a fractional `iStep` is accepted.

---

# PR 3 — retrain, regenerate the figure, refresh prose

## 6d. PR3 pre-implementation review (2026-10-16, 5-reviewer `/review-openspec`, at `7cf545e`)

The PR3 block below was written in 2026-09, before PR2's three review rounds, and was amended after
a review against what #118 actually merged. Decisions taken with the user:

- **The issue-#1 pointers are reworded, as a spec amendment.** Issue #1 is closed and no new issue
  is opened, so docs that pointed the wing-frame conversion (`R(t)ᵀM`) at it now say "deferred, not
  currently tracked". This change's own delta specs required the "issue #1" wording in five places
  (force-surrogate `:21, :434, :448, :538`; coordinate-convention `:19`); those are amended, and the
  two tests pinning it (task 0b) are re-pinned. This is the spec changing, not the shift leaking
  beyond `CF_mx`/`CF_mz`.
- **Training records its dataset.** `build_training_metadata` passed no `inputs_file`, so no
  committed record said which parquet trained `surrogate.pt`. New requirement "Committed surrogate
  artifacts are tied to the dataset they were trained on" (tasks 35b-35c).
- **The flapping-wing V3 validation figure is out of scope** (task 47a).
- **The noise floor uses two reruns**, not one (task 35).
- **Two #115-adjacent clauses are corrected** in "Honest evidence-figure caption", because this
  change already rewrites that requirement and would otherwise re-archive them: the targets that
  "read as dominant" (named CF_x, which is now negative) and the negative-R² "tell" (named CF_y,
  which is now +0.811; the code names the most negative of the six). #115's numbers are untouched.

Tasks are listed in **execution order**; the original numbers are kept so earlier cross-references
still resolve, which is why 33/34 sit after 39.

0b. [x] **Task-0 blast radius, PR3 additions** (each edit below is authorised by a decision above or
    by 32h; any other test needing an edit still halts the change):
    - `tests/test_force_surrogate_evidence_figure.py:470` (caption must reference issue #1) and
      `:779` (README must contain "issue #1") — re-pinned to the lab-frame / "not currently tracked"
      wording (task 46a).
    - `tests/test_force_surrogate_evidence_figure.py:788` (`~468` literal) — read from the sidecar
      (task 42). Pins checked but not expected to change: `:84` ("20 passes of 12535 rows" in a
      fixture), `:246/:511/:808` (`batch_size == 12535`, the holdout row count, invariant), `:308`
      (`"2.4" not in cap`), `:785` (`"2.4" not in readme`), `:780` (`cf_mx`/`cf_mz`).
    - `tests/test_force_surrogate_sweep.py:1015-1037` — docstring, `reason`, and the
      `cluster_workflows` assertion (task 34).
    - `tests/test_force_surrogate_scale_invariance.py:412` (staleness banner) — **not** edited: it
      flips from "banner required" to "banner forbidden" by itself once the retrained predictions
      match the dataset, which is the point of 32h.
    - Expected green and **not** edited: `test_flapping_wing_validation_figures.py:88-90` (reads the
      coarse holdout but compares in `tmp_path`; see 47a), `test_no_false_diffused_ib_claim.py`.

## 7. Guards and prose that do not depend on the retrain — land BEFORE any GPU run

Training records `git.commit`/`dirty` at capture time (`train.py:957`, before outputs are written,
`git diff HEAD` ignores untracked files). Everything in this section is committed first so the
retrain runs from a clean tree whose commit holds the code and prose that produced it.

34. [x] **Test first** — rewrite `tests/test_force_surrogate_sweep.py::test_coarse_corpus_provenance_flags_downstream_regeneration_source`
    (`:1015`, docstring `:1016-1021`) so the record must name the change that produced the
    committed artifacts: `reason` names `fix-moment-reference-hinge` and #108; the CFD's own
    provenance (the two cluster workflow IDs and `docker_image_digest`) sits under a key that says it
    is the CFD run, separate from a record of the PR2 re-extraction and the PR3 local retrain; no
    record claims a cluster workflow produced the re-extraction or the retrain. Replaces the
    `cluster_workflows` truthiness assertion (`:1033`). Red until task 33.
    *Done `c853570` (red by design until 33). Kept `docker_image_digest` at its path; the old `cluster_workflows` became `cfd_cluster_workflows`, with `re_extraction`/`retrain` records each carrying `cluster_workflows: []`. Mutation: 15/15 killed.*
33. [x] Rewrite the **coarse** `examples/prelim_sweep/sweep_provenance.json`
    `downstream_artifacts_regenerated_from` to satisfy task 34. **Keep `docker_image_digest`'s value
    and its read path** — `_cfd_digests` (`test_force_surrogate_scale_invariance.py:339`) reads it as
    the coarse CFD digest; if the key moves, move the reader in the same commit. The **fine** corpus
    gets **no** record: it has no such block, is not retrained here, and its moment provenance lives
    in its `run_metadata.json` `moment_reference`.
    *Done `7cfab3b`. `dataset.units.json` is not listed as re-extracted: PR2 left it byte-unchanged (`git diff --stat fea817a 5ffed81`).*
35b. [x] **Test first** — CPU unit test: `build_training_metadata(..., dataset_path=p)` records
    `inputs.file` naming `p` and `inputs.hash == sha256(p)`; and `run_training` passes its
    dataset through (assert on the `run_metadata.json` a tiny CPU `run_training` writes). The
    parameter is **optional**, so the three existing callers
    (`test_force_surrogate_train.py:534, :552`, `test_force_surrogate_train_gpu.py:168`) stay
    unedited; task 39a is what makes its absence from the committed artifact fail CI.
    *Done `6a48074` (CPU tests + a GPU-tier `run_training` passthrough test). Mutation: 5/5 killed on the CPU tests; the `run_training` passthrough is torch-tier, covered by the GPU test and by 39a on CI.*
35c. [x] Implement: `build_training_metadata` takes the dataset path and passes it as
    `inputs_file` to `capture_surrogate_run_metadata`; `run_training` supplies it. Fix
    `scripts/train_surrogate.py:13-14`, whose docstring says `--out-dir examples/prelim_sweep` —
    that would overwrite the corpus `run_metadata.json` (PR2's moment-reference provenance); the
    correct directory is `examples/prelim_sweep/surrogate`.
    *Done `6a48074`. A named-but-missing dataset raises `FileNotFoundError` (the base capture would silently record no `inputs`).*
39. [x] **Test first** (red today: `surrogate/run_metadata.json` holds only `git.error`) — CI-runnable,
    no GPU:
    - `surrogate/run_metadata.json` and `figures/run_metadata.json` each have a 40-hex
      `git.commit`, `branch == "fix-moment-reference-hinge-pr3"`, `dirty is False`, and no `error`
      key (the `{commit, source}` docker-build-arg fallback shape, `metadata.py:205`, fails this).
    - Both corpus `run_metadata.json` keep `branch == "fix-moment-reference-hinge-pr2"` and
      `dirty is False`.
    - `figures/run_metadata.json` `inputs.hash` equals sha256 of the committed
      `holdout_predictions.parquet`, and its `metrics_json_sha256` equals sha256 of the committed
      `surrogate/metrics.json` (written at `evidence_figure.py:618`, never asserted today).
    - The recorded commits do not survive the squash-merge as ancestors; they resolve via
      `refs/pull/<n>/head`.
    *Test written `03dee7a`, in the new `tests/test_committed_surrogate_provenance.py` (no existing test edited). Red today for the surrogate (`git.error`) and figure (`dirty`, stale branch) records, green for both corpus records and the figure hashes. Mutation on the green parts: 13/13 killed. Re-run mutation on the surrogate/figure parts after task 40.*
39a. [x] **Test first** (red today for `CF_mx`/`CF_mz`) — unconditional: every `<target>_true` in
    `examples/prelim_sweep/surrogate/holdout_predictions.parquet`, for all six targets, equals
    `dataset.parquet` on `(config_name, time)`; and `surrogate/run_metadata.json` `inputs.hash`
    equals sha256 of the committed `dataset.parquet`. Unlike the banner test, no state passes with
    a mismatch, and it covers `CF_x/CF_y/CF_z/CF_my`, which the banner test does not.
    *Test written `03dee7a`; red today (`CF_mx: 12535 holdout rows differ`). Positive control: with the pre-#108 parquet (`fea817a`, blob `55b74a8f`) swapped in, it passes — it discriminates exactly the target change.*
42. [x] **Test first** — replace the `~468` literal (`test_force_surrogate_evidence_figure.py:788`)
    with a check that the README states `~{round(latency_speedup)}×` read from the committed
    `evidence_figure_metrics.json`. Green against today's artifacts. Any new prose must also pass
    `"2.4" not in readme` (`:785`): numbers such as "32.4%" or "≈2.45" trip it.
    *Done `ab2e271`. Mutation: 4/4 killed.*
41b. [x] **Test first** — the `CF_mx`, `CF_mz` and `CF_my` config-resolved R² quoted in the README's
    honest-reading passage match `metrics.json` `config_resolved.<c>.config_mean_r2` at the stated
    precision. Green against today's artifacts; it forces task 41 to move the numbers with the data.
    *Test written `ab2e271`; red today only because the README never quotes `CF_mz`'s R², which the spec scenario requires. Mutation-test after task 41.*
46a. [x] Reword the issue-#1 pointers to "deferred, not currently tracked", and re-pin
    `test_force_surrogate_evidence_figure.py:470` and `:779` to assert "lab-frame" plus "not
    currently tracked":
    - `docs/coordinate-convention.md:108-110` and the heading at `:168` ("Consequence for any future
      wing-frame moment conversion (deferred, not currently tracked)");
    - `src/mosquito_cfd/force_surrogate/normalization.py:76` (`MomentCoefficients` docstring);
    - `src/mosquito_cfd/force_surrogate/evidence_figure.py:14`, `:54`, and the **rendered caption**
      at `:350` (the PNG changes in task 40, not before);
    - `examples/prelim_sweep/README.md:353-355`, which is also wrong on the facts: it calls the fix
      "a solver-level refactor + full cluster re-run", which T2a (#38) already did. The real reason
      the panel reports the `M_y` component is that moments are lab-frame about the hinge.
    *Done `7dcd74e`. Left alone, as history of what #1 did deliver (T2a): `docs/coordinate-convention.md:8,:68`, `benchmarks/flapping_wing.py:16`, `examples/flapping_wing/RESULTS.md`, `docs/aerodynamics_validation/roadmap.md`. Mutation: 6/6 killed.*
44. [x] `evidence_figure.py`: keep the invariants, drop the per-corpus specifics so the next corpus
    change need not edit them — `:16-18` (~470× / ~310×, already disagreeing with the README's
    468×), `:53-59`, and the example at `:292-293` (which target is the "tell"), which the retrain
    may falsify.
    *Done `14153e5`.*
43. [x] `docs/force_surrogate/roadmap.md`, stale since 2026-08-24:
    - rows 5-6 (`:190-196`): drop inline numbers (incl. row 6's ~468×/~310×); point at
      `surrogate/metrics.json` `config_resolved`, `figures/evidence_figure_metrics.json`, and the
      README's honest-reading section;
    - Vision `:18-20` and CC-4 `:102-103` claim the figure overlays the quasi-steady baseline; it
      reports it as a reference number and does not overlay it;
    - new PR-table rows: #61, #85/#86, #97→#100, #117/#118, this PR, and #110 as blocked-until-merge;
    - `:223-226` pilot "re-confirm before regeneration": superseded — the full 27-config fine corpus
      completed at `ns.cfl = 0.6` (#100);
    - `:233`: #20 is closed.
    Leave the CHANGELOG's #71 entries (`docs/CHANGELOG.md:49-50`) alone — append-only history.
    *Done `14153e5`. Also added rows for #58 and #71, absent from the table.*
46. [x] Disambiguate "corrected hinge" wherever touched: "corrected hinge geometry (#71)" for the
    deck fix (README `:341`, `:348`, `:362`), "hinge-referenced moments" / "moment reference point"
    for this change, never a bare "hinge fix".
    *`:341`/`:362` done `14153e5`; `:266`/`:348` carry retrain numbers and are reworded with task 41.*
41a. [x] Add the raw-vs-derived reference-point clause beside the schema note (README `~:196`) as a
    **cross-reference** to `docs/coordinate-convention.md#moments`, not a restatement.
    *Done `14153e5`.*
47. [x] Record that these need no change: `examples/prelim_sweep_fine/README.md` (no moment, R² or
    latency content), `examples/prelim_sweep/figures/README.md` (no numbers),
    `scripts/make_config_mean_collapse_diagnostic.py` / `openspec/project.md:410-421` (fixture
    outputs).
    *Recorded; no change to any of them.*
47a. [x] File a follow-up issue: `examples/flapping_wing/generate_validation_figures.py:121` reads
    the coarse `holdout_predictions.parquet`, and its committed `V3_scale_invariance.png` /
    `validation_figures_summary.json` are already stale (CF_x r² 0.9932 vs 0.99926) and become more
    so. Out of scope here; reference the issue in the PR body.
    *Filed as #124.*

## 8. Noise floor, then retrain — OPERATOR-RUN (WSL2 + local A5000)

> **Human checkpoint before the first GPU run.** Precondition for 35 and 36: §7 committed,
> `git status --porcelain` empty.

Environment for every GPU step: WSL2, `UV_PROJECT_ENVIRONMENT=$HOME/.venvs/mosquito-cfd-train` (on
ext4 — the worktree's Windows `.venv` must not be rebuilt as a Linux one), `uv sync --frozen --group
train`, and `--group train` on **every** `uv run` (a bare `uv run` may sync torch away). Run from the
worktree root and do **not** export `GIT_DIR`/`GIT_WORK_TREE` (the retry at `metadata.py:174-178`
handles the Windows worktree gitdir, #78). Leave `CUBLAS_WORKSPACE_CONFIG` unset: the committed
baseline ran without it, and setting it would shrink the measured floor to ~0 by changing the
protocol rather than measuring it.

35a. [x] **Pre-flight.** Inside WSL, `get_git_info()` prints a 40-hex commit, branch
    `fix-moment-reference-hinge-pr3`, `dirty: False` (a CRLF/filemode false-dirty would show here).
    Host, GPU and driver match the committed `surrogate/run_metadata.json` (`talmo-lab-02`, RTX
    A5000, driver 552.86); halt if not.
    *Done (2026-10-16): all match; `get_git_info()` in WSL gave `54127f6`, `-pr3`, `dirty: false`
    with no `GIT_DIR` export; torch 2.12.1+cu126 (CUDA available), physicsnemo 2.1.1, pandas 3.0.0,
    `uv.lock` unchanged. GPU-tier tests 7/7 in 21 s; removing `run_training`'s dataset passthrough
    fails the new GPU test (`KeyError: 'inputs'`). A run takes ~20 s, not the hours budgeted.*
35. [x] **Noise-floor control (design D9).** Write `git cat-file blob
    fea817a:examples/prelim_sweep/dataset.parquet` to the scratchpad (bash, not PowerShell
    redirection) and check `git hash-object` is `55b74a8f…`. Train on it **twice**, seed 1234, 2000
    epochs, `--device cuda`, `--wandb disabled`, `--docker-digest` taken from the coarse corpus
    `run_metadata.json` `docker_image`, `--out-dir` in the scratchpad (never under `examples/`).
    Record, for all six targets' `config_mean_r2`, the three pairwise deltas (run 1 vs run 2, each run
    vs committed). The run-vs-run delta is the floor proper; the run-vs-committed deltas are
    advisory, because the committed record carries no dataset hash and no commit. Record the table
    here and in the PR body as text; commit nothing from these runs.

    **Result: the retrain is bitwise-deterministic on this host.** Both reruns reproduce the
    committed surrogate exactly — `holdout_predictions.parquet` sha256 `de4f8793…` and
    `surrogate.pt` `71b77c50…` identical to the committed files; all six `config_mean_r2` deltas
    are 0. Only `metrics.json`'s `inference` block differs (wall-clock timing: latency 0.152 / 0.191
    ms vs committed 0.154, so the README's latency floor is a single timing sample that moves
    ~380-470× between identical runs). Design D9's premise (cuBLAS nondeterminism makes a retrain
    non-reproducible) does not hold here, so the floor is exactly 0. Under the rule as written,
    task 38a's tolerance would be 1e-6 and any data change would "fail" it by construction.

35d. [x] **Seed-variation control (added with the user, 2026-10-16, before any corrected run).**
    The reference that 35 was meant to supply is how much config-resolved R² moves under an
    irrelevant perturbation. Same pre-#108 parquet, same code, seeds 1235-1238 (scratchpad only):

    | target | 1234 (committed) | 1235 | 1236 | 1237 | 1238 | range |
    |---|---|---|---|---|---|---|
    | CF_x | −0.007 | 0.092 | −1.453 | 0.433 | 0.727 | 2.18 |
    | CF_y | 0.811 | 0.949 | 0.930 | 0.981 | 0.948 | 0.17 |
    | CF_z | 0.985 | 0.994 | 0.996 | 0.995 | 0.950 | 0.05 |
    | CF_mx | 0.993 | 0.994 | 0.999 | 0.972 | 0.972 | 0.03 |
    | CF_my | 0.507 | −0.458 | 0.193 | 0.688 | 0.807 | 1.27 |
    | CF_mz | 0.713 | −5.455 | −0.813 | −0.174 | 0.860 | 6.32 |

    **Config-resolved R² is strongly seed-dependent** for CF_x, CF_my and CF_mz: each is a
    cycle-mean R² over only the 6 holdout configs, and the shared-trunk model's between-config
    error moves with initialisation. Only CF_mx, CF_z and CF_y are seed-robust. Consequences:
    - several committed claims are seed-1234 artifacts: CF_x's negative R² (the caption's "tell";
      positive for 3 of the 4 other seeds) and "CF_mx ≈0.99 clearly beats CF_my ≈0.51" (CF_my
      reaches 0.81 at seed 1238);
    - the CF_my check is **vacuous** at this sample size: a 3× seed-spread tolerance (2.9 for
      CF_my, 18.5 over all six) cannot fail for a quantity bounded above by 1.
38a. [x] **Pre-registered before task 36 (revised with the user):** there is no pass/fail on
    `CF_my`. The comparison is **5-seed old vs 5-seed new** for all six targets: the corrected
    parquet is trained at seeds 1234-1238 too (1234 into `examples/prelim_sweep/surrogate/`, the
    committed artifact, protocol unchanged; 1235-1238 in the scratchpad, never committed). Report
    each target's old and new seed range, and where the committed seed-1234 corrected value falls in
    them. A target is said to have **moved** only if its old and new ranges do not overlap;
    otherwise the change is reported as within seed variation. Prose (task 41) states only claims
    that hold across all five seeds, or quotes the range. File an issue for multi-seed evaluation in
    the trainer and evidence figure, whose caption still prints single-seed numbers.
    *Original 38a, superseded by the revised 38a above (the floor is exactly 0, so this rule's
    1e-6 tolerance would fail any data change by construction):* floor = max |Δ| over the six targets
    and the three task-35 pairs; tolerance = 3 × floor (1e-6 if the floor is 0).
36. [x] Retrain on the corrected committed parquet with the same arguments, `--dataset
    examples/prelim_sweep/dataset.parquet --out-dir examples/prelim_sweep/surrogate` (seed 1234),
    after the seeds 1235-1238 scratchpad runs on the same parquet (task 38a), so those run from the
    clean tree too.
    *Done `8185268` (seed 1234 from the clean tree at `d13f06e`; recorded `dirty: false` and the corrected dataset's sha256 `01c88ae9…`). Seeds 1235-1238 ran first, in the scratchpad.*
37. [x] `git diff --exit-code uv.lock`; `library_versions` still `torch 2.12.1+cu126` /
    `physicsnemo 2.1.1`; `git diff --exit-code examples/prelim_sweep/dataset.parquet
    examples/prelim_sweep_fine/` (PR3 must not touch either corpus); `uv run --group train pytest -m
    gpu tests/test_force_surrogate_train_gpu.py` on the A5000.
    *Done: `uv.lock` unchanged; torch 2.12.1+cu126 / physicsnemo 2.1.1; neither corpus touched since #118; GPU-tier tests 7/7.*
38. [x] **Verification** — *(superseded by 38a: report the 5-seed old-vs-new comparison; no CF_my
    pass/fail)* |Δ `CF_my` config-resolved R²| (corrected vs committed) is within the
    task-38a tolerance; report pass/fail against that pre-registered number, and the multiple of the
    floor. Operator evidence, not a CI test: the target is invariant, the shared-trunk prediction is
    not. Record the new `CF_mx`/`CF_mz` (and all six) honestly whatever they are, each as a multiple
    of the floor.
    *Done (per 38a). No target's old and new 5-seed ranges are disjoint, so none moved beyond
    seed variation:*

    | target | old 1234 | old range | new 1234 (committed) | new range |
    |---|---|---|---|---|
    | CF_x | −0.007 | [−1.45, 0.73] | −4.171 | [−4.72, 0.48] |
    | CF_y | 0.811 | [0.81, 0.98] | 0.627 | [0.63, 0.99] |
    | CF_z | 0.985 | [0.95, 1.00] | 0.980 | [0.96, 1.00] |
    | CF_mx | 0.993 | [0.97, 1.00] | 0.957 | [0.96, 1.00] |
    | CF_my | 0.507 | [−0.46, 0.81] | 0.069 | [−1.96, 0.93] |
    | CF_mz | 0.713 | [−5.45, 0.86] | −8.449 | [−8.45, 0.92] |

    *The design's risk ("`CF_mx` skill will likely drop sharply") is not borne out across seeds.
    Seed 1234 is a low draw for CF_x, CF_y and CF_mz; committed anyway as pre-registered. Multi-seed
    evaluation in the trainer/figure is #125.*

> **Human checkpoint before committing binaries.** Push exactly one surrogate/figure version:
> blobs pushed to a PR head are permanent on GitHub even after a squash-merge. Review fixes that do
> not change the model go in commits with no binaries.

40. [x] Commit the four `surrogate/*` outputs (red by design: the figure sidecar no longer equals
    `metrics.json`). Then regenerate the evidence figure from that clean tree, so
    `figures/run_metadata.json` records `dirty: false` and that commit. Commit
    `figures/{evidence_figure.png,evidence_figure_metrics.json,run_metadata.json}` **together with**
    tasks 41c, 41 and 45, which makes the head green. Do not regenerate the wing-phase PNGs (they do
    not depend on `CF_m*`; re-rendering adds blobs for nothing).
    *Done: surrogate `8185268`, figure + README + CHANGELOG `0140425` (figure recorded `8185268`, `dirty: false`). Head green: 1316 passed. Mutation on the surrogate/figure halves of 39: 9/9 killed.*
41c. [x] Remove the README staleness banner (`examples/prelim_sweep/README.md:3-17`); the banner test
    then requires its absence.
    *Done `0140425`; the banner test now passes in its inverse direction.*
41. [x] Refresh every README number derived from `surrogate/` or `evidence_figure_metrics.json`,
    found by grep rather than a fixed line list, and mark each **changes** or **invariant** in the PR
    body:
    - changes: aggregate R² / "~99.9%" (`:262-263`, `:334`), the config-mean range (`:266`), the
      per-axis config-resolved R² (`:336`) and the claim that CF_x's is negative (`:337-339`, which
      may flip — rewrite the bullet's logic if so), the CF_mx-vs-CF_my ranking (`:348-349`, the
      headline the retrain may overturn), the timing numbers (`:371-375`, incl. the latency);
    - invariant (target-only or timing-independent): `:349` ≈0.005% (`within_config_variance_fraction`
      reads true targets only, `train.py:557-558`), the `:361-362` overshoot factors, `:372` N=12,535.
    *Done `0140425`. Also added the 5-seed range table and rewrote the two seed-1234 artifacts (the CF_x "tell", now "negative for 4 of 5 seeds"; the CF_mx-beats-CF_my ranking). The latency (~440×) is flagged as a single timing sample (~380-470× across identical reruns). Mutation on 41b: 8/8 killed.*
45. [x] Extend the existing #118 BREAKING `### Changed` entry (`docs/CHANGELOG.md:29-33`) rather than
    adding a second: replace "still reflect the old targets until the retrain" with the outcome (new
    `CF_mx`/`CF_mz` config-resolved R², `CF_my` against the noise floor), suffixed with this PR's
    number.
    *Done `0140425`. Replace `(#108)` with the PR number once opened.*

## 9. Close-out

48. [x] `uv run ruff check` / `ruff format --check` over the CI paths (`ci.yml:24,27`): `src/ tests/
    scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`.
49. [x] `uv run pytest -m "not gpu"` green, with the task-0/0b list reconciled — including the banner
    test passing with the banner **removed** (the inverse direction proves the retrain consumed the
    corrected parquet).
    *1316 passed, 14 skipped, 0 failed (`--group viz`, as CI).*
50. [x] Both parquets expose exactly `DATASET_COLUMNS` with committed dtypes; both sidecars
    round-trip through `read_units_sidecar`.
51. [x] `openspec validate fix-moment-reference-hinge --strict`
52. [ ] `/pre-merge-check`, including the 5-reviewer `/review-pr`. Before `/cleanup-merged`, check
    `grep -c '\[ \]' tasks.md` is 0 (`openspec list` does not count numbered-list checkboxes).
53. [x] *(PR2: 24.2 MiB of new parquet blobs, stated in #118 and on #102.)* State the ~26 MiB binary growth in the PR body for issue #102's evidence.
53a. [ ] State PR3's own share (~1.9 MiB: holdout parquet ~1.5 MiB, PNG ~0.27 MiB, `.pt` ~41 KiB) in
    the PR body and comment it on #102.
