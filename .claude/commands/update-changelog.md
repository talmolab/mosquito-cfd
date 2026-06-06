# Update CHANGELOG.md

Update the project's CHANGELOG.md file (located at `docs/CHANGELOG.md`) following the Keep a Changelog format.

> If `docs/CHANGELOG.md` does not yet exist, create it with the format shown below.

## When to Update

- Adding new features
- Fixing bugs
- Making breaking changes
- Updating dependencies (including pinned solver commits in `docker/build-args.env`)
- Updating Docker images or CI workflows
- Improving documentation
- Refactoring code

## CHANGELOG Format

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New features that have been added

### Changed
- Changes to existing functionality

### Fixed
- Bug fixes

### Deprecated
- Features that will be removed in future versions

### Removed
- Features that have been removed

### Security
- Security fixes and improvements
```

## Categories

- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Vulnerability fixes

## Steps to Update

1. **Check current changes**
```bash
# View recent commits since last tag
git log --oneline $(git describe --tags --abbrev=0)..HEAD

# Or view all uncommitted changes
git diff HEAD
```

2. **Identify change category**
- Is it a new feature? → Added
- Is it a bug fix? → Fixed
- Does it change existing behavior? → Changed
- Does it remove something? → Removed

3. **Write clear descriptions**
- Start with a verb (Added, Fixed, Updated, etc.)
- Be concise but descriptive
- Include PR numbers if applicable
- Reference issues if applicable

## Examples

### Good Examples
```markdown
### Added
- Parametric wing planform generation CLI (`generate-wing-planform`) (#12)
- Run metadata capture (git SHA, docker image, hardware, timing) for reproducibility
- FlowPastSphere validation case (100 timesteps verified on A40)

### Fixed
- Vertex file writer producing inconsistent line endings across platforms
- Degenerate (collinear) planform handling in area computation

### Changed
- Pinned IAMReX commit in docker/build-args.env to the validated revision
- Docker base image to nvidia/cuda:12.4.1-devel-ubuntu22.04
```

### Poor Examples
```markdown
### Added
- New stuff  # Too vague
- Fixed things  # Wrong category and vague
- Updated code  # Not descriptive
```

## Version Numbering

Follow Semantic Versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Incompatible API/CLI/output-format changes
- **MINOR**: Add functionality (backwards compatible)
- **PATCH**: Bug fixes (backwards compatible)

## Releasing a Version

When ready to release:

1. **Move Unreleased items to new version**
```markdown
## [Unreleased]
(empty or future items)

## [0.2.0] - YYYY-MM-DD
### Added
- (move items from Unreleased here)
```

2. **Update version in pyproject.toml**
```bash
uv version 0.2.0
```

3. **Commit and tag**
```bash
git add docs/CHANGELOG.md pyproject.toml
git commit -m "chore: release version 0.2.0"
git tag -a v0.2.0 -m "Release version 0.2.0"
```

## Best Practices

1. **Update as you go**: Don't wait until release to update the CHANGELOG
2. **Be user-focused**: Write from the user's perspective, not implementation details
3. **Include breaking changes**: Clearly mark any breaking API/CLI/output-format changes
4. **Credit contributors**: Mention PR authors when applicable
5. **Link to issues/PRs**: Include links for more context

## Integration

- Run `/update-changelog` before creating a PR to capture changes
- Run `/pre-merge-check` to verify the PR is ready, including changelog updates
- Run `/cleanup-merged` after merge to finalize the release cycle
