# Tasks — wing grid-convergence tooling + medium deck (T3a)

TDD throughout: each implementation task names the test written **first** and the behavior it verifies
**before** the code exists. `uv` for all Python. Branch: `add-wing-grid-convergence` (off `main`).
Cluster-free — everything is tested against the committed coarse run + synthetic fixtures.

## 1. Medium-grid deck (changes only the grid)

- [x] 1.1 **Test first (deck-invariance):** in `tests/test_convergence_deck.py`, add
  `test_medium_deck_changes_only_the_grid` — parse `examples/flapping_wing/inputs.3d.validation` (the
  canonical coarse deck; sha256 matches `run_metadata_t2a.json` `inputs.hash`) and
  `inputs.3d.convergence_medium` into `key → value` maps (strip `#` comments; **normalize each value's
  internal whitespace** via `" ".join(v.split())` so reformatting like `"2  2 2"` doesn't false-diff).
  Assert the **symmetric difference of differing keys is exactly `{amr.n_cell}`** (medium `128 64 128`,
  coarse `64 32 64`). **Also** assert `float(coarse["ns.fixed_dt"]) == float(medium["ns.fixed_dt"]) == 5e-4`
  and `float(coarse["particle_inputs.radius"]) == float(medium["particle_inputs.radius"]) == 1.5` (string
  `"0.0005"` ≠ `"5e-4"`, so parse as floats). Fails: medium deck missing.
- [x] 1.2 **Author** `examples/flapping_wing/inputs.3d.convergence_medium` by copying
  `inputs.3d.validation` and changing **only** `amr.n_cell` to `128 64 128` (header comment updated to
  "MEDIUM grid — Tier T3 convergence"; comments are ignored by the invariance test). 1.1 passes.

## 2. Wing grid-convergence grader (report-only 2-grid order-band GCI)

- [x] 2.1 **Test first (known-answer band + report-only + guards):** in
  `tests/test_wing_grid_convergence.py`, add `test_wing_grid_convergence_known_answer` — for
  `cf_coarse=0.92, cf_medium=0.80, r=2, safety_factor=1.25`, assert
  `relative_change == (0.80-0.92)/0.80` (`≈ -0.15`), `gci_p1 == 1.25*0.15/(2**1-1)` (`= 0.1875`),
  `gci_p2 == 1.25*0.15/(2**2-1)` (`= 0.0625`) — so **both orders are load-bearing** (a hard-coded `/3` would
  fail `gci_p1`). Assert `set(out) == {cf_coarse, cf_medium, relative_change, gci_p1, gci_p2, r}` with **no**
  `*_pass`/`*_match`/`converged`/`in_band` key **and no `cf_exact`/Richardson-extrapolant key**. Add
  `test_wing_grid_convergence_guards`: a near-zero `cf_medium` (below `_DEGENERATE_CF_FLOOR`) raises
  `ValueError` (not `ZeroDivisionError`/nan); an **opposite-sign** pair (`cf_coarse=+0.5, cf_medium=-0.4`)
  returns **finite** report values (`|relative_change| > 1`, large finite GCI band) — honestly "not
  converged," no error. Fails: function missing.
- [x] 2.2 **Implement** `wing_grid_convergence(cf_coarse, cf_medium, *, r=2.0, safety_factor=1.25) -> dict`
  in `src/mosquito_cfd/benchmarks/wing_convergence.py`: `relative_change = (cf_medium-cf_coarse)/cf_medium`
  (sphere `epsilon`, normalized by `cf_medium`); `gci(p) = safety_factor*|relative_change|/(r**p-1)` emitted
  at **p=1 and p=2** (the diffused-IB order band — 1st-order near-boundary to formal 2nd-order). **Do NOT
  emit a Richardson `cf_exact`** grid-independent estimate (part of the coarse↔medium delta is an
  IB-regularization model change with no Richardson limit — see design D3/D4; it is also redundant with the
  GCI). Guard `abs(cf_medium) >= _DEGENERATE_CF_FLOOR` (import from `flapping_wing`) → `ValueError`.
  Report-only, no verdict key. Docstring: the order is **unobservable** from 2 grids, diffused-IB force is
  **expected below 2nd order** (single p=2 understates uncertainty), **`gci_p1` is the reported band edge NOT
  a rigorous upper bound** (`gci→∞` as `p→0`; sub-1 order → larger GCI), and `relative_change < 0` means the
  coefficient **dropped** under refinement (the #40 direction). 2.1 passes.
- [x] 2.3 **Test first (end-to-end reuse of the body-frame stack):** add
  `test_convergence_from_csvs_reuses_body_frame`. A helper `wing_grid_convergence_from_body_forces(
  coarse_csv, medium_csv, *, f_star, phi_amp_deg, pitch_amp_deg, window_t0=STEADY_WINDOW_T0)` reconstructs
  the peak `CF_chord`/`CF_normal` from **both** CSVs via `reconstruct_wing_body_forces` +
  `body_frame_overall_match` (reused, not re-derived) and returns `wing_grid_convergence` per component.
  Test (a) **self-convergence:** coarse == medium == `forces_t2a_newconv.csv` → `relative_change == 0`,
  `gci_p1 == gci_p2 == 0` (same CSV ⇒ bit-identical peaks ⇒ exact `== 0` is safe, not `pytest.approx`);
  (b) **scaled medium:** a `tmp_path` CSV built by scaling
  **only `Fx/Fy/Fz`** by `k=0.85` (all other columns preserved) → each peak scales by `k` →
  `relative_change == (k-1)/k` (`≈ -0.17647`, **not** `k-1`, since the denominator is `cf_medium = k·cf_coarse`).
  Drives 2.4.
- [x] 2.4 **Implement** `wing_grid_convergence_from_body_forces` reusing `reconstruct_wing_body_forces` /
  `body_frame_overall_match`. 2.3 passes.

## 3. LEV vorticity / Q-criterion pure functions (reported diagnostic)

- [x] 3.1 **Test first (known analytic vorticity):** in `tests/test_lev_diagnostic.py`, add
  `test_vorticity_and_q_on_solid_body_rotation` — solid-body rotation `(u,v,w)=(−Ω·y, Ω·x, 0)` →
  `vorticity_magnitude == 2Ω` (interior, `abs≈1e-10`) and `q_criterion == Ω²`; pure shear
  `(u,v,w)=(γ·y,0,0)` → `|ω| == γ`, `Q == 0`. Fails: functions missing.
- [x] 3.2 **Implement** `vorticity_magnitude(u, v, w, spacing)` (`‖∇×u‖`) and `q_criterion(u, v, w,
  spacing)` (`Q = ½(‖Ω‖² − ‖S‖²)`, half-difference convention) in `src/mosquito_cfd/benchmarks/lev.py`
  (pure numpy via `np.gradient`). `spacing` accepts a **scalar** (isotropic) **or** a `(dx, dy, dz)` triple
  passed per-axis to `np.gradient` (so an anisotropic grid is not silently mis-differentiated). Reported, no
  gate; the yt plotfile→field wiring + the "LEV present" call are **T3b**. Docstring states the
  half-difference Q convention (not the `‖Ω‖²−‖S‖²` variant). 3.1 passes.
- [x] 3.3 **Test first (edge cases):** add `test_lev_edge_cases` — a uniform (zero-gradient) field → `|ω| ==
  0`, `Q == 0`; an **anisotropic** `(dx,dy,dz)` case that **guarantees** scalar≠triple by construction: use
  solid-body rotation `(−Ωy, Ωx, 0)` on a grid with `dy ≠ dx` (a **cross-axis** gradient `∂u/∂y` on the
  mis-spaced axis), assert the `(dx,dy,dz)` triple gives the analytic `2Ω` while a scalar `dx` gives the
  **wrong** `Ω(1 + dy/dx) ≠ 2Ω` (so the two genuinely differ — not a tautology); a field with exactly 2
  points on an axis raises `ValueError` (match `at least 3`), exactly 3 passes. Drives the guards + per-axis
  spacing in 3.2.

## 4. Traceability

- [x] 4.1 **Edit `docs/aerodynamics_validation/roadmap.md` — the T3 row cell itself, not just a note.** The
  T3 row currently states a **graded** oracle ("CF converged **within tol** … LEV present") and graded
  tier-name language ("Confirm CF grid-converged … LEV resolved"). Both must be **rewritten** to match the
  report-only decision (an unloosenable "within tol" with no tolerance behind it violates CC-V2). Rewrite
  the exit-criterion cell to: coarse↔medium **relative change + 2-grid GCI band (p=1..2)** on peak
  body-frame CF_chord/CF_normal — **reported, no pass bar**; LEV vorticity/Q **reported, not gated**; and
  soften "Confirm … converged/resolved" → "**quantify** grid sensitivity … **report** the LEV". Split the
  row into **T3a (this change: tooling+deck)** and **T3b (operator run + RESULTS)**, and add a
  reconciliation-log entry recording that **T3's original graded oracle is relaxed to a reported diagnostic**
  because a rigorous "converged" claim is not defensible from 2 grids + diffused IB, with the **true
  observed-order (3-grid/256³) study explicitly deferred to the H100/grant** (so T3 is not silently marked
  "done" on weaker evidence than its row demanded).
- [x] 4.2 **File the T3 tracking issue BEFORE `gh pr create`** (`gh issue create` → capture `#<T3>`, wire it
  into the PR body) — the T3 EPIC (medium-grid convergence), noting T3a delivers tooling/deck and T3b is the
  operator-run graded follow-up. Draft `docs/aerodynamics_validation/t3b-handoff.md`: **reference** the
  existing RESULTS.md "Run Commands (Reproducibility)" section and state only the **delta** — swap
  `inputs.3d.validation → inputs.3d.convergence_medium`, `:fp64 @ f93dc794`, the `capture_run_metadata` step,
  expected ~hours wall time, the ~8× box-count/memory scaling at 128³ (max_grid_size 32 → 64 boxes), and the
  CFL/dt fallback (design D4). Do not re-transcribe the full command.

## 5. Verification

- [x] 5.1 `uv run ruff check .` and `uv run ruff format --check .` clean.
- [x] 5.2 `uv run pytest` — full suite green (new + existing).
- [x] 5.3 `"/c/Users/Elizabeth/AppData/Roaming/npm/openspec" validate add-wing-grid-convergence --strict`
  passes.

## 6. Commit & PR discipline

- [x] 6.1 **Commit grouping** (atomic, CI-green each): (1) `chore(openspec)` — the **entire change dir**
  (`proposal.md`, `design.md`, `tasks.md`, **`specs/flapping-wing-grid-convergence/spec.md`**), docs-only,
  green; (2) `feat(flapping-wing)` — the deck + `wing_convergence.py` + `lev.py` (+ `__init__` export if
  new modules) + **all** §1–3 tests together (tests import the new code / read the new deck, so they may not
  precede it), green; (3) `docs` — the roadmap T3 row edit + T3b handoff, green (no doc-guard test exists in
  T3a, so the docs commit carries no red-until-doc trap). `ruff format` before each `src/`/`tests/` commit.
  **Every commit carries the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.**
- [x] 6.2 **#40 and the new T3 issue must NOT auto-close (G-1):** no commit message, PR title, or PR body may
  place a closing keyword (`close`/`fix`/`resolve` + variants) adjacent to **`#40` or the real T3 issue
  number** — **including in a negated clause** ("does not resolve #40" auto-closed #40 once already; see
  [[github-negated-closing-keyword-autocloses]]). T3a is only **half** the tier, so it must NOT close the T3
  issue either. **Actively suppress the repo's default `(closes #N)` PR-title convention** for both numbers.
  Reference them keyword-free, e.g. *"Unblocks Tier T4 (#40) — #40 stays open; part of Tier T3 (#NN),
  medium run + grading are T3b so #NN stays open."* PR title e.g. `T3a: wing grid-convergence tooling +
  medium deck (advances #40) (#<PR>)`. **Pre-merge grep** — first **substitute the captured T3 number for
  `NN`** in the pattern (and confirm the PR body uses that real number), then run it over the PR title+body
  AND every commit. The pattern allows an **optional colon** (`Closes: #40` is also a GitHub directive) and
  ignores what precedes the keyword (so it catches the negated form):
  `git log main..HEAD --format='%B' | grep -Ei '(clos|fix|resolv)[a-z]*:?[[:space:]]+#?(40|NN)'` — **must
  print nothing** (grep exits 1 on no-match, which is the PASS case; if wrapping in a `set -e` script, append
  `|| true` so the clean case doesn't abort).
- [x] 6.3 **Rollback note:** the three commits are effect-independent — `git revert` the `feat` commit backs
  out the deck+grader+LEV+tests without disturbing the openspec proposal or the docs.
