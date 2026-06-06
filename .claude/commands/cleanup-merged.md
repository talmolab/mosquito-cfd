---
description: Clean up merged branch and archive OpenSpec change
---

# Clean Up Merged Branch

Clean up after a PR merge by deleting branches and archiving OpenSpec changes.

## 1. Verify Merge Status

First, confirm the PR has been merged:

```bash
# Show recent merged PRs
gh pr list --state merged --limit 5

# View specific PR status
gh pr view <number>
```

Verify the branch appears in the merged list before proceeding.

## 2. Switch to Main and Pull

```bash
git checkout main
git pull
```

Confirm you're on the latest main branch.

## 3. Delete Feature Branch

Delete both local and remote tracking references:

```bash
# Delete local branch (safety check with -d)
git branch -d <branch-name>

# Prune remote tracking references
git remote prune origin
```

**Important**: The `-d` flag (not `-D`) ensures the branch has been merged. Git will prevent deletion if the branch hasn't been fully merged.

## 4. Archive OpenSpec Change (if applicable)

If this was an OpenSpec-tracked change:

### Check for OpenSpec directory

```bash
ls openspec/changes/
```

### Archive using OpenSpec CLI

```bash
# Archive the change (moves to archive and updates specs)
openspec archive <change-id> --yes
```

If the change is tooling-only (no spec deltas):

```bash
openspec archive <change-id> --yes --skip-specs
```

### Validate after archival

```bash
openspec validate --strict
```

## 5. Commit and Push

```bash
git add openspec/
git commit -m "chore: Archive <change-id> OpenSpec change

Moved completed OpenSpec change to archive after PR #<number> merge.

Related: PR #<pr-number>"

git push
```

## 6. Verify Cleanup

Confirm cleanup is complete:

```bash
# Branch should not appear
git branch -a | grep <branch-name> || echo "Branch deleted"

# OpenSpec should be in archive (if applicable)
ls openspec/changes/archive/<change-id>

# Validate OpenSpec state
openspec validate --strict
```

## Summary Checklist

After cleanup, verify:

- Branch deleted (local + remote pruned)
- OpenSpec change archived (if applicable)
- OpenSpec validates cleanly (if applicable)
- Main branch clean and up-to-date

## Common Scenarios

### Scenario 1: Simple bug fix (no OpenSpec)

1. Switch to main, pull
2. Delete branch
3. Done

### Scenario 2: Feature with OpenSpec documentation

1. Switch to main, pull
2. Delete branch
3. Archive OpenSpec change with CLI
4. Validate, commit, push

### Scenario 3: Branch not yet merged

**Stop!** Do not force delete with `-D`.

1. Check merge status: `gh pr view <number>`
2. If PR is still open, ask user to merge first
3. If PR was closed without merging, confirm before force deletion

## Safety Checks

### Before Deleting

```bash
# Verify branch is fully merged
git branch --merged main | grep <branch-name>

# If not in the list, the branch is NOT fully merged
```

### Force Delete Warning

**Never** use `git branch -D` unless you're absolutely certain:

- The branch was closed without merging (intentional)
- You've verified with the team this is the right action
- You understand the commits will be lost

## Troubleshooting

### Branch won't delete

```
error: The branch '<branch-name>' is not fully merged.
```

**Solution**: Check if PR was actually merged:

```bash
gh pr view <number>
```

If it shows "Merged", there may be a remote sync issue:

```bash
git fetch --all --prune
git checkout main
git pull
git branch -d <branch-name>
```

### Can't find OpenSpec change

Not all PRs have OpenSpec documentation. Check:

```bash
ls openspec/changes/
```

If the change isn't there, skip the archive step.

## Integration

- Run after `/pre-merge-check` confirms PR is ready
- Follow up with `/update-changelog` if needed
- Use `openspec list` to verify archive state
