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
   - The page cited "the fig 2 caption"; the definition is in §2.4 and is illustrated by fig 1(f),
     which is what the axis table's own column header already said. The citation now names §2.4.
9. [x] Update the `MomentCoefficients` docstring to cross-reference rather than restate.

**PR1 ships a helper with no caller** — say so in the PR body.

---

# PR 2 — wire into extraction, guard, re-extract both corpora

## 3. Deck source and the three signature changes

10. [ ] **Test first** — a config with no locatable deck raises `ValueError` naming the config and
    the resolved path — never a bare `TypeError`.
11. [ ] **Test first** — a deck missing `particle_inputs.hinge_*`, or with a non-finite hinge,
    raises `ValueError` naming **both** config and deck path. (`read_deck_value` rejects non-finite
    but names neither, so a wrapping layer is required.)
12. [ ] Update `_write_manifest` and `_validated_point_config` to emit `input_file` plus a minimal
    deck — **and** handle the four `COMMITTED_MANIFEST` sites from task 0 separately, since they
    resolve real decks and will see a real `(0, 1.5, 0)` shift.
13. [ ] Implement deck resolution inside `build_dataset` (manifest `input_file` resolved against
    `Path(manifest_path).parent`, hinge via `geometry_guard.read_deck_value`). Because
    `acceptance_gate.py:64` already passes `manifest_path`, neither production call site changes for
    the directory.
13a. [ ] Add the **offset return channel**: the derived per-config offsets must travel out of
    `build_dataset` with the data. Do **not** let the driver re-derive them — a second derivation
    can drift from the applied one, and the CI guard would then reconcile the driver's value while
    the parquet carries another.
13b. [ ] Add an `extra` passthrough to `build_run_metadata` (`dataset.py:370-400`), whose `extra` is
    currently hardcoded to `{"dropped_configs": ...}`. `scripts/extract_forces.py:92-97` calls it,
    not `capture_surrogate_run_metadata`, so there is no channel for the frame record today.
13c. [ ] **Test first** — `run_acceptance_gate` still returns `GateResult(passed, failures)` rather
    than raising, when a deck is missing / `X,Y,Z` absent / the origin moves. The new `ValueError`s
    would otherwise convert an enumerating gate into a traceback.

## 4. Origin columns and the shift

14. [ ] **Test first** — `X,Y,Z` added to `_REQUIRED_CSV_COLUMNS`; a CSV lacking them raises the
    existing missing-column `ValueError` naming config and absent columns.
15. [ ] **Test first** — a CSV whose `X,Y,Z` **varies** raises `ValueError` naming the config.
    Exact equality, no tolerance.
16. [ ] **Test first** — constant-but-**NaN** `X,Y,Z` is rejected. Note the hazard is **pandas**,
    not numpy: `pd.Series([4.0, nan, 4.0]).max() - .min() == 0` is `True` and `.nunique()` is `1`,
    both of which *pass* a naive constancy check, while `np.ptp(...) == 0` and `all(x == x[0])`
    both correctly reject NaN. The guard must assert finiteness explicitly.
17. [ ] **Test first** — a header-only CSV contributes zero rows without the origin guard raising
    on an empty array (both `np.ptp` and `x == x[0]` raise on empty, so an explicit length guard is
    needed either way).
18. [ ] **Test first** — end-to-end through `build_dataset` with a **non-`(0,1.5,0)`** offset so a
    hardcoded constant fails: `CF_mx`/`CF_mz` equal `(Mx + a·Fz)/m_ref` and `(Mz − a·Fx)/m_ref`,
    `CF_my` unchanged.
19. [ ] **Test first** — a two-config manifest whose decks differ in **`hinge_y`** (with nonzero
    `Fz`) emits correspondingly different `CF_mx`. Note decks differing only in `hinge_x` would
    leave `CF_mx` identical, so the fixture must vary the component that enters it.
20. [ ] **Test first** — raw `Mx/My/Mz` stay bitwise equal to the CSV values.
21. [ ] Implement the wiring in `dataset.py` at the raw-column read (`:186-193`).
22. [ ] **Test first** — the corpus `run_metadata.json` records, under named keys, the moment
    reference point, the **per-configuration** offsets, the resolved `--input-dir`, and a
    **per-config sha256 of each consumed IB-particle CSV**; and `dataset.units.json` is unchanged in
    shape. Name the keys in the spec so writer and guard are not specified independently.
23. [ ] Implement the provenance record through the task-13b passthrough.
23a. [ ] **Test first** — extraction reconciles the deck it read against the run's recorded
    `deck_sha256` (present in every fine per-config `run_metadata_<name>.json`) and fails loudly on
    mismatch. This closes the mutable-deck/immutable-CSV gap. The coarse corpus has no per-config
    metadata and therefore no anchor — record that asymmetry as a known limitation.

