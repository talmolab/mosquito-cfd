# View GitHub Copilot Review Comments

**Quick command to view all GitHub Copilot inline code review comments for a PR**

The repository is resolved dynamically via `gh repo view`, so these commands work in any
checkout without hardcoding the repo name.

## Quick Usage (GraphQL - Recommended)

```bash
# For a specific PR number (simpler, more reliable)
REPO_OWNER=$(gh repo view --json owner --jq '.owner.login')
REPO_NAME=$(gh repo view --json name --jq '.name')
gh api graphql \
  -f owner="$REPO_OWNER" \
  -f name="$REPO_NAME" \
  -F prNumber=PR_NUMBER \
  -f query='
query($owner: String!, $name: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $prNumber) {
      reviews(first: 10) {
        nodes {
          author { login }
          comments(first: 50) {
            nodes {
              path
              line
              body
            }
          }
        }
      }
    }
  }
}
' --jq '.data.repository.pullRequest.reviews.nodes[] | select(.author.login | contains("opilot")) | .comments.nodes[] | "File: \(.path):\(.line)\n\(.body)\n" + ("="*80)'
```

## Alternative: REST API

```bash
# For current PR dynamically (repo + PR number resolved from gh)
gh api repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/pulls/$(gh pr view --json number -q .number)/comments --jq '.[] | "File: \(.path):\(.line // .original_line)\n\(.body)\n" + ("="*80)'
```

## What This Does

1. Fetches all inline code review comments from Copilot
2. Formats each comment showing:
   - File path and line number
   - Comment body
   - Separator line between comments

## Important Notes

- GitHub Copilot inline comments come from user **"Copilot"**
- Review summaries come from **"copilot-pull-request-reviewer[bot]"**
- GraphQL approach can fetch both in one query (more efficient)
- REST API requires separate calls for reviews vs comments

## Get Review Summary

To see the overall review summary from Copilot:

```bash
REPO_OWNER=$(gh repo view --json owner --jq '.owner.login')
REPO_NAME=$(gh repo view --json name --jq '.name')
gh api graphql \
  -f owner="$REPO_OWNER" \
  -f name="$REPO_NAME" \
  -F prNumber=PR_NUMBER \
  -f query='
query($owner: String!, $name: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $prNumber) {
      reviews(first: 10) {
        nodes {
          author { login }
          state
          body
          submittedAt
        }
      }
    }
  }
}
' --jq '.data.repository.pullRequest.reviews.nodes[] | select(.author.login | contains("opilot")) | {state, submitted: .submittedAt, body}'
```

## Typical Copilot Comments Include

- Code quality suggestions
- Error handling improvements
- Type safety recommendations
- Best practice violations
- Inconsistencies with documented patterns
- Missing edge case handling

## Integration with Pre-Merge Checks

This command should be run as part of the pre-merge workflow (Phase 6: Review Feedback) to ensure all Copilot feedback is addressed before merging.

## Example Output

```
File: src/mosquito_cfd/geometry/planform.py:120
Empty array fallback for the vertex list creates inconsistent geometry. Should raise or return an empty result for missing optional values...
================================================================================
File: src/mosquito_cfd/benchmarks/metadata.py:56
Missing error handling when the docker image digest cannot be resolved. If the result is None, downstream metadata has no feedback...
================================================================================
```
