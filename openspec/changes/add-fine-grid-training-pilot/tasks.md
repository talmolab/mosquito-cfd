# Tasks — fine-grid training-data pilot

TDD for everything cluster-free; the actual CFD runs (Phase 2) are operator/live-cluster work,
not unit-testable. `uv` for all Python ops. Branch: `add-fine-grid-training-pilot` (off `main`).

---

## 0. Fine-grid base deck — cluster-free

- [ ] 0.1 Create `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` as an exact copy of
  `examples/prelim_sweep/base_inputs.3d.validation`, changing only `amr.n_cell` (`64 32 64` →
  `256 128 256`). Header comment documents this is the fine-grid pilot deck and why
  `ns.fixed_dt` is left at `5e-4` (untested-but-plausibly-stable, not pre-emptively dropped).
- [ ] 0.2 **Test first (deck invariance):** add `tests/test_fine_pilot_deck.py` with
  `test_fine_pilot_deck_matches_coarse_base_except_n_cell`. Parse both decks into `{key: value}`
  maps (reuse the parsing approach from `tests/test_convergence_deck.py`); assert the symmetric
  difference of keys is empty; assert `amr.n_cell` is `"256 128 256"` in the fine pilot deck and
  `"64 32 64"` in the coarse base; assert every other value is identical. Fails: deck missing or
  an unexpected field changed.
- [ ] 0.3 **Verify:** `uv run pytest tests/test_fine_pilot_deck.py -v`.

---

## 1. Pilot deck generation (TDD, cluster-free)

- [ ] 1.1 **Test first (byte-reproducibility):** add
  `test_pilot_decks_are_byte_reproducible_from_generate_sweep` to `tests/test_fine_pilot_deck.py`.
  Call `generate_sweep(base_inputs_path=".../base_inputs.3d.fine", output_dir=tmp_path, ...)`
  twice with the 3 pilot configs (`s55_f115_p45`, `s45_f100_p45`, `s35_f085_p45`, each
  `pitch_amp_deg=45`), `n_wingbeats=2`, `dt=5e-4`, and identical `timestamp`; assert the two
  output trees are byte-identical (deck files + `sweep_manifest.json`). Reuses
  `generate_sweep()` unmodified — this test would already pass today; it's here to pin the
  pilot's specific invocation, not to test new code.
- [ ] 1.2 **Test first (max_step values):** add `test_pilot_max_step_matches_run_duration_formula`.
  Assert `derive_run_duration(1.15, 2, 5e-4) == (3478, ...)`,
  `derive_run_duration(1.00, 2, 5e-4) == (4000, ...)`,
  `derive_run_duration(0.85, 2, 5e-4) == (4706, ...)`.
- [ ] 1.3 Write a short, one-off pilot-generation script (not a permanent library addition —
  e.g. `examples/prelim_sweep_fine_pilot/generate_pilot.py`) that calls `generate_sweep()` with
  the fine base deck, the 3 pilot configs, `n_wingbeats=2`, `dt=5e-4`, writing into
  `examples/prelim_sweep_fine_pilot/`.
- [ ] 1.4 **Verify:** `uv run pytest tests/test_fine_pilot_deck.py -v`; run the generation
  script for real and confirm the 3 decks + manifest land under
  `examples/prelim_sweep_fine_pilot/inputs/`.
- [ ] 1.5 **Test first (isolation guard):** add `test_coarse_corpus_unperturbed_by_pilot_generation`
  asserting every file under the committed `examples/prelim_sweep/` has the same `sha256` before
  and after running the pilot-generation script (guards against a path typo silently writing
  into the frozen corpus).

---

## 2. Cluster submission — live RunAI, operator/this-session work

