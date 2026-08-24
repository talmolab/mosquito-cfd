## Context

`get_git_info()` is called on the **driver/local host** (not inside a pod/container) whenever a
run is launched from a git checkout — including `.claude/worktrees/<name>`-style worktrees
created by Git for Windows and then read via `wsl git ...` for the actual CFD invocation (per
`openspec/project.md`'s "Local A5000 CFD testing" and "PowerShell (MSYS mangles paths)" notes).
A worktree's `.git` is a pointer file, not a directory:

```
gitdir: C:/repos/mosquito-cfd/.git/worktrees/<name>
```

A Linux `git` binary invoked from WSL cannot parse `C:/...` as absolute (no leading `/`), so it
treats the whole line as a relative path, fails to resolve it, and every subsequent git command
fails with "not a git repository" — indistinguishable from a genuinely missing repo.

Confirmed manually (issue #77):

```
$ wsl git rev-parse HEAD
fatal: not a git repository: /mnt/c/repos/.../worktrees/<name>/C:/repos/mosquito-cfd/.git/worktrees/<name>

$ GIT_DIR=/mnt/c/repos/mosquito-cfd/.git/worktrees/<name> \
  GIT_WORK_TREE=/mnt/c/repos/.../worktrees/<name> wsl git rev-parse HEAD
<resolves correctly>
```

## Goals / Non-Goals

**Goals**
- Recover git provenance (`commit`, `branch`, `dirty`, `diff_hash`, `repository`) when
  `get_git_info()` is called against a Windows-created worktree from a Linux git binary.
- Leave the non-worktree (common) path byte-for-byte unchanged in behavior and cost.
- Keep the fix fully unit-testable without WSL, Docker, or any live cluster access.

**Non-goals**
- Fixing pod-side/container git-less environments (issue #66 — different code path,
  `extract_git_info`, different root cause).
- General-purpose Windows↔WSL path translation utility (rejected as scope creep; the only
  present need is translating a `.git` pointer's gitdir path).
- Rewriting or migrating the `.git` pointer file itself (would risk breaking the Windows-side
  git client that created it).
- Retroactively patching already-committed `run_metadata*.json` files that predate this fix.

## Decisions

### Decision 1: Reactive retry-on-failure, not proactive detection

`get_git_info()` runs its existing git calls first, exactly as today. Only if that first attempt
fails does it check whether `.git` is a *file* (not a directory) and whether its content names a
Windows drive-letter path; if so, it translates the path and retries once with
`GIT_DIR`/`GIT_WORK_TREE` overridden.

**Why not proactive** (check the pointer file before the first attempt, to skip a
guaranteed-to-fail first call in the known-worktree case): the proactive version would need to
duplicate the "is this a worktree pointer" check on *every* call, including the overwhelming
majority of calls that are not worktrees and not failing — trading a small amount of latency in
the rare worktree-failure case for an extra file stat + regex check on every normal-repo call.
Reactive retry keeps the common case (non-worktree, or a worktree already resolvable in the
current environment, e.g. running the same command on native Windows against the same worktree)
exactly as fast and exactly as simple as today; the retry path only ever executes when the first
attempt has already failed. Confirmed with the user during the pre-proposal scoping questions
(retry-design question, answered "keep reactive retry-on-failure") — this was an explicit design
choice, not an oversight.

### Decision 2: Retry environment inherits the full caller environment

The retry subprocess call is invoked with `{**os.environ, **override}` — the full inherited
environment (`PATH`, `HOME`, credential-helper configuration, etc.) plus the two translated
variables (`GIT_DIR`, `GIT_WORK_TREE`).

**Why not a minimal explicit env**: git subprocess invocations conventionally rely on inherited
environment for credential helpers, `PATH`-resolved git itself, locale, and any user-level git
config that reads environment variables. A minimal explicit env risks silently breaking
authenticated operations (e.g. a private `remote get-url` resolution requiring a credential
helper found via `PATH`/`HOME`) for a fix whose only intended effect is gitdir resolution.
Confirmed with the user during the pre-proposal scoping questions (env-scope question, answered
"keep full os.environ + overrides").

### Decision 3: Detection is structural (Windows drive-letter gitdir pattern), not "are we in WSL"

The retry path is gated on the *content* of the `.git` pointer file (does it name a Windows
drive-letter path?), not on detecting "this process is running inside WSL." This makes the fix
testable without any WSL environment at all — a synthetic `.git` pointer file with Windows-style
content on any OS exercises the real code path.

This design is verified only for the WSL `/mnt/<drive>` mount convention, since that is the only
confirmed deployment shape (issue #77's repro). A Linux git binary reading the same Windows-style
pointer via a different mount convention (e.g. a CIFS share mounted at some other path) would
need a *different* translation target than `/mnt/<drive>`, which this design does not attempt —
that case is explicitly out of scope and untested (see Non-goals), not implicitly claimed to
work.

### Decision 4: Test coverage is mocked-subprocess + on-disk fixture only, no WSL-gated integration test

All new tests either mock `subprocess.run` or create a real (non-WSL) `.git` pointer file on disk
in a temp directory and assert the translation/retry-env-construction logic directly. No test
invokes a real `wsl` binary.

**Why**: CI runs on Linux runners with no WSL available, so a WSL-gated test would only ever
execute on a Windows developer's machine, adding maintenance burden (a test that's silently
skipped everywhere except one person's laptop) without contributing to CI signal. The manual
repro already recorded in issue #77 stands as the human-verified real-WSL confirmation; the
automated suite's job is to lock in the translation/retry logic so it can't regress silently.
Confirmed with the user during the pre-proposal scoping questions (test-strategy question,
answered "mocked + on-disk fixtures only").

### Decision 5: `repo_path=None` resolves to `Path.cwd()`, matching the real call sites

Both current production call sites — `capture_run_metadata()`
(`src/mosquito_cfd/benchmarks/metadata.py:185`) and `sweep.py`'s `_git_commit()`
(`src/mosquito_cfd/force_surrogate/sweep.py:326`) — call `get_git_info()` with **no argument**.
This is exactly how the bug manifests in practice (issue #77, and the provenance loss in PR #71's
`examples/prelim_sweep/surrogate/run_metadata.json`): the caller's actual working directory *is*
the worktree, not an explicitly-passed path.

`get_git_info()` SHALL resolve `repo_dir = repo_path if repo_path is not None else Path.cwd()`
before doing anything else, and pass that same `repo_dir` to both the initial git invocation
(as `cwd=`) and to `_worktree_retry_env(repo_dir)` on retry. This was missed in the first draft
of this proposal (caught by `/review-openspec`'s spec-quality pass, which noted the design and
tests as drafted only exercised the explicit-`repo_path` path) — see finding #1 in
[`review-reconciliation.md`](review-reconciliation.md). Tests for the no-argument call path use
`monkeypatch.chdir()` into a fixture worktree directory (with `subprocess.run` mocked exactly as
in the explicit-`repo_path` retry test) rather than passing `repo_path` explicitly, so the exact
production call shape is covered.

## Risks / Trade-offs

- **A worktree pointer that happens to start with a single uppercase/lowercase letter followed by
  `:`** (e.g. a relative POSIX path that coincidentally matches, which is not possible in valid
  git pointer syntax since POSIX paths don't contain `:` in this position) — the regex is anchored
  and requires `[A-Za-z]:[\\/]`, which cannot arise from a genuine POSIX absolute or relative
  path, so there is no realistic false-positive case.
- **Silent double subprocess cost on every worktree case under WSL**: accepted — this only occurs
  in the already-broken case (first attempt was always going to fail), so the retry adds cost
  only where the alternative was silently losing provenance entirely.

### Why N instead of M? Broadened exception handling, discovered during pre-PR self-review

The approved design (Decision 5 and the implementation task) specified catching
`(subprocess.CalledProcessError, FileNotFoundError)` — matching the pre-existing code exactly.
During `/review-pr`'s pre-PR self-review (three independent reviewer lenses, each empirically
reproducing the failure), two real crash bugs surfaced that this narrower exception set didn't
cover, both violating `get_git_info()`'s own documented contract ("never raise, always return a
dict"):

1. A non-UTF-8 `.git` pointer file (corrupted, or containing raw bytes) made
   `_worktree_retry_env`'s `git_pointer.read_text(encoding="utf-8")` raise `UnicodeDecodeError`
   — a `ValueError` subclass, not caught by `except OSError`, so it propagated all the way out of
   `get_git_info()`.
2. A `repo_path` pointing at a nonexistent directory (or an existing file, not a directory) made
   `subprocess.run(cwd=..., check=True)` raise `NotADirectoryError` — an `OSError` subclass, but
   not `FileNotFoundError`, so it wasn't caught by the original `except
   (subprocess.CalledProcessError, FileNotFoundError)`. `Path.cwd()` itself (used when no
   `repo_path` is given) can also raise `FileNotFoundError` if the process's cwd has been deleted
   — and that call sat outside any `try` block entirely in the first implementation.

**Fix**: `_worktree_retry_env`'s `read_text` now passes `errors="replace"` (matching the
`errors="replace"` convention already used on every `subprocess.run` call in this file) instead
of letting a decode failure raise. `get_git_info()`'s exception clauses were broadened from
`(subprocess.CalledProcessError, FileNotFoundError)` to `(subprocess.CalledProcessError,
OSError)` — a strict widening, since `FileNotFoundError` is itself an `OSError` subclass — and
the `repo_dir` resolution (`Path.cwd()` in the no-argument case) is now inside its own `try`/
`except OSError`, falling back to the same honest error dict rather than raising.

**Why this wasn't caught earlier**: five `/review-openspec` rounds reviewed the *design* of the
retry mechanism (translate → retry → fall back) exhaustively, but none of those rounds executed
the code — they read `tasks.md`'s test descriptions, which (like the original design) only
exercised valid-UTF-8, drive-letter-or-POSIX gitdir content. The pre-PR `/review-pr` pass is the
first point in this workflow where reviewers empirically reproduced failures with `uv run
python`/`monkeypatch`, and pathological byte content and nonexistent paths were exactly the
input classes design-level review doesn't naturally reach for. Three new regression tests
(`test_get_git_info_returns_error_dict_for_nonexistent_repo_path`,
`test_worktree_retry_env_handles_non_utf8_pointer_content`,
`test_get_git_info_handles_non_utf8_worktree_pointer`) lock this in, plus `cwd`-kwarg assertions
were added to the existing retry-success and no-`repo_path` tests (a gap the TDD reviewer found
independently: no test had asserted `cwd` actually reached `subprocess.run`, despite this being
the exact subject of round-1 finding #14). No GitHub issue was filed — this was caught and fixed
within the same implementation session, before any PR existed, so there was no external-facing
bug to track.

### Why N instead of M? (round 2) — an unguarded call site survived the round-1 fix

After PR #78 was opened, `/review-pr` was run a second time in PR mode (posting to GitHub). Two
independent reviewer lenses — Behavioral Correctness and TDD/Testing — each found, independently,
that the round-1 fix above was incomplete: `get_git_info()`'s `override =
_worktree_retry_env(repo_dir)` call site had **no** `try`/`except` around it at all, unlike both
`_collect_git_info` call sites. Inside `_worktree_retry_env`, `git_pointer.is_file()` was called
*before* the function's own `try`/`except OSError` (which only wrapped `read_text`).
`pathlib.Path.is_file()` swallows some `OSError`s internally (`ENOENT`, `ENOTDIR`, a few Windows
equivalents) but **not** `PermissionError`/`EACCES` — so a transient permission problem on the
`.git` stat (a locked file, an ACL issue, momentary CIFS unavailability — all realistic on this
project's Windows/WSL/CIFS-mounted deployments per `openspec/project.md`'s Cluster Path Mappings)
would still propagate an uncaught `PermissionError` out of `get_git_info()`, directly
contradicting both the function's own docstring ("any OS-level failure ... is reported the same
way as 'not a repository'") and the spec requirement ("SHALL NOT raise any exception").

The TDD reviewer separately found that two of the round-1 regression tests didn't actually pin
what they claimed to: `test_get_git_info_returns_error_dict_for_nonexistent_repo_path` used a
path that never existed, which already raised `FileNotFoundError` — caught even by the
*original*, narrower exception set — so it never exercised the `OSError`-widening it was meant to
guard. The real gap was an *existing file* passed as `repo_path` (confirmed empirically on this
Windows dev machine: `subprocess.run(cwd=<a file>)` raises `NotADirectoryError`, not
`FileNotFoundError`), which no test exercised at all.

**Fix**: moved `git_pointer.is_file()` inside `_worktree_retry_env`'s existing `try`/`except
OSError` block (a single `try` now wraps both the stat and the read). Added four tests, verified
RED against the pre-fix code before being confirmed GREEN: `test_get_git_info_returns_error_dict_when_repo_path_is_a_file_not_directory`
(genuinely exercises `NotADirectoryError`, unlike the round-1 nonexistent-path test),
`test_get_git_info_returns_error_dict_when_cwd_resolution_raises_oserror`,
`test_worktree_retry_env_returns_none_when_is_file_raises_permission_error`, and
`test_get_git_info_does_not_crash_when_worktree_check_raises_permission_error`.

**Why this survived one full pre-PR review round**: the round-1 fix correctly widened the two
call sites that were already inside a `try` block, but didn't audit for call sites *outside* any
`try` block entirely — `_worktree_retry_env`'s own internal `is_file()`/`read_text()` split had a
gap between "before the try" and "inside the try" that no round-1 reviewer traced line-by-line.
This is exactly why a second review pass in PR mode (not just re-trusting the round-1 fix) was
worth running. No GitHub issue was filed — caught and fixed before merge, no external-facing bug
to track.

## Migration Plan

None required — this is a pure bugfix to a currently-broken code path with no schema change to
existing valid outputs (a case that previously produced `{"error": ...}` now produces the full
git-info dict; no other case's output changes). No data migration, no config flag.

## Open Questions

None outstanding. The four pre-proposal scoping questions (retry design, env scope, test
strategy, and scope boundary re: issue #66 and retroactive patching) were confirmed with the
user before this proposal was written. Five rounds of `/review-openspec` subsequently surfaced
twenty-one findings across all five passes (three BLOCKING, thirteen IMPORTANT, five SUGGESTION)
— see [`review-reconciliation.md`](review-reconciliation.md) for the full finding → fix → location
mapping, including two separate instances of a review round under-reporting its own prior
round's fix count (rounds 2 and 3 each did this once; both were caught by the next round) and one
instance of stale prose in the reconciliation file itself (round 5). All five reviewer lenses
converged on "ready for implementation, no further review round needed" as of round 5.
