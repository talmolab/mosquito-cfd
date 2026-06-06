---
description: Guide through the complete release process for the mosquito-cfd project
---

# Release Process for mosquito-cfd

Comprehensive workflow for releasing a new version of `mosquito-cfd`. This repo is a
**service** that publishes Docker images to GitHub Container Registry (GHCR) via
`.github/workflows/docker.yml`, and builds a Python wheel/sdist with the `uv_build` backend.

## Purpose

This command guides you through the complete release process, ensuring:

1. All pre-release checks pass (tests, coverage, lint/format, CI)
2. Version is bumped correctly following semantic versioning
3. Changes are documented and committed properly
4. GitHub release + tag is created with appropriate notes
5. Docker images are published to GHCR automatically on tag push (via `docker.yml`)
6. Release is verified and documented

## Tool Usage

This project uses **uv** as its build backend and package manager:

- **`uv run <tool>`** — Run tools from the dev dependency group (pytest, ruff)
- **`uvx <tool>`** — Run one-off tools without installing (pip-audit)
- **`uv build`** — Build wheel and sdist using the `uv_build` backend
- **`uv version`** — Manage version numbers with semantic versioning support

## Prerequisites

Before starting a release, ensure:

- You are on the `main` branch with latest changes
- All PRs intended for this release are merged
- CI is passing on the main branch (lint, test, dockerfile-lint)
- You have maintainer permissions for the repository
- `gh` CLI is authenticated
- `uv` is installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Usage

```bash
/prepare-release            # Interactive release workflow
/prepare-release patch      # Bug fixes (0.1.0 → 0.1.1)
/prepare-release minor      # New features (0.1.0 → 0.2.0)
/prepare-release major      # Breaking changes (0.1.0 → 1.0.0)
/prepare-release alpha      # Pre-release alpha (0.1.0 → 0.2.0a1)
/prepare-release beta       # Pre-release beta (0.2.0a1 → 0.2.0b1)
/prepare-release rc         # Release candidate (0.2.0b1 → 0.2.0rc1)
/prepare-release stable     # Stable release (0.2.0rc1 → 0.2.0)
```

**Arguments:** `$ARGUMENTS`

## Release Workflow

### Step 1: Pre-Release Validation

Verify the project is ready for release:

```bash
# Check we're on main branch
git branch --show-current  # Should be 'main'

# Ensure working directory is clean
git status

# Pull latest changes
git pull origin main

# Verify CI is passing on main
gh run list --branch main --limit 5
```

**Run validation commands:**

```bash
# Lint + formatting (matches CI lint job)
uv run ruff check src/
uv run ruff format --check src/

# Full test suite with coverage
uv run pytest tests/ -x -q --cov=src/mosquito_cfd --cov-report=term-missing
```

**Build and validate package:**

```bash
# Build wheel and sdist using uv_build backend
uv build

# Security audit (one-off tool via uvx)
uvx pip-audit || echo "Security audit found issues (review before releasing)"
```

**Stop if any checks fail.** Fix issues before proceeding.

### Step 2: Determine Version Number