- [ ] 2.1 Confirm `WORKSPACE_HOSTPATH` for the pilot (mirrors the existing Z:\ → NFS pattern
  used for `examples/flapping_wing/` and `examples/prelim_sweep/`); stage
  `examples/prelim_sweep_fine_pilot/` (decks, `wing.vertex`) onto that path.
  **[Open question from design.md — resolve before first submission.]**
  **[skip-with-reason if the NFS staging step cannot be completed this session.]**
- [ ] 2.2 Confirm `amrex.the_arena_init_size` is adequate for 256×128×256 on the RunAI A40s (48
  GB VRAM; T3c used 18-28 GiB on a 24 GB A5000). **[Open question from design.md.]**
- [ ] 2.3 Submit config 1 (`s55_f115_p45`, highest Reynolds) via
  `cluster/argo/scripts/submit_workflow.sh smoke` with `SMOKE_CONFIG_NAME=s55_f115_p45`,
  `SMOKE_INPUT_FILE=inputs/inputs.3d.s55_f115_p45`, `SMOKE_MAX_STEP=3478`,
  `WORKSPACE_HOSTPATH=<pilot path>`. Watch the pod log for the first ~10-15 min for immediate
  blow-up/NaN before committing to the full wait.
  - [ ] 2.3.1 If stable at `dt=5e-4`: let it run to completion; record wall time + `s_per_step`.
  - [ ] 2.3.2 If it diverges: apply the T3c fallback (`ns.fixed_dt=2.5e-4`,
    `max_step=6956`), re-submit, record that this config needed the fallback.
  - [ ] 2.3.3 If still unstable at `2.5e-4`: stop. Record as a genuine "unstable at this
    kinematic range" finding — do not retry further or route around it silently.
- [ ] 2.4 Submit config 2 (`s45_f100_p45`, mid Reynolds), same procedure as 2.3
  (`SMOKE_MAX_STEP=4000`, fallback `max_step=8000`).
- [ ] 2.5 Submit config 3 (`s35_f085_p45`, lowest Reynolds), same procedure as 2.3
  (`SMOKE_MAX_STEP=4706`, fallback `max_step=9412`).

---

## 3. Commit results + write the pilot report

- [ ] 3.1 Commit each completed config's `run_metadata_<name>.json` (git/docker/hardware/timing,
  same schema as `run_metadata_t3c.json`) and force CSV under
  `examples/prelim_sweep_fine_pilot/`.
- [ ] 3.2 **Test first (provenance pin, skipif absent):** add
  `test_pilot_run_metadata_schema` to `tests/test_fine_pilot_deck.py`, `@pytest.mark.skipif`
  per config if that config's `run_metadata_*.json` doesn't exist yet. Assert the required
  fields (`git`, `docker_image`, `image_digest`, `timing.wall_time_s`, `timing.timesteps`,
  `timing.s_per_step`, `fixed_dt`, `dt_reduced`) are present for every config that did complete.
- [ ] 3.3 Write the pilot report (`docs/aerodynamics_validation/fine-grid-training-pilot-report.md`,
  same shape as `t3c-handoff.md`): per-config stability/timing table, the real (measured) cost
  projection for the full 27-config regeneration, and an explicit go/no-go recommendation.
- [ ] 3.4 Update `docs/force_surrogate/roadmap.md` with a pointer to this pilot and its outcome.

---

## 4. Verification

- [ ] 4.1 `uv run ruff check src/` and `uv run ruff format --check src/` clean.
- [ ] 4.2 `uv run pytest tests/test_fine_pilot_deck.py -v` — Phase 0/1 tests pass; Phase 3
  tests report SKIPPED until their config's data is committed, then PASS once it lands.
- [ ] 4.3 The full suite `uv run pytest tests/` is green (no regressions).
- [ ] 4.4 `openspec validate add-fine-grid-training-pilot --strict` passes.

---

## Explicitly deferred (follow-on change, if the pilot recommends proceeding)

- Regenerating all 27 configs at fine resolution.
- Any change to `src/mosquito_cfd/force_surrogate/sweep.py`.
- Re-training the surrogate on new data.
