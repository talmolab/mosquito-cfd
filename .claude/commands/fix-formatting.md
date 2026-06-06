# Fix Formatting Issues

Automatically fix formatting and style issues instead of just checking them.

## Quick Start

```bash
# Auto-fix all formatting + lint issues
uv run ruff check --fix src/
uv run ruff format src/
```

This command will:
1. Run Ruff's autofixer to resolve lint issues (imports, pyupgrade, etc.)
2. Run Ruff's formatter to format all Python code
3. Show what changed

> Note: formatting is done via `ruff format` (line-length 88, configured in `[tool.ruff]`
> in `pyproject.toml`), enforced in CI by `ruff format --check`.

## What Gets Fixed

### Ruff Format
- Line length (88 characters, per `[tool.ruff]` in `pyproject.toml`)
- Quote style (double quotes)
- Indentation (4 spaces)
- Trailing commas
- Whitespace normalization

### Ruff Lint Autofix (E, F, I, UP, D rule sets)
- Import sorting (`I`)
- Unused imports (`F401`)
- pyupgrade modernizations (`UP`)

### Not Auto-Fixed
- Docstring content (must fix manually)
- Variable names
- Logic errors
- Most `F`-class correctness issues (must fix manually)

## Commands Executed

```bash
# Auto-fix lint issues first, then format
uv run ruff check --fix src/
uv run ruff format src/
```

## Expected Output

### Files Reformatted

```
$ uv run ruff check --fix src/
Found 3 errors (3 fixed, 0 remaining).

$ uv run ruff format src/
2 files reformatted, 12 files left unchanged.

Formatting fixed! Review changes with 'git diff'
```

### No Changes Needed

```
$ uv run ruff check --fix src/
All checks passed!

$ uv run ruff format src/
14 files left unchanged.

Code already properly formatted!
```

## Usage Workflow

### Before Committing

```bash
# 1. Fix formatting automatically
/fix-formatting

# 2. Review changes
git diff

# 3. Stage and commit
git add -u
git commit -m "style: apply ruff formatting"
```

### After PR Review

```bash
# Reviewer says: "Please fix formatting"

# Quick fix:
/fix-formatting

# Commit the fixes
git add -u
git commit -m "style: fix formatting per review"
git push
```

### Before Creating PR

```bash
# Clean up formatting before opening PR
/fix-formatting

# Check everything passes
/run-ci-locally

# Create PR
gh pr create
```

## What to Review After Running

### Check Git Diff

Always review what Ruff changed:

```bash
git diff src/
```

**Look for:**
- Line wrapping changes (long lines split)
- Quote normalization (' -> ")
- Trailing comma additions
- Import reordering
- Whitespace changes

**Common changes:**
```python
# Before
def discretize_wing(vertices: np.ndarray, n_panels: int = 8, smooth: bool = True, scale: float = 1.0) -> np.ndarray:
    return np.concatenate([interp(a, b) for a, b in zip(vertices[:-1], vertices[1:])])

# After (ruff formatted)
def discretize_wing(
    vertices: np.ndarray,
    n_panels: int = 8,
    smooth: bool = True,
    scale: float = 1.0,
) -> np.ndarray:
    return np.concatenate(
        [interp(a, b) for a, b in zip(vertices[:-1], vertices[1:])]
    )
```

### Verify Tests Still Pass

Formatting should never break tests, but verify:

```bash
uv run pytest tests/
```

If tests fail after formatting, you likely have a syntax error (rare).

## Comparison with /lint

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/lint` | **Check** lint/formatting without changing | Before push, to verify |
| `/fix-formatting` | **Fix** lint/formatting automatically | After changes, to clean up |

**Workflow:**
1. Write code
2. Run `/fix-formatting` to auto-fix
3. Run `/lint` to verify what remains
4. Commit

## Configuration

Ruff configuration lives in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "D"]  # D = pydocstyle (Google convention)
ignore = ["E501"]                     # ruff format owns line length
```

## Manual Fixes Still Needed

Some issues require manual fixing:

### Docstring Issues

```python
# Ruff format won't add or fix docstring content
def compute_area(vertices):
    """Compute area"""  # Missing period

# Fix manually:
def compute_area(vertices):
    """Compute polygon area."""  # Correct
```

### Missing Docstrings

Ruff format won't add docstrings — write them yourself. Run `/lint` after
`/fix-formatting` to find remaining issues.

## Tips

1. **Run frequently**: Format as you go, not at the end
2. **Separate commits**: Keep formatting-only changes in their own commit
3. **Review diffs**: Make sure Ruff didn't do anything unexpected
4. **IDE integration**: Set up Ruff in your editor to format on save

## Troubleshooting

### "ruff not found"
```bash
uv sync --frozen
```

### "Formatting broke my code"
Very rare, but if it happens:
```bash
# Revert
git checkout -- src/
```

## Related Commands

- `/lint` - Check lint/formatting without fixing
- `/run-ci-locally` - Run all CI checks (includes formatting check)
- `/coverage` - Verify tests still pass after formatting
