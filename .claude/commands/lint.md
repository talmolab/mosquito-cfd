Run linting and formatting with `ruff`.

This matches the lint job in `.github/workflows/ci.yml`.

## Check Mode (default)

Verify linting and formatting without modifying files:

```bash
uv run ruff check src/ && uv run ruff format --check src/
```

## Fix Mode

Auto-fix linting and formatting issues:

```bash
uv run ruff check --fix src/ && uv run ruff format src/
```

Then manually fix any remaining errors which cannot be automatically fixed by ruff.

## CI Reference

These commands mirror the `lint` job in `.github/workflows/ci.yml`:
- **Lint step 1**: `uv run ruff check src/`
- **Lint step 2**: `uv run ruff format --check src/`

> Note: formatting is checked via `ruff format` (line-length 88, configured in `[tool.ruff]`),
> and docstring linting (ruff `D`, Google convention) is configured in `pyproject.toml`.
> CI enforces formatting with `ruff format --check`.

## Integration

- Run `/lint` before committing to catch issues early
- Run `/fix-formatting` to auto-apply formatting fixes
- Run `/run-ci-locally` for full CI verification including tests
- Run `/pre-merge-check` for comprehensive PR readiness
