# OpenSpec Agent Guidelines

This document provides conventions and clarifications for AI agents working with this OpenSpec repository.

## Directory Structure

```
openspec/
├── project.md              # Project overview, goals, architecture
├── AGENTS.md               # This file - agent guidelines
├── specs/                  # Capability specifications
│   └── <capability>/
│       └── spec.md         # Requirements and scenarios
└── changes/                # Proposed changes
    └── <change-id>/
        ├── proposal.md     # Change summary and rationale
        ├── tasks.md        # Implementation work items
        ├── design.md       # Architectural decisions (when needed)
        └── specs/          # Spec deltas for this change
            └── <capability>/
                └── spec.md
```

## Conventions

### Change IDs

- Use verb-led identifiers: `add-validation`, `refactor-markers`, `fix-metadata-hash`
- Keep concise but descriptive
- Lowercase with hyphens

### Spec Files

- One capability per folder under `specs/` or `changes/<id>/specs/`
- Use `## ADDED Requirements`, `## MODIFIED Requirements`, or `## REMOVED Requirements` headers
- Each requirement must have at least one `#### Scenario:` demonstrating expected behavior
- Cross-reference related capabilities with `[Capability Name](../other-capability/spec.md)`

### Requirements Format

```markdown
## ADDED Requirements

### Requirement: <Descriptive Name>

<Requirement description>

#### Scenario: <Scenario Name>

**Given** <initial context>
**When** <action taken>
**Then** <expected outcome>
```

### Tasks Format

Tasks in `tasks.md` should be:
- Ordered by dependency/sequence
- Small and verifiable
- Include validation steps (tests, manual checks)
- Mark parallelizable work with `[parallel]`

```markdown
## Tasks

1. [ ] Implement core function X
2. [ ] Add unit tests for function X
3. [ ] Update documentation
4. [parallel] Integration test A
5. [parallel] Integration test B
```

## Commands Reference

- `openspec list` - List all changes
- `openspec list --specs` - List all specifications
- `openspec show <id>` - Show change details
- `openspec show <spec> --type spec` - Show specification details
- `openspec validate <id>` - Validate a change proposal
- `openspec validate <id> --strict` - Strict validation

## Best Practices

1. **Read before writing**: Always review `project.md` and existing specs before proposing changes
2. **Minimal scope**: Keep changes focused; split large efforts into multiple change proposals
3. **Validate early**: Run `openspec validate` frequently during proposal development
4. **Concrete scenarios**: Write scenarios that can be directly translated to tests
5. **Dependencies explicit**: Note which specs depend on others in cross-references