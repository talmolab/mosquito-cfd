# Run CI Checks Locally

Run CI-equivalent checks locally before pushing your code.

## What This Command Does

This command runs CI-equivalent checks matching `.github/workflows/ci.yml`:

### Step 1: Ruff Linting

```bash
uv run ruff check src/
```

### Step 2: Ruff Formatting Check

```bash
uv run ruff format --check src/
```

### Step 3: Run Tests

```bash
uv run pytest -v
```

> Note: CI tolerates "no tests collected" (pytest exit code 5) while the test suite
> is being built out. Locally, treat exit code 5 as a soft pass until tests exist.

### Step 4: Coverage Report

```bash
uv run pytest --cov=src/mosquito_cfd --cov-report=xml --cov-report=term-missing --durations=-1 tests/
```

### Step 5: Dockerfile Lint (optional, requires hadolint or Docker)

CI lints the Dockerfiles with hadolint (`failure-threshold: error`). To reproduce locally:

```bash
docker run --rm -i hadolint/hadolint < docker/Dockerfile.fp64
docker run --rm -i hadolint/hadolint < docker/Dockerfile.fp32
docker run --rm -i hadolint/hadolint < docker/Dockerfile.python
```

Run each step sequentially. If any step fails, stop and report the failure with instructions to fix.

## Expected Output

### Success (All Checks Pass)

```
[1/4] Ruff linting...
All checks passed!
PASSED

[2/4] Ruff formatting check...
N files already formatted
PASSED

[3/4] Running tests...
================================ test session starts =================================
...
================================ XX passed in XX.XXs =================================
PASSED

[4/4] Running coverage...
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
...
PASSED

ALL CI CHECKS PASSED
```

### Failure (Checks Failed)

```
[2/4] Ruff formatting check...
Would reformat: src/mosquito_cfd/geometry/planform.py
FAILED

Fix: Run 'uv run ruff format src/' to auto-fix formatting
```

## Quick Fixes

When checks fail:

- **Ruff lint fails**: `uv run ruff check --fix src/` (then fix remaining manually)
- **Ruff format fails**: `uv run ruff format src/`
- **Tests fail**: Read the test output and fix the failing tests
- **Coverage low**: Write tests for uncovered lines (use `/coverage` for details)
- **Dockerfile lint fails**: Fix the flagged hadolint rule in `docker/Dockerfile.*`

## CI Configuration Reference

These commands mirror `.github/workflows/ci.yml`:

- **Lint job step 1**: `uv run ruff check src/`
- **Lint job step 2**: `uv run ruff format --check src/`
- **Test job**: `uv run pytest -v`
- **Dockerfile-lint job**: hadolint on `docker/Dockerfile.fp64`, `Dockerfile.fp32`, `Dockerfile.python`

CI runs on: ubuntu-latest with Python 3.11 (uv-managed). This is a service repo with
Docker-based CI.

## When to Use

- Before every `git push`
- Before creating a PR
- After making significant changes
- When you want confidence your PR will pass CI

## Integration

| Command | What it does | When to use |
|---------|-------------|-------------|
| `/lint` | Ruff lint + format check | Quick formatting check |
| `/coverage` | Pytest + coverage report | Checking test coverage |
| **`/run-ci-locally`** | **All of the above** | **Before pushing/PR** |

## Troubleshooting

### "Module not found"
```bash
# Sync dependencies (frozen, matches CI)
uv sync --frozen
```

### "Tests fail locally but pass in CI"
- Check Python version: `uv run python --version` (should be 3.11)
- Check dependencies are synced: `uv sync --frozen`
- Try running on a clean install: `uv sync --reinstall`

## Related Commands

- `/lint` - Just linting and formatting checks
- `/coverage` - Full coverage analysis with line-by-line detail
- `/pre-merge-check` - Comprehensive pre-merge workflow including CI