## 5. Guards that land BEFORE re-extraction

24. [ ] **Test first** — extend `tests/test_force_surrogate_scale_invariance.py`: for **both**
    committed parquets, derive the offset **from the committed deck**
    (`particle_inputs.{x,y,z} − particle_inputs.hinge_{x,y,z}`) — *not* from the `run_metadata.json`
    the same extraction wrote, which would make the guard blind to a sign flip — and assert
    **per config** (not per (stroke, freq) key, which groups 3 configs and can mask one):
    `CF_mx == (Mx + a·Fz)/m_ref`, `CF_mz == (Mz − a·Fx)/m_ref`, `CF_my == My/m_ref`, and that
    `CF_mx` is **not** `allclose` to `Mx/m_ref`.
    **Expected to fail against the not-yet-regenerated parquets — that is the point.** Commit before
    task 28 and paste the failure output in the PR body.
24a. [ ] **Test first — the physical bound (design D8.6).** Assert the force-weighted spanwise arm
    `b = M_hinge_x / F_z` lies in `(0, 3]` for the overwhelming majority of settled-beat rows on
    both corpora. Measured: correct sign gives 96.8% (coarse) / 98.1% (fine) in bounds with median
    ≈ 1.59; a sign flip gives **0.9% / 0.5%**. This is the only check that compares a number to
    physics rather than to our own bookkeeping.
24b. [ ] **Test first** — extend `tests/test_sweep_hinge_geometry.py` to parametrize
    `assert_hinge_at_span_root` over `glob("examples/prelim_sweep*/inputs/inputs.3d.*")`. It
    currently covers **2 base decks and zero of the 57 per-config decks** — one of those two being
    the *pilot* directory, not the fine corpus. This change makes all 57 numerically load-bearing.
25. [ ] Mint a `_FROZEN_RAW_FORCE_SHA` equivalent for `examples/prelim_sweep_fine` from the
    **committed** parquet. Land it in a commit that touches **no parquet**, before the
    re-extraction commit, with its own green CI run — otherwise a SHA minted from the *new* parquet
    is indistinguishable from one minted from the old and launders any raw-column corruption.
26. [ ] Commit the task-30 gate as a script under `scripts/`. It MUST read its baseline from
    `git show HEAD:<path>` into a temp file and print the baseline blob SHA in its output, so the
    pasted stdout proves which side it compared against. Comparing the re-extracted file to itself
    would pass every item vacuously.

## 6. Re-extract both corpora — OPERATOR-RUN, NOT CI-GATED

> Requires the `Z:` NFS mount. Extraction runs on **Windows**. Evidence: gate script committed, full
> stdout in the PR body, regenerated `run_metadata.json` committed.

27. [ ] Precheck `Z:` is mounted and non-stale. Run under the locked environment
    (`git diff --exit-code uv.lock` afterwards) — the parquet's `str` dtype is pandas-version-coupled.
28. [ ] Re-extract `examples/prelim_sweep/dataset.parquet` (+ sidecar + metadata) from its runs
    directory, deriving `--docker-digest` programmatically from the committed `run_metadata.json`
    (`sha256:07625ce4…`).
29. [ ] Re-extract `examples/prelim_sweep_fine/dataset.parquet` (+ sidecar + metadata) with its
    **own, different** digest (`sha256:92817878…`).
30. [ ] **Verification gate**, per corpus, against the `git show HEAD:` baseline: `Fx..Fz`,
    `CF_x/CF_y/CF_z`, `My`, `CF_my`, `config_name`, `split`, and row counts **per config** all
    unchanged; exactly `CF_mx`/`CF_mz` differ; `dropped_configs == []`; regenerated `docker_image`
    equals the committed one. Note row counts **cannot** discriminate the corpora — both have
    identical per-config `max_step` maps summing to 109,656 — so only the raw-force SHA tripwires
    distinguish a swapped `--input-dir`.
30a. [ ] **Zero-offset end-to-end control (design D11)** — run the new extractor over the real `Z:`
    CSVs with the offset forced to zero; the emitted parquet must be value-identical to the
    committed pre-change parquet across all 22 columns. Isolates "the rewired pipeline changed
    something" from "the shift changed something".
30b. [ ] **Algebraic control (design D11)** — derive corrected `CF_mx`/`CF_mz` from the *old*
    committed parquet in pandas and assert value-equality with the re-extracted columns. Gives a
    reviewer without `Z:` a way to regenerate the target from first principles.
31. [ ] Tasks 24/24a/25 now pass. Paste all outputs in the PR body.
32. [ ] Run the corpus acceptance gate on the fine corpus. Note honestly that it is **near-vacuous
    for this change** — its symmetry and tripwire checks operate on `CF_x` only; the moment-relevant
    part is `check_no_nan_or_inf` over `CF_m*`.

