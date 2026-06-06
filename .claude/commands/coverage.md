Run tests with coverage.

## Usage

Run the full test suite with coverage analysis:

```bash
uv run pytest --cov=src/mosquito_cfd --cov-report=term-missing tests/
```

This generates a coverage summary showing per-file hit/miss statistics with line numbers for uncovered code.

## Arguments

$ARGUMENTS

Supported arguments:
- `--html` - Generate HTML coverage report in `htmlcov/`
- `--xml` - Generate XML report for CI (matches GitHub Actions)
- `--cov-fail-under N` - Fail if coverage drops below N%

## Examples

```bash
# Basic coverage summary
uv run pytest --cov=src/mosquito_cfd --cov-report=term-missing tests/

# With HTML report for browsing
uv run pytest --cov=src/mosquito_cfd --cov-report=term-missing --cov-report=html tests/

# XML report matching CI
uv run pytest --cov=src/mosquito_cfd --cov-report=xml --durations=-1 tests/

# Fail if coverage drops below 80%
uv run pytest --cov=src/mosquito_cfd --cov-report=term-missing --cov-fail-under=80 tests/

# Coverage for specific test file
uv run pytest --cov=src/mosquito_cfd --cov-report=term-missing tests/test_geometry.py
```

## Interpreting Results

The `term-missing` report shows:
- **Stmts**: Total statements in file
- **Miss**: Uncovered statements
- **Cover**: Coverage percentage
- **Missing**: Line numbers not covered by tests

Focus on:
1. New code added in the current PR
2. Critical paths (geometry generation, metadata capture, numerical transforms)
3. Edge cases (empty data, NaN handling, boundary conditions)

## Integration

After running coverage:
- Use results to identify untested code paths
- Write targeted tests for uncovered lines
- Run `/lint` to verify code quality
- Run `/run-ci-locally` for full CI verification
