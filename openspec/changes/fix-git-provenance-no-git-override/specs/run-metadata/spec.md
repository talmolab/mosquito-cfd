## MODIFIED Requirements

### Requirement: git commit is always recorded as a full 40-character SHA

The metadata generator SHALL source the git commit hash for its output from, in order of
precedence: (1) an explicit `--git-commit` override supplied by the caller, used verbatim after
validation and never consulting the pod's `git` block at all; otherwise (2) the pod-side
`run_metadata.json`'s `git.commit` field, verbatim (already a full SHA when present, produced by
`get_git_info()`). It SHALL NOT truncate, re-derive, or accept a hand-typed abbreviated hash as a
silent substitute in either path: an override that is not a full 40-character SHA SHALL be
rejected with a clear validation error, exactly as an invalid/missing pod-sourced value is today.

#### Scenario: full SHA passes through unmodified when no override is supplied

- **GIVEN** a pod-side `run_metadata.json` with `git.commit` = a 40-character hex string, and no
  `--git-commit` override supplied
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output's `git.commit` is the identical 40-character string

#### Scenario: a truncated pod-sourced commit is rejected

- **GIVEN** a pod-side `run_metadata.json` whose `git.commit` is a truncated (e.g. 7-character)
  string, and no `--git-commit` override supplied
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error naming the offending value, rather than passing it
  through

#### Scenario: a pod-side git block with no commit key at all is rejected absent an override

- **GIVEN** a pod-side `run_metadata.json` whose `git` block is
  `{"error": "git not available or not a repository"}` (the exact shape produced when the pod
  image has no `.git` directory at all), and no `--git-commit` override supplied
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error, rather than raising an unrelated `KeyError` or
  silently producing output with a missing/empty `git.commit`

#### Scenario: a manual override bypasses the pod value entirely

- **GIVEN** a pod-side `run_metadata.json` whose `git` block has no valid `commit` (e.g. the
  missing-key shape above), and a caller-supplied `--git-commit` equal to a valid 40-character SHA
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output's `git.commit` is exactly the supplied override value, the output's `git`
  dict includes `"source": "cli-override"`, and the pod's own `git` block is never consulted (the
  generator does not raise even though that block has no valid commit)

#### Scenario: a malformed manual override is rejected

- **GIVEN** a caller-supplied `--git-commit` value that is not a full 40-character hex string
  (e.g. a truncated or non-hex value)
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error naming the offending override value, rather than
  passing it through or silently falling back to the pod's own value

#### Scenario: an uppercase or mixed-case override is rejected, matching existing validation

- **GIVEN** a caller-supplied `--git-commit` value that is 40 characters long but contains
  uppercase hex digits (e.g. all-uppercase)
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error, identically to how an uppercase pod-sourced
  `git.commit` is rejected today — case is not folded or normalized for either path

#### Scenario: a manual override wins even when the pod's own commit is valid

- **GIVEN** a pod-side `run_metadata.json` whose `git.commit` is already a valid, different
  40-character SHA, and a caller-supplied `--git-commit` equal to a different valid 40-character
  SHA
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output's `git.commit` is exactly the supplied override value (not the pod's), and
  the output's `git` dict includes `"source": "cli-override"` — the override always takes
  precedence, whether or not the pod's own value happened to be valid

## ADDED Requirements

### Requirement: get_git_info falls back to a build-time-baked commit when git itself is completely unavailable

`get_git_info()` SHALL, only after its existing direct git query and Windows-worktree retry (see
the WSL-worktree-resolution requirement below) have both failed, check for a `MOSQUITO_CFD_COMMIT`
environment variable. If that variable is present, is not the literal string `"unknown"`, and is a
full 40-character lowercase-hex SHA, it SHALL return
`{"commit": <value>, "source": "docker-image-build-arg"}` instead of the honest error dict — this
is the mechanism by which a pod-side container with no `.git` directory at all (baked with this
value at Docker build time) still yields git provenance. If the variable is absent, empty, exactly
`"unknown"` (the Dockerfile's default for an unparameterized local build), or present but not a
full 40-character lowercase-hex SHA (e.g. truncated, uppercase, or containing whitespace — a
misconfigured build pipeline), it SHALL fall through to the existing
`{"error": "git not available or not a repository"}` result unchanged, exactly as if no baked
value had been supplied at all — this function SHALL NOT return an unvalidated string as a
`commit` under any circumstance, matching the same format guarantee the CLI-override path applies
to a human-supplied commit. This fallback SHALL NOT be consulted, and SHALL NOT alter behavior or
output, for any case where the direct git query or the Windows-worktree retry already succeeds.

#### Scenario: baked commit is used when git is entirely unavailable

- **GIVEN** a repo directory with no `.git` at all, the initial `git rev-parse HEAD` call fails,
  and the `MOSQUITO_CFD_COMMIT` environment variable is set to a 40-character commit SHA
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"commit": <that SHA>, "source": "docker-image-build-arg"}` with no `error`
  key

#### Scenario: the "unknown" sentinel is treated as absent

- **GIVEN** the same no-`.git` setup, but `MOSQUITO_CFD_COMMIT` is set to the literal string
  `"unknown"` (the Dockerfile's default value for a `docker build` run without
  `--build-arg MOSQUITO_CFD_COMMIT=...`)
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}`, identical to today's
  behavior — it does not fabricate a commit from the sentinel value

#### Scenario: a malformed baked commit is treated as absent, not silently trusted

- **GIVEN** the same no-`.git` setup, but `MOSQUITO_CFD_COMMIT` is set to a value that is not a
  full 40-character lowercase-hex SHA — e.g. whitespace (`" "`), a truncated short SHA
  (`"abc1234"`), or an uppercase value — the kind of value a misconfigured build pipeline could
  produce
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}` — the malformed value
  is never returned as a `commit`, and this holds for every caller of `get_git_info()`
  (including ones outside the `force_surrogate/metadata_capture.py` pipeline, such as
  `force_surrogate/sweep.py`'s `_git_commit()`, which applies no format validation of its own and
  would otherwise propagate an unvalidated value straight into a committed provenance file)

#### Scenario: a successful direct git query is never overridden by the baked commit

- **GIVEN** a normal repo directory where the initial `git rev-parse HEAD` call succeeds, and
  `MOSQUITO_CFD_COMMIT` also happens to be set in the environment to some other value
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns the real git-derived info dict (the actual `git rev-parse` commit, plus
  `branch`/`dirty`/`repository`), and the `MOSQUITO_CFD_COMMIT` environment variable is never
  consulted

#### Scenario: a successful Windows-worktree retry is never overridden by the baked commit

- **GIVEN** a Windows-created worktree whose `.git` pointer file resolves successfully via the
  existing WSL-worktree retry, and `MOSQUITO_CFD_COMMIT` is also set in the environment
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns the retry's real git-derived info dict, and the `MOSQUITO_CFD_COMMIT`
  environment variable is never consulted

#### Scenario: the direct git query is always attempted before the baked commit is consulted

- **GIVEN** no `.git` at all, so the direct git query is bound to fail, and `MOSQUITO_CFD_COMMIT`
  is set to a valid 40-character commit SHA
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** the direct `git rev-parse HEAD` invocation is attempted (and observably fails) before
  the baked-commit dict is returned — the fallback tier is never consulted first, only after the
  direct attempt (and the Windows-worktree retry, when applicable) has already failed