> **Do not push a corpus regeneration you have not already gated.** Before the push the blobs are
> unreferenced and `git reset` prunes them for free.

---

# PR 3 — retrain, regenerate the figure, refresh prose

## 7. Noise floor, then retrain — OPERATOR-RUN (WSL2 + local A5000)

35. [ ] **Noise-floor control (design D9).** Retrain on the **uncorrected** committed coarse parquet
    at seed 1234 on the same host; record the delta for **all six** targets' `config_mean_r2`, not
    just `CF_my` — the headline finding concerns `CF_mx`, which has no noise floor otherwise.
36. [ ] Retrain on the corrected parquet: `uv sync --frozen --group train`, then
    `scripts/train_surrogate.py` (seed 1234, 2000 epochs, `--device cuda`), run **from the worktree
    root** so `get_git_info`'s automatic retry fires (`metadata.py:187-192`). Do **not** export
    `GIT_DIR`/`GIT_WORK_TREE`.
37. [ ] Verify `git diff --exit-code uv.lock` and `library_versions` still
    `torch 2.12.1+cu126` / `physicsnemo 2.1.1`.
38. [ ] **Verification** — `CF_my`'s config-resolved R² stays within the task-35 noise floor (state
    the multiple). Not a strict invariance claim: the target is invariant, the shared-trunk model's
    prediction is not. Record the new `CF_mx`/`CF_mz` numbers honestly whatever they are.
39. [ ] **Test** — the committed `surrogate/run_metadata.json` **and both corpus
    `run_metadata.json` files** have a 40-hex `git.commit`, the expected `branch`, and no `error`
    key. CI-runnable, no GPU. (Expect `dirty: true`; the recorded `commit` will not survive
    squash-merge as an ancestor — the `branch` string is just a frozen field and is unaffected.)
40. [ ] Regenerate `examples/prelim_sweep/figures/`. **Same commit as task 36's outputs** —
    `test_committed_figure_metrics_matches_committed_inputs` asserts float equality between the
    figure sidecar and `metrics.json`.

## 8. Provenance records and prose

33. [ ] Update the **coarse** `sweep_provenance.json`'s `downstream_artifacts_regenerated_from` to
    record this change. Note the **fine** corpus has **no such block** and is not retrained here, so
    it needs a different (or no) record — do not assume symmetry. Reconcile with
    `tests/test_force_surrogate_sweep.py:1033`, which asserts `cluster_workflows` is truthy: this
    change involves no cluster run, so either the field's semantics or the assertion must change.
    **This task belongs in PR3**, because the record's `affected` list includes `surrogate/*` and
    `figures/*`, which PR2 does not regenerate.
34. [ ] **Test first** — extend `tests/test_force_surrogate_sweep.py:1015` so the `reason` names the
    change that actually produced the committed artifacts, not merely that a record exists.
41. [ ] Refresh **every** number in `examples/prelim_sweep/README.md` derived from the regenerated
    artifacts: the moment-ranking passage (`:327-338`), the config-mean range (`:249`), **and** the
    latency/throughput disclosures (`:358`). Add a clause at `:179` noting raw `M*` and derived
    `CF_m*` differ in reference point.
42. [ ] Re-pin or relax `tests/test_force_surrogate_evidence_figure.py:788` so the latency literal
    tracks the artifact. Check the rewritten prose against the brittle `"2.4" not in readme` guard
    at `:785`, the `cf_mx`/`cf_mz` substring assertion at `:780`, and
    `test_no_false_diffused_ib_claim.py`.
43. [ ] Update `docs/force_surrogate/roadmap.md:190-193` and add the roadmap PR-table row. Leave
    `docs/CHANGELOG.md:41`'s #71 entry alone — append-only history.
44. [ ] Update `evidence_figure.py:53-59` and `:292-295`: keep the invariant, drop the per-corpus
    specifics so the next corpus change need not edit it again.
45. [ ] Add a `### Changed` entry under `docs/CHANGELOG.md` `[Unreleased]`.
46. [ ] Disambiguate "corrected hinge" wherever touched — "hinge-referenced moments" or "moment
    reference point", never a bare "hinge fix".
47. [ ] Note explicitly that `examples/prelim_sweep_fine/README.md` needs no change.

## 9. Close-out

48. [ ] `uv run ruff check` / `ruff format --check` over the CI paths.
49. [ ] `uv run pytest -m "not gpu"` green, with the task-0 list reconciled.
50. [ ] Both parquets expose exactly `DATASET_COLUMNS` with committed dtypes; both sidecars
    round-trip through `read_units_sidecar`.
51. [ ] `openspec validate fix-moment-reference-hinge --strict`
52. [ ] `/pre-merge-check`
53. [ ] State the ~26 MiB binary growth in the PR body for issue #102's evidence.
