# Reconciliation: adversarial round 2 (harden-json-loader)

Two reviewers attacked the round-1 fixes:

- **R2-A** (Opus) built staged prototypes of tasks 1–4 in a scratch copy of `src/` and reproduced
  every red and guard claim.
- **R2-B** (Sonnet) diffed the MODIFIED blocks against the live specs and checked consistency across
  the documents.

Since round 1, the new module is renamed from `_json` to `_json_loader` (S-RENAME below), so
round 1's `_json` means `_json_loader`. Round 1's line numbers refer to its own revision. Findings
are quoted verbatim, trimmed with "…".

## BLOCKING

**B1 (R2-A B1 and R2-B B-1, found independently).** "`openspec/specs/field-surrogate/spec.md:1150-1152` … scenario 'Reading provenance does not load the force-surrogate stack'. It says: 'the import statements of both `mosquito_cfd/_provenance.py` and `mosquito_cfd/_manifest.py` … name only standard-library modules'. Task 2 makes `_manifest.py` import `mosquito_cfd._json`. That scenario is then false … Fix: add a MODIFIED delta for that field-surrogate requirement, or make the scenario allow exactly `mosquito_cfd._json`."

- **Addressed.** There is a new `specs/field-surrogate/spec.md` with a MODIFIED block for
  "Corpus snapshots carry run identity and digest-pinned provenance". It is a full copy produced by
  a script that asserts the replaced bullet occurs exactly once.
