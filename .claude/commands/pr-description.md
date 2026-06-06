Update PR description.

Use the `gh` CLI to fetch the current PR description, then update it with a comprehensive description of the changes made in this PR.

Command to fetch PR info:

```bash
gh pr view PR_NUMBER --json number,title,body,url,state,closingIssuesReferences
```

If there is an associated issue (linked in the PR metadata or mentioned in the PR description), then use the `gh` CLI to fetch that too to contextualize the work done in the PR:

```bash
gh issue view ISSUE_NUMBER
```

Include a summary, example usage (for enhancements), API/CLI changes, Docker/CI impact (if any), and other notes for future consideration (including reasoning behind design decisions).

Update the description with:

```bash
gh pr edit PR_NUMBER --body "<new description>"
```
