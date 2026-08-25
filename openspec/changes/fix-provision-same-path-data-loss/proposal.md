## Why

`cluster/argo/scripts/submit_workflow.sh`'s `provision()` function stages a local corpus onto a
workspace path by doing `rm -rf "$local_workspace/inputs"` immediately followed by `cp -r
"$corpus_dir/inputs" "$local_workspace/"`. If `--corpus-dir` and `--workspace-hostpath` (after
`to_local_path` translation) resolve to the **same real filesystem location** — the same literal
path, or two different-looking paths that are actually the same directory (a relative vs.
absolute spelling, a trailing slash, a symlink) — the `rm -rf` deletes the corpus's own `inputs/`
before the `cp -r` can read from it. This was found and live-reproduced during PR #82's
(`fix-argo-sweep-timeouts`) second review round while auditing `provision()` for an unrelated
reason; `provision()` itself is untouched by that PR:

```
$ cluster/argo/scripts/submit_workflow.sh full --corpus-dir X --workspace-hostpath X ...
cp: cannot stat '.../inputs': No such file or directory
```

The failure is not a clean `die()` — it's a raw `cp` error after the corpus's `inputs/` directory
has already been permanently deleted from disk. Recoverable only if the corpus happens to be an
unmodified git checkout; if it isn't (e.g. deck regeneration produced local-only changes not yet
committed), this is real, silent-until-too-late data loss. The existing basename-match guard
(`corpus-dir`/`workspace-hostpath name different corpora`) does not catch this: identical paths
trivially have identical basenames, so that guard passes right through.

This is unrelated to issues #63/#64 and does not touch anything `fix-argo-sweep-timeouts`
modified — `provision()`'s body is untouched by that PR, confirmed via diff. Fixed as its own
change per the user's explicit choice.

## What Changes

- `provision()` gains a new precondition, checked **before** any mutation (alongside its
  existing preconditions, matching the function's own stated "fail fast, mutate nothing"
  discipline): resolve both `$corpus_dir` and the translated `$local_workspace` via `realpath -m`
  (GNU coreutils; canonicalizes symlinks and `.`/`..`/trailing-slash without requiring the target
  to already exist — needed since `local_workspace` may not exist yet, that's what `mkdir -p`
  right after this check is for) and `die` with a clear message if they resolve to the same real
  path, before the destructive `rm -rf`.
- `realpath` is GNU coreutils, already implicitly relied on elsewhere in this script (`sed -i`,
  `mktemp --suffix=`, `grep -c`) and confirmed present in every environment this script actually
  runs in: this repo's own Windows dev/test setup (via Git Bash's MSYS2 coreutils), `ubuntu-latest`
  CI, and the real WSL/Linux production target.

## Non-goals (explicit)

- Does not touch anything else in `provision()` — the existing basename-match guard, the
  replace-not-merge `inputs/`/manifest handling, and the `wing.vertex` hash verification are all
  unchanged.
- Does not change `full)`/`smoke)`'s call sites, `--no-provision`, or anything in the
  `fix-argo-sweep-timeouts` PR (#82) — that PR's own diff never touches `provision()`'s body,
  confirmed, and stays that way.
- Does not attempt to recover already-lost data from a past run that hit this bug — no evidence
  any real cluster submission has actually hit this combination (the coarse and fine corpora have
  always used distinct `--corpus-dir`/`--workspace-hostpath` pairs in every documented
  submission); this is a preventive fix for a reachable-but-so-far-unobserved operator mistake.

## Impact

- Affected specs: `force-surrogate` (`MODIFIED Requirements` delta on "Argo sweep-submission
  provisions the NFS workspace before submitting").
- Affected code: `cluster/argo/scripts/submit_workflow.sh` (`provision()` only) +
  `tests/test_submit_workflow_provision.py` (new regression test).
- Cluster cost: none — cluster-free, same stub-`argo` testing pattern as the rest of this
  subsystem.