- The scenario's last bullet is split in two:
  - `_provenance.py` keeps its stdlib-only rule;
  - `_manifest.py` may import "exactly `mosquito_cfd._json_loader` (as `import
    mosquito_cfd._json_loader` or `from mosquito_cfd._json_loader import …`)", and
    `_json_loader.py` imports only the standard library.
- R2-B also mentioned `field-surrogate:617-618` and `docs/field_surrogate/roadmap.md:340`. Both
  stay true transitively, and the design says why they are left alone.
- **Where:**
  - `specs/field-surrogate/spec.md`, in the scenario "Reading provenance does not load the
    force-surrogate stack" (the two split bullets);
  - `proposal.md` Impact (the `field-surrogate` bullet);
  - `design.md` D2, "`_manifest`'s import contract".

## IMPORTANT

**I1 (R2-A I1).** "`test_gate_manifest_errors_are_the_shared_readers` is not green at c898b24 for three of the five payloads … deep: RecursionError … digits: ValueError … (no label, cause=None) … utf8: UnicodeDecodeError … So deep, digits and utf8 are **Red**; only `[]` and `5` are **Guards** … relabel by parameter in task 1.1, D6 and the commit-body instructions."

- **Addressed.**
  - The test is labelled **Mixed**: reds for deep, digits and UTF-8, with their `c898b24`
    failures; guards for `[]` and `5`.
  - D6 gains a "Red and guard cases" bullet.
  - The commit-body instructions say a Mixed test is listed under both headings, by parameter.
- **Where:**
  - `tasks.md` 1.1, the `test_gate_manifest_errors_are_the_shared_readers` entry ("Red: nesting,
    digit limit and UTF-8 …");
  - `tasks.md` header ("A **Mixed** test is listed under both headings, by parameter");
  - `design.md` D6, "Red and guard cases".

**I2 (R2-A I2).** "The M21 self-test misses a realistic helper bug … the reverse-prefix mutant `any(a.startswith(name) for a in allowed)` survives. That mutant also accepts `from mosquito_cfd import force_surrogate` … **ImportFrom:** check `node.module` only … **Import:** check each `alias.name` the same way … `from mosquito_cfd import _json` … rejected … say so in D2 … **Self-test:** add `from mosquito_cfd import force_surrogate` and `import mosquito_cfd` … **M21:** define it in both directions … Do not copy `test_corpus_imports_no_force_surrogate_or_benchmarks`' 'module + module.alias' expansion."

- **Addressed.**
  - D2 adopts the reviewer's semantics word for word: `ImportFrom` checks `node.module` only, and
    `Import` checks each `alias.name`.
  - The accept and reject lists are as given, and include the warning about the "module +
    module.alias" expansion.
  - The self-test pins all eight verdicts.
  - M21 is split into M21a (`name.startswith(a)`) and M21b (`a.startswith(name)`).
- **Where:**
  - `design.md` D2 (the `ImportFrom` and `Import` bullets, the accepted and rejected lists, and the
    recursion bullet);
  - `tasks.md` 1.1, `test_stdlib_only_allow_list_is_exact`;
  - `design.md` mutation table, M21a and M21b.

**I3 (R2-A I3).** "Spec … 'Every rejection of the file's contents SHALL be exactly a `ValueError` … raised `from` the underlying exception'. The non-object rejection has no underlying exception … Fix: limit 'raised from' to the UTF-8 and JSON cases."

- **Addressed.**
- **Where:** `specs/force-surrogate/spec.md:12-15`: "The UTF-8 and JSON rejections SHALL be raised
  `from` the underlying exception. The non-object rejection has no underlying exception."

**I4 (R2-B I-1).** "`tasks.md:265` says 'if 8.3 decides it is fully resolved'. There is no task 8.3."

- **Addressed.** It now reads "if 9.2 decides it is fully resolved".
- **Where:** `tasks.md` 8.1.

**I5 (R2-B I-2).** "The proposal's `read_units_sidecar` BREAKING bullet understates the change … 'The exception type is `ValueError` before and after' … Non-UTF-8 bytes raise a bare `UnicodeDecodeError` … They become exactly `ValueError`. Deep nesting raises `RecursionError`. It becomes `ValueError`."

- **Addressed.** The bullet is now "errors change". It lists the message changes, plus the type
  changes for nesting, non-UTF-8 and the digit limit. The CHANGELOG task takes its BREAKING items
  from this bullet.
- **Where:** `proposal.md` BREAKING items, the third bullet ("Types change: …").

**I6 (R2-B I-3).** "The MODIFIED manifest requirement does not say `require_object=False` … Add 'with `require_object=False`, keeping its own non-object check and message' to the MODIFIED text."

- **Addressed.** The reviewer's wording is used, and the paragraph is re-wrapped (R2-B S-8).
- **Where:** `specs/force-surrogate/spec.md`, MODIFIED "Sweep-manifest reading lives in a shared
  standard-library-only module", first paragraph: "with the label `sweep manifest` and
  `require_object=False`, keeping its own non-object check and message."

## SUGGESTIONS adopted

- **S-RENAME (R2-A S2, R2-B S-1).** "The module name `_json` is also the name of CPython's C
  accelerator, which is in `sys.stdlib_module_names` … Consider `_jsonio` or `_json_loader`."
  The module is renamed to `_json_loader` throughout. Where: every change document, and `design.md`
  Risks, "Module name".
- **R2-A S1 and R2-B S-5.** The mixed-by-parameter loader test is relabelled: the sidecar's `{`,
  empty and BOM cases are guards. `test_json_decode_error_message_is_unchanged` runs against
  `_json_loader` only, so it is a genuine red. Task 2.1's helper edit is a "Guard (edited)".
  `test_json_alone_loads_nothing_heavy` fails with `_run_child`'s `AssertionError`.
- **R2-A S3.** The proposal's Impact describes the run-metadata MODIFIED delta fully: a new SHALL
  and a new scenario.
- **R2-B S-2, S-3, S-4.** The D2 arithmetic is reworded (six remain; five other than `dataset`). D3
  lists which callers check existence first and which pass opening errors through. D5 says the
  drift test is written at task 2.
- **R2-B S-7.** Task 5.1 uses `grep -rnE --include=*.py "#175|Not yet wrapped"`. A `#175` hit must be
  a deliberate reference.
- **R2-B S-8.** The MODIFIED manifest paragraph is re-wrapped.

## Not adopted

- **R2-B S-6 (DRY residue).**
  - `design.md` D1's code block keeps the three message f-strings, because the code is the design.
  - Round 1's I9 claim that the templates are gone referred to the prose catalogue, not to the code.
  - The scenario payload restatement is deliberate (round 1, Subagent 1 M3).
- **R2-B S-9 (committing the reconciliation files).** They are committed with the proposal. The
  archived `share-light-corpus-helpers` change keeps its `reconciliation-round1.md` the same way.
  Their line numbers are as of their own revision, as stated at the top of each.

## Verified correct by round 2

Reproduced by R2-A on prototypes, or checked by R2-B:

- **D4.** The `ConfigExtractionError` text and chaining are byte-identical. The gate still returns
  failures for non-UTF-8, `[]` and `5` run_metadata. Deep and digit-limit run_metadata raise the
  labelled `ValueError` from both `build_dataset` and `run_acceptance_gate`.
- **M9 and `record_check_result`.** M9 is killed by `[]` and `5`, and the `require_object=False`
  variant is equivalent for all five payloads. `record_check_result` leaves the bytes unchanged for
  all five.
- **`source_config_fields`.** Every red and guard in task 3 is right at each stage. The missing
  `max_step` test reaches `_entry_field`. The committed-manifest guard gives 58 OK both before and
  after.
- **Other prototypes.** The `read_units_sidecar` messages are as claimed. On `src_proto` the
  affected test files show only the two planned failures. `_json_loader` loads only itself in a
  fresh interpreter.
- **Documents.** Both original MODIFIED blocks differ from the live text only by the intended
  edits. The scenario styles match per file. The counts (56, 57, 58), the D- and M-references and
  the pinned test names are consistent. The CHANGELOG plan matches the file. Spot-checked "Where"
  citations land on the claimed text.
