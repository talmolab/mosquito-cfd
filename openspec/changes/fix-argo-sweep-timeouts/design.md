# Design: fix-argo-sweep-timeouts

Condensed decision log, mirroring `add-fine-grid-corpus-full`'s own `design.md` format (the
change that introduced the `--parallelism` mechanism this proposal extends).

## D1 — `--active-deadline-seconds`: mirror `--parallelism` exactly, then layer auto-scale on top

Same shape as the existing `--parallelism` flag (`add-fine-grid-corpus-full`'s D4): no default
value (empty sentinel = not given), positive-integer validation
(`^[1-9][0-9]*$`) before touching any file, anchored grep-count-exactly-one-match on
`^  activeDeadlineSeconds: [0-9]\+$` (confirmed 2-space top-level indent, same `spec:` scope as
`parallelism`, single occurrence in the file), `sed`-patch onto a temp copy, self-verify the
patch landed, `die` otherwise. The committed `force-surrogate-sweep.yaml` is never mutated.

**Combining with `--parallelism` onto one temp copy, not two.** The existing code creates a temp
copy only if `--parallelism` is given. This proposal generalizes that gate: a temp copy is
created if *either* flag (explicit or auto-scaled) needs patching, and every needed patch lands
on that **same** temp copy, each independently anchored and self-verified before the next patch
is attempted:

```bash
ACTIVE_DEADLINE_SECONDS=""   # empty = not given; same idiom as PARALLELISM
--active-deadline-seconds) ACTIVE_DEADLINE_SECONDS="$2"; shift 2;;
...
full)
  require_image
  [[ -n "$NO_PROVISION" ]] || provision "$CORPUS_DIR" "$WORKSPACE_HOSTPATH" true   # UNCHANGED — do not drop this call
  workflow_file="$SWEEP_WORKFLOW_FILE"

  # Validate PARALLELISM's format BEFORE it is used for anything, including auto-scale below.
  # This must run here, not only inside the later patch block — compute_auto_deadline_seconds
  # divides by $PARALLELISM and int()-parses it in Python; an unvalidated "0" or "abc" reaching
  # that call raises an uncaught ZeroDivisionError/ValueError (a raw traceback), not a die()
  # message, defeating the "fails loudly and clearly" guarantee this whole mechanism exists to
  # provide (caught in review: the pre-existing invalid-parallelism regression test only checks
  # the exit code, not stderr content, so it would keep "passing" while silently regressing from
  # a clean die() to a traceback).
  if [[ -n "$PARALLELISM" ]]; then
    [[ "$PARALLELISM" =~ ^[1-9][0-9]*$ ]] || die "--parallelism must be a positive integer (got: $PARALLELISM)"
  fi

  effective_deadline="$ACTIVE_DEADLINE_SECONDS"
  if [[ -z "$effective_deadline" && -n "$PARALLELISM" ]]; then
    effective_deadline="$(compute_auto_deadline_seconds "$CORPUS_DIR/sweep_manifest.json" "$PARALLELISM")"
  fi

  if [[ -n "$PARALLELISM" || -n "$effective_deadline" ]]; then
    tmp="$(mktemp --suffix=.yaml)"
    trap 'rm -f "$tmp"' EXIT
    cp "$SWEEP_WORKFLOW_FILE" "$tmp"
    if [[ -n "$PARALLELISM" ]]; then
      # $PARALLELISM already validated above; only the anchored-patch-and-verify remains here.
      n=$(grep -c '^  parallelism: [0-9]\+$' "$tmp" || true)
      [[ "$n" -eq 1 ]] || die "expected exactly one top-level 'parallelism:' line, found $n"
      sed -i -E "s/^(  parallelism: )[0-9]+\$/\1${PARALLELISM}/" "$tmp"
      grep -q "^  parallelism: ${PARALLELISM}\$" "$tmp" || die "parallelism patch did not apply as expected"
    fi
    if [[ -n "$effective_deadline" ]]; then
      # Validated here (not hoisted above): an explicit --active-deadline-seconds is validated
      # exactly like an explicit --parallelism, but an AUTO-SCALED value is already
      # well-formed by construction (compute_auto_deadline_seconds only ever prints a positive
      # integer or fails the script outright) — this check is a defense-in-depth belt on the
      # explicit-flag path, not a gate the auto-scale path depends on.
      [[ "$effective_deadline" =~ ^[1-9][0-9]*$ ]] || die "--active-deadline-seconds must be a positive integer (got: $effective_deadline)"
      n=$(grep -c '^  activeDeadlineSeconds: [0-9]\+$' "$tmp" || true)
      [[ "$n" -eq 1 ]] || die "expected exactly one top-level 'activeDeadlineSeconds:' line, found $n"
      sed -i -E "s/^(  activeDeadlineSeconds: )[0-9]+\$/\1${effective_deadline}/" "$tmp"
      grep -q "^  activeDeadlineSeconds: ${effective_deadline}\$" "$tmp" || die "activeDeadlineSeconds patch did not apply as expected"
    fi
    workflow_file="$tmp"
  fi
```

**This snippet is an insertion into the existing `full)` case, not a replacement of it** — the
`require_image` and `provision` lines are the script's real, unchanged preconditions, included
here explicitly (review caught an earlier draft that elided them for brevity, which risks an
implementer copying the snippet verbatim and silently dropping provisioning, breaking
`tests/test_submit_workflow_provision.py`). Everything below `argo submit "$workflow_file" ...`
(the `--parameter` list, `-n "$NAMESPACE"`, `--watch`) is also unchanged and omitted here only for
length.

Why `cp` + `sed -i` rather than the original's `sed ... > tmp` redirect: with two independent
patches that may each apply, redirecting `original > tmp` then `tmp > tmp2` then `mv tmp2 tmp`
for the second patch is needless indirection once the file is already a private scratch copy we
own. `sed -i` in place on `$tmp` (never on `$SWEEP_WORKFLOW_FILE`) is simpler and equally safe.
GNU `sed` is already assumed in this environment (the script's `provision()` already assumes GNU
`sha256sum`'s escaping convention).

The explicit `--active-deadline-seconds` value and an auto-scaled value take the **same** code
path (`effective_deadline` is just resolved from one of two sources before the shared
validate→patch→verify block runs) — auto-scaling is not a second, divergent mechanism.

## D2 — Auto-scale fallback: when it fires, and the exact formula

**Trigger**: fires only when `--parallelism` is explicitly given (any value, including one that
happens to match the committed default) **and** `--active-deadline-seconds` is *not* given.
Rationale: the danger this closes is specifically "operator overrides concurrency, forgets the
coupled deadline no longer fits" (issue #63's literal root cause) — if parallelism is left alone,
the committed 86400 was already correctly sized for it; if the operator gave an explicit
deadline, they've made a deliberate choice that should not be second-guessed.

**Formula** (implemented as a single `python3` invocation — stdlib-only (`json`, `math`, `sys`),
no repo virtualenv dependency, safe to call from a bare WSL/cluster-ops shell that doesn't have
`uv sync`'d):

```python
import json, math, sys
manifest_path, parallelism = sys.argv[1], int(sys.argv[2])
PER_CONFIG_HOURS = 2.4   # measured mean wall_time_s across all 27 configs of force-surrogate-sweep-vb8t5
RETRY_MARGIN_HOURS = 4   # matches the retryStrategy.backoff.maxDuration bump (issue #64) — one
                         # retried config's full backoff sequence must fit inside this margin
n = len(json.load(open(manifest_path))["configs"])
hours = math.ceil(n * PER_CONFIG_HOURS / parallelism + RETRY_MARGIN_HOURS)
print(hours * 3600)
```

Wrapped in a named shell function:

```bash
compute_auto_deadline_seconds() {
  local manifest_path="$1" parallelism="$2"
  local python_bin=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
      python_bin="$candidate"
      break
    fi
  done
  [[ -n "$python_bin" ]] \
    || die "python3 (or python) is required to auto-scale --active-deadline-seconds; none found working on PATH"
  [[ -f "$manifest_path" ]] || die "auto-scaling the deadline needs $manifest_path, but it does not exist"
  "$python_bin" -c '
import json, math, sys
manifest_path, parallelism = sys.argv[1], int(sys.argv[2])
PER_CONFIG_HOURS = 2.4
RETRY_MARGIN_HOURS = 4
n = len(json.load(open(manifest_path))["configs"])
hours = math.ceil(n * PER_CONFIG_HOURS / parallelism + RETRY_MARGIN_HOURS)
print(hours * 3600)
' "$manifest_path" "$parallelism" || die "failed to compute auto-scaled --active-deadline-seconds from $manifest_path"
}
```

### Why an actually-invoked probe instead of a bare `command -v python3` check?

The proposal originally specified a plain `command -v python3` precondition, with round-2/3
review already flagging (as non-blocking) that this could return a false positive on some
platforms. During implementation this was upgraded from a theoretical caveat to a confirmed,
reproducible failure: on this repo's own Windows dev/test environment, `command -v python3`
succeeds (a non-functional Windows App-Execution-Alias stub resolves on `PATH`), but actually
running `python3 -c ...` fails with a non-Python "install from the Microsoft Store" message —
and this broke real test runs, including two **pre-existing** `--parallelism`-only tests that
now transitively exercise auto-scale (the documented coupling from D4). The fix implemented:
probe each candidate (`python3`, then `python`) by *actually invoking* a no-op (`"$candidate" -c
""`), not just checking `command -v`, and use the first one that genuinely works. This has no
effect on the real production target (WSL/Linux, where `python3` is the standard and always
wins the probe on the first attempt) and fixes the exact class of false-positive this script's
own Windows dev/test environment exhibits — discovered empirically, not hypothetically, during
implementation.
```

so call sites read as intent, not an inline heredoc. (Caveat found in round-2 review: on some
platforms — e.g. Windows without a real Python install — `command -v python3` can return success
for a non-functional App-Execution-Alias stub, giving a false-positive precondition. This does
not break the design's actual guarantee: the subsequent `python3 -c ... || die` still catches the
resulting failure with a clear message, never a raw traceback, since the stub's own failure is
non-Python and gets caught by the same `|| die` wrapper. The precondition check is a fast, clear
first-line diagnostic for the common case, not the sole safety net.) The explicit `command -v
python3` and
manifest-existence checks close two review findings: (1) this script has zero prior Python
dependencies (pure bash/sed/grep/mktemp/sha256sum/argo/kubectl) and its header assumes only a
WSL shell with `KUBECONFIG` exported — a bare `python3` binary is a new, previously-unstated
precondition worth failing loudly on rather than assuming; (2) without the manifest-existence
check, a missing `sweep_manifest.json` would surface as an opaque `FileNotFoundError` traceback
from Python's own `open()`, not a `die()` message. The final `|| die ...` also catches malformed
JSON or an unexpected manifest schema (e.g. a missing `"configs"` key) with one clear message
rather than a bare Python traceback bleeding into the operator's terminal — precise diagnosis of
*which* malformation occurred is sacrificed for a uniformly clear failure mode, which is an
acceptable trade at this script's size.

**Why derive config count from the manifest instead of hardcoding 27**: the manifest is already
read once per submission by the workflow itself (`load_manifest_configs`); hardcoding 27 here
would silently go stale the day the corpus's config count changes for any reason (e.g. a future
finer/coarser grid). Reading `"$CORPUS_DIR/sweep_manifest.json"` — the git-committed local copy,
not the NFS-provisioned remote copy — needs no path translation and is guaranteed present by the
time this code runs in the `full` case regardless of `--no-provision` (it's a local file the
repo already ships, not something `provision()` creates).

**Why 2.4h and not the pilot's projected ~2.3h or the worst-case 5.16h outlier**: 2.4h is the
directly measured mean of the actual 27-config `vb8t5` run's `wall_time_s` values (not the
pre-run pilot projection), giving `27 configs × 2.4h ÷ 1 worker + 4h margin = 68.8h → 69h` at
`parallelism=1` — comfortably above the real 64.8h serial sum. Using the 5.16h single-config
outlier for every config would over-budget by roughly 2×; the mean plus a dedicated 4h retry
margin already covers one config needing a full backoff-and-retry cycle without inflating every
other config's contribution to match the worst single outlier.

**Worked check at the default `parallelism=3`** (if an operator explicitly re-passes `--parallelism
3`, matching the current default, with no explicit deadline): `27 × 2.4 ÷ 3 + 4 = 25.6 → 26h =
93600s` — slightly more generous than the committed 86400s default, because the committed default
carries no retry margin at all, which is the exact gap issue #63's discussion flagged.

**Deviation from issue #63's own suggested metric — acknowledged, not silent.** Issue #63's "Ask"
section suggests "computing a safe deadline from the manifest's total step count" as a longer-term
option, i.e. a per-*step* cost model. This proposal instead uses a per-*config* measured-hours
mean. Reasoning: `run_metadata_*.json` already records each config's real `wall_time_s` directly
(what actually elapsed, including any IB-solver/AMR cost variation across configs), whereas a
step-count-based estimate would need a second, separately-measured seconds-per-step constant and
each config's `max_step` — more moving parts for a proposal-sized fix, and per-step cost is not
obviously more accurate than the directly-measured per-config mean already computed from real
28,481–4,706-step corpus runs (`max_step` varies by config; a flat seconds/step constant would
itself be an approximation, not a more precise ground truth). The simpler per-config metric is
adopted for this change; a future step-count-based refinement remains open if the mean-hours
estimate proves too coarse in practice.

## D3 — `retryStrategy.backoff.maxDuration`: static bump, no new flag

Issue #64 asks only that the **committed** template value be fixed — unlike issue #63, there is
no request for a per-submission override, and no evidence any submission would ever want a
different `maxDuration` than "enough for the full `limit: 5` sequence plus real-world headroom."
`4h` is not a fresh guess: it is the exact value the one-off `force-surrogate-retry-failed-trz9k`
workflow already used to successfully recover these exact 3 configs on the real cluster. `limit:
5`, `duration: "2m"`, and `factor: 2` are unchanged; `2m→4m→8m→16m→32m = 62m` fits inside 4h with
~3h of margin for however many preemption/retry cycles actually occur under sustained
over-quota pressure.

## D4 — Test design (mirrors `test_submit_workflow_parallelism.py`'s stub-`argo` shell-test shape)

New file `tests/test_submit_workflow_active_deadline.py`, same stub-`argo`-on-`PATH` /
`SWEEP_WORKFLOW_FILE`-env-seam pattern as the existing parallelism tests — **and, explicitly
resolving an ambiguity round 3 review flagged, the same unconditional `--no-provision` baked into
the shared invocation helper's base argument list**, exactly matching
`tests/test_submit_workflow_parallelism.py`'s own `_run_submit_workflow` (which already always
passes `"--no-provision"` ahead of each test's own `*args`, with the comment "this test file is
entirely about `--parallelism`; provisioning ... must not touch real NFS defaults here"). Every
test below inherits this baked-in flag from the shared helper — no individual test needs to
remember to add it itself, closing the exact bug class task 3.0 was found to have individually in
round 2 (a test that omitted it hit `provision()`'s real `mkdir -p` against the default NFS path
instead of exercising the code under test):

**New coupling in the pre-existing `tests/test_submit_workflow_parallelism.py` (noted, not a
defect to fix).** Its `--parallelism`-only tests (e.g.
`test_parallelism_override_patches_only_the_temp_copy`,
`test_invalid_parallelism_rejected_before_touching_anything`) invoke `full --parallelism <N>`
with no `--active-deadline-seconds` and the *default* `--corpus-dir`
(`examples/prelim_sweep`, whose real manifest exists) — under this proposal's trigger rule, they
now also implicitly exercise the new auto-scale codepath (requiring `python3` on `PATH` and a
readable real manifest to keep passing), even though they assert nothing about the resulting
`activeDeadlineSeconds` and were written purely to test `--parallelism` in isolation. This is an
acceptable, intentional coupling — not a gap needing a code fix — but it does mean a broken
auto-scale formula could theoretically corrupt the patched temp file's `activeDeadlineSeconds`
line while these three tests stay green (they only check the `parallelism:` line and the
`sha256`, not the deadline). The new test suite below (in particular
`test_parallelism_without_explicit_deadline_autoscales`, task 3.1) is what actually pins the
auto-scaled value; the pre-existing parallelism tests are not expected to be extended for this.

- `--active-deadline-seconds N` alone (no `--parallelism`) → captured temp file has
  `activeDeadlineSeconds: N`, `parallelism:` line unchanged from the committed file's value, and
  the committed file's own `sha256` is unchanged before/after.
- Both flags given → captured temp file has **both** overrides applied, both correctly, on one
  temp file (not two divergent ones) — the test that actually distinguishes "combined patch onto
  one copy" from "two independent unrelated copies" is asserting the single captured file has
  both new values simultaneously.
- `--parallelism N` given, `--active-deadline-seconds` omitted → captured file's
  `activeDeadlineSeconds` equals the value the D2 formula predicts for a **known small fixture
  manifest** using the real production schema `{"configs": [ {...}, {...}, {...} ]}` (e.g. a
  `tmp_path` corpus dir with a 3-config `sweep_manifest.json` — a bare `{"n_configs": 3}` would
  NOT exercise the real `json.load(...)["configs"]` read path and must not be used — so the
  expected value is hand-computable and small: at `parallelism=1`,
  `ceil(3*2.4/1+4)*3600 = ceil(11.2)*3600 = 43200`), invoked with `--no-provision` (the fixture
  corpus dir need not have `inputs/` staged — only the manifest matters for this test) at a
  couple of different `--parallelism` values.
- Explicit `--active-deadline-seconds` + `--parallelism` together, with a corpus dir whose
  manifest is missing/unreadable, **and `--no-provision`** — the explicit value wins; auto-scale
  is never invoked (confirmed by the command succeeding despite the unreadable manifest, which
  would otherwise make auto-scale fail). `--no-provision` is required here: `provision()` itself
  demands `sweep_manifest.json` exist for `full` (`require_manifest=true`) and would `die` on the
  intentionally-broken fixture before the code path under test is ever reached — omitting it
  would test `provision()`'s pre-existing guard, not this proposal's precedence rule.
- Missing `sweep_manifest.json` at the resolved `--corpus-dir` when auto-scale would need to
  fire, **with `--no-provision`** (same reason as above — otherwise `provision()`'s own
  precondition check fires first and the test exercises the wrong code path) → fails fast with a
  clear message (not a raw Python traceback) before any `argo submit` call.
- Neither flag given → true no-op: captured file (there should be none — no temp file created at
  all) — mirrors the existing `test_omitting_parallelism_is_a_true_noop` assertion shape.
- Invalid `--active-deadline-seconds` (`0`, `-1`, `abc`) → fails fast, stub never invoked, no temp
  file, committed file untouched — same shape as the existing invalid-`--parallelism` tests.
- **Invalid `--parallelism` (`0`, `-1`, `abc`) with auto-scale eligible to fire** (no explicit
  `--active-deadline-seconds`, default `--corpus-dir` whose real manifest exists) → fails fast
  with a clear "positive integer" `die` message and, critically, **`"Traceback" not in
  result.stderr`** — this is the regression test for the validation-ordering bug two independent
  reviewers found in an earlier draft of this design (the D1 snippet originally resolved
  `effective_deadline`/called `compute_auto_deadline_seconds` before validating `$PARALLELISM`'s
  format, so `--parallelism 0` triggered an uncaught `ZeroDivisionError` and `--parallelism abc`
  an uncaught `ValueError` — both silently masked by the pre-existing test that only checks the
  exit code, not stderr content). D1's corrected snippet validates `$PARALLELISM` immediately on
  parse, before it is ever passed to `compute_auto_deadline_seconds`.
- Missing/reformatted `activeDeadlineSeconds:` line in the (test-injected, via
  `SWEEP_WORKFLOW_FILE`) workflow copy → fails loudly with a clear "expected exactly one..."
  message, mirroring the existing parallelism "failed substitution is never silently submitted"
  test.
- **Boundary: a 0-config manifest** → the formula degenerates to `ceil(0*2.4/parallelism+4)*3600
  = 14400` (just the retry margin) — assert this exact value, confirming the formula doesn't
  divide-by-zero or otherwise misbehave when `n=0` (this is a distinct case from an *invalid*
  `--parallelism`; a 0-config manifest is a valid, if degenerate, corpus).
- **Boundary: a very large `--parallelism`** (e.g. `1000000`) against the same 3-config fixture →
  assert success and `activeDeadlineSeconds == 18000` (`ceil(3*2.4/1000000 + 4)*3600 =
  ceil(4.0000072)*3600 = 5*3600` — `math.ceil` rounds up past *any* nonzero fractional remainder,
  however tiny, so this is 5h, not the 4h the config-count term's near-zero contribution might
  suggest at a glance; round-3 review caught an earlier draft asserting `14400`/4h here, which is
  simply wrong arithmetic, unlike the 0-config case below where the config-count term is exactly
  `0.0` and `ceil(4.0) == 4` genuinely holds) — confirms no integer/float overflow and a sane
  floor rather than a nonsensical tiny or negative result.
- **Help text documents the flag and the coupling risk**: invoking `submit_workflow.sh help`
  shows `--active-deadline-seconds` and a distinctive mention of the parallelism/deadline
  coupling risk in its output (task 2.6; traces to the delta spec's matching scenario under the
  first requirement).

`tests/test_argo_workflows.py::test_single_config_template_retry_strategy` gains a new assertion
for `maxDuration: "4h"` (or unquoted `4h` — check the committed file's actual quoting convention
for `duration`/`factor` and match it). No existing assertion in that test currently pins the old
`30m` value, so this is a pure addition, not a breaking change to an existing assertion.

`tests/test_argo_workflows.py::test_workflow_has_image_and_parallelism_and_deadline`'s existing
`"activeDeadlineSeconds: 86400" in text` assertion is verified to still pass unmodified — this
proposal never changes the *committed* default, only adds an override path.

## Open questions — resolved

- **Should the auto-scale formula live in a separate importable Python module instead of an
  inline `python3 -c`/heredoc?** Decided: inline, stdlib-only, wrapped in a named shell function.
  `cluster/argo/scripts/` has no existing Python helpers and no established pattern for the bash
  script shelling into the repo's own `src/mosquito_cfd` package (which would additionally
  require a synced `uv` environment to be active in whatever shell runs `submit_workflow.sh` —
  not guaranteed on a bare WSL cluster-ops shell). A future change could promote this to a real
  module with its own unit tests if the formula grows more complex; not warranted at this size
  (one `ceil` expression).
- **Should the pre-submit sanity-check from the issue #63 comment be built as part of this auto-
  scale work, since the two are related?** No — per the user's explicit decision (comment
  author's repo association could not be verified), deferred to a follow-up issue, not built
  here. The auto-scale fallback already closes the specific silent-mismatch failure mode issue
  #63 itself describes; the sanity-check idea is a distinct, broader pre-flight-estimate feature.
- **Should there be an automated test for "`python3` genuinely absent from `PATH`"?**
  **Superseded during implementation** — see "### Why: post-self-review fixes" below. A
  dedicated test was added after all, using self-contained fake-interpreter shell stubs rather
  than trying to hide the real `python3`/`python` cross-platform (which is what this note
  originally, correctly, flagged as too fragile).
- **Does task 2.6's help-text test need its own spec scenario?** Yes — added (see the delta
  spec's Requirement 1, new scenario "Help text documents the flag and the coupling risk").
  The precedent that the base `--parallelism` requirement also lacks such a scenario is a
  pre-existing gap in that requirement, not a reason to repeat it here now that a reviewer has
  flagged it.

### Why: post-self-review fixes (found by `/review-pr`'s 5-agent team, after implementation)

Three real, adversarially-verified gaps surfaced during the pre-PR self-review pass (Phase 3.5
of `/pre-merge-check`), none caught by the 4 rounds of proposal-time review (implementation
didn't exist yet to review). All three are fixed in the shipped diff, not just noted:

1. **BLOCKING, live-reproduced**: `compute_auto_deadline_seconds`'s inline `python3 -c '...'`
   only guarded the manifest-file-missing case. A manifest that *exists* but is malformed JSON,
   or is valid JSON with `"configs"` missing or not a list, reached the one-liner unguarded and
   raised an uncaught `KeyError`/`JSONDecodeError`/`TypeError` — a raw traceback, directly
   contradicting this function's own stated purpose (every other failure mode is a clean
   `die()`). Fixed: the one-liner's body is now wrapped in `try/except Exception`, with an
   explicit `isinstance(configs, list)` check (closing a sibling gap: a dict `"configs"` value
   would otherwise make `len()` silently return a *wrong but plausible* key count instead of
   erroring). New regression test:
   `test_autoscale_malformed_manifest_configs_fails_with_clear_message_not_a_traceback`.
2. **IMPORTANT, traced**: `provision()`'s corpus/workspace basename-match guard is skipped
   entirely under `--no-provision` (which every auto-scale-triggering test in this file already
   sets). Since `compute_auto_deadline_seconds` reads `$CORPUS_DIR/sweep_manifest.json`
   independently of `$WORKSPACE_HOSTPATH`, an operator who overrides `--workspace-hostpath`
   (pointing at a real, different corpus) without also updating `--corpus-dir` — while passing
   `--no-provision` — would get a deadline silently auto-scaled from the *wrong* corpus's config
   count. Fixed: a basename-consistency check now runs unconditionally, but **only** inside the
   auto-scale trigger branch (`-z "$effective_deadline" && -n "$PARALLELISM"`) — not on every
   `full` invocation, since an explicit `--active-deadline-seconds` never needs `$CORPUS_DIR` to
   match anything. This required updating `tests/test_submit_workflow_active_deadline.py`'s
   auto-scale-triggering tests (3.1, 3.1a, 3.1b) to pass a `--workspace-hostpath` with a
   matching basename (harmless under `--no-provision`, which never actually touches the path —
   only its basename is compared). New regression tests:
   `test_autoscale_dies_on_corpus_workspace_basename_mismatch` and
   `test_explicit_deadline_skips_the_basename_check_entirely`.
3. **IMPORTANT**: the `python3`→`python` interpreter-fallback loop itself (added earlier in this
   same design to fix a *different*, already-shipped bug — the Windows App-Execution-Alias
   false-positive) had zero test coverage of its own fallback/failure branches; `ubuntu-latest`
   CI never exercises them since `python3` always resolves and works there first. Fixed: two new
   tests — `test_autoscale_falls_back_to_working_interpreter` (parametrized over which of
   `python3`/`python` is the "broken" one) and `test_autoscale_dies_clearly_when_no_interpreter_
   works` — using self-contained fake-interpreter shell stubs that satisfy the two call shapes
   `compute_auto_deadline_seconds` actually uses (the `-c ""` presence probe, and the real `-c
   '<code>' manifest parallelism` computation, faked to print the fixed expected value for this
   test's known inputs) rather than trying to exec a real Python interpreter from a stub (a first
   attempt at this hit exactly the Windows-path/`exec`-portability problem this whole function
   exists to work around — self-contained fakes avoid it entirely).