Follow semantic versioning (https://semver.org):

**MAJOR.MINOR.PATCH** with optional pre-release suffix (PEP 440)

- **PATCH** (0.1.0 → 0.1.1): Bug fixes, documentation updates, minor improvements
- **MINOR** (0.1.0 → 0.2.0): New features, backward-compatible changes
- **MAJOR** (0.1.0 → 1.0.0): Breaking changes (API/CLI/output-format/Docker-tag changes)
- **Pre-release** (0.1.0 → 0.2.0a1): Alpha/beta/rc for testing before stable

Current version: read from `pyproject.toml` (`uv version`).

**Review changes since last release:**

```bash
LAST_TAG=$(gh release list --limit 1 --json tagName --jq '.[0].tagName' 2>/dev/null || echo "none")
echo "Last release: $LAST_TAG"
if [ "$LAST_TAG" != "none" ]; then
  git log $LAST_TAG..HEAD --oneline --no-merges
else
  echo "No previous releases found. Showing recent commits:"
  git log --oneline -20
fi
```

### Step 3: Metadata Completeness Check

Read `pyproject.toml` and verify these fields exist and are correct:

- `[project]`: name, version, description, readme, requires-python
- `license` field matches the LICENSE file (BSD-3-Clause)
- `[project.scripts]`: `generate-wing-planform` CLI entry point is defined
- `[build-system]`: uses `uv_build` backend
- Pinned external commits in `docker/build-args.env` are at the intended revisions

Report any missing metadata and fix it.

### Step 4: Documentation Audit

Check for consistency across documentation:

1. **CHANGELOG** (`docs/CHANGELOG.md`):
   - Has content in `[Unreleased]` (warn if empty)
   - No duplicate section headers
   - No placeholder dates
   - License references match the actual LICENSE file (BSD-3-Clause)

2. **README.md**:
   - Python version matches `requires-python` in pyproject.toml
   - Install / run (Docker) instructions are correct
   - Docker image tags / GHCR registry references are correct

3. **openspec/project.md**:
   - Current State section reflects what is actually shipped
   - Constraints / Technology Stack are accurate

Report all issues found. Fix or ask the user about ambiguous issues.

### Step 5: Update CHANGELOG

Move `[Unreleased]` content into a new version section (run `/update-changelog`):

```markdown
## [Unreleased]

## [X.Y.Za1] - YYYY-MM-DD (Pre-release)

### Added
- (moved from Unreleased)
...
```

- Use today's date
- Keep an empty `[Unreleased]` section at top
- For pre-releases, use the full PEP 440 version (e.g., `0.1.0a1`) and add `(Pre-release)`
- Clean up any formatting issues

### Step 6: Create Release Branch and Bump Version

```bash
CURRENT_VERSION=$(uv version)
echo "Current version: $CURRENT_VERSION"

# Create release branch
NEW_VERSION="X.Y.Z"  # from Step 2
git checkout -b release/v$NEW_VERSION

# Bump version (uv version manages pyproject.toml)
uv version --bump $ARGUMENTS    # e.g., alpha, beta, rc, patch, minor, major, stable
# Or set explicitly:
# uv version $NEW_VERSION
```

### Step 7: Build and Test Release Artifacts

```bash
# Clean previous builds
rm -rf dist/ build/

# Build wheel + sdist
uv build

# Verify artifacts
ls -lh dist/
# Should see: mosquito_cfd-X.Y.Z-py3-none-any.whl
#             mosquito_cfd-X.Y.Z.tar.gz

# Test wheel install in isolated env
uv run --isolated --with dist/*.whl python -c "import mosquito_cfd; print('import OK')"

# Test CLI entry point
uv run --isolated --with dist/*.whl generate-wing-planform --help
```

### Step 8: Commit Version Bump and Changelog

```bash
git add pyproject.toml docs/CHANGELOG.md
# Include any other files fixed during audit (README, etc.)

git commit -m "chore: bump version to v$NEW_VERSION

- Update version in pyproject.toml
- Update CHANGELOG.md with release notes"

git push origin release/v$NEW_VERSION
```

### Step 9: Create and Merge Version Bump PR

```bash
gh pr create \
  --title "Release v$NEW_VERSION" \
  --body "$(cat <<'EOF'
## Release v$NEW_VERSION

### Version Bump
- Bumps version from $CURRENT_VERSION to $NEW_VERSION

### Pre-Release Checklist
- [x] All tests pass locally
- [x] Coverage verified
- [x] Lint + format checks pass (uv run ruff check / ruff format --check)
- [x] Build artifacts verified (uv build)
- [x] Wheel installs and CLI entry point works
- [x] CI passing on main branch
- [x] CHANGELOG.md updated

### Post-Merge Steps
1. Create GitHub release + tag v$NEW_VERSION
2. Verify Docker image publish to GHCR via .github/workflows/docker.yml
3. Test pulling the published image

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"

# Wait for CI checks
gh pr checks --watch

echo "Request review from maintainers, then merge when approved"
```

### Step 10: Create GitHub Release and Tag

After the PR is merged to main:

**GUARDRAILS before creating the release:**

1. **Verify CHANGELOG is up-to-date**: Read `docs/CHANGELOG.md` and confirm the `[Unreleased]`
   section is empty, the new `## [X.Y.Z]` section exists with today's date, and it has content.

2. **Extract the exact changelog section** for this version:
   ```python
   import re
   with open("docs/CHANGELOG.md") as f:
       content = f.read()
   pattern = rf"## \[{re.escape(NEW_VERSION)}\].*?(?=\n## \[|\Z)"
   match = re.search(pattern, content, re.DOTALL)
   if not match:
       raise ValueError(f"Version {NEW_VERSION} not found in CHANGELOG.md!")
   print(match.group(0).strip())
   ```
   If the section is missing or empty, **stop and fix the CHANGELOG first**.

```bash
git checkout main
git pull origin main

# For pre-releases, add --prerelease; for stable, omit it.
gh release create v$NEW_VERSION \
  --title "mosquito-cfd v$NEW_VERSION" \
  --prerelease \
  --notes "$(cat <<EOF
## Docker Image

\`\`\`bash
docker pull ghcr.io/talmolab/mosquito-cfd:fp64
\`\`\`

## What's Changed

<INSERT EXTRACTED CHANGELOG SECTION HERE — excluding the version header line>

**Full Changelog**: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/commits/v$NEW_VERSION

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Pushing the tag triggers `.github/workflows/docker.yml`, which builds and publishes the
Docker images to GHCR with the configured tag scheme (`{precision}`, `latest-{precision}`,
`{precision}-{sha}`).

### Step 11: Verify Release

```bash
# Watch the docker publish workflow
gh run watch

# Confirm the image is pullable
docker pull ghcr.io/talmolab/mosquito-cfd:fp64

# Confirm the GitHub release exists
gh release view v$NEW_VERSION
```

### Step 12: Post-Release Tasks

```bash
# Clean up release branch (if not auto-deleted)
git branch -d release/v$NEW_VERSION

echo "Release v$NEW_VERSION complete!"
echo "GHCR: https://github.com/talmolab/mosquito-cfd/pkgs/container/mosquito-cfd"
echo "GitHub: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/v$NEW_VERSION"
```

## Rollback Procedures

### If Release Fails Before Image Publish

```bash
# Delete GitHub release
gh release delete v$NEW_VERSION --yes

# Delete tag
git tag -d v$NEW_VERSION
git push origin :refs/tags/v$NEW_VERSION

# Revert version bump on main
git revert HEAD
git push origin main
```

### If Release Fails After Image Publish

- Published GHCR images can be deleted/marked via the GitHub Packages UI, or superseded by
  a new patch release. Prefer releasing a fixed patch version over deleting published tags.

## Publishing Architecture

- **Build backend**: `uv_build` (defined in `pyproject.toml [build-system]`)
- **Build command**: `uv build` (creates wheel + sdist)
- **Image publishing**: `.github/workflows/docker.yml` builds and pushes to
  `ghcr.io/talmolab/mosquito-cfd` on push to main/tags
- **No PyPI publishing workflow** is currently configured; this repo ships as a Docker
  service plus an installable Python utility package built locally with `uv build`.

## Integration with Other Commands

- `/run-ci-locally` - Run exact CI checks locally
- `/lint` - Quick lint + format check
- `/coverage` - Detailed test coverage analysis
- `/update-changelog` - Update CHANGELOG.md with changes
- `/pre-merge-check` - Comprehensive pre-merge validation
- `/cleanup-merged` - Clean up release branch after merge
