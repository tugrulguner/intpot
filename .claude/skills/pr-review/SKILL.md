---
name: pr-review
description: Review a GitHub pull request on the intpot repo. Use when asked to review a PR, given a PR URL or number, or told to check a pull request.
disable-model-invocation: true
allowed-tools: Bash(gh *) Bash(git *) Bash(.venv/bin/python *) Bash(.venv/bin/pytest *) Read Grep Glob Agent
argument-hint: <pr-number-or-url>
---

# intpot PR Review

Review a pull request on the intpot codebase — a converter between Typer (CLI), FastMCP (MCP), and FastAPI (API).

## Input

`$ARGUMENTS` is a PR number (e.g. `25`) or full GitHub PR URL.

## Steps

### 1. Gather context

Run in parallel:
- `gh pr view $ARGUMENTS --json title,body,state,additions,deletions,changedFiles,baseRefName,headRefName,author,commits`
- `gh pr diff $ARGUMENTS`
- `gh pr view $ARGUMENTS --json reviews,comments`

If an earlier review exists and the author pushed fixes, focus on whether the fixes address that feedback. Don't re-review unchanged code.

### 2. Understand the affected code

Read the files the PR touches in their current main-branch state before judging the diff. Understand what exists today and why the change is being made.

### 3. intpot-specific checks

Read the **Reviewing a change** section of [`AGENTS.md`](../../../AGENTS.md) and apply it,
along with the **Rules that come from real bugs** section above it. Those are the criteria
for this codebase and they live there so every agent and every human reviewer reads the
same list. Don't restate them here — this file would go stale, and it has before.

Apply general correctness and security review on top of them.

### 4. Verify your claims

Before posting any comment, verify it:
- If you claim a function doesn't exist → grep for it
- If you claim a code path is broken → trace through it
- If you claim an import is wrong → check the actual module
- If you're unsure → search the codebase rather than guessing

Do NOT post a comment you cannot back up with evidence.

### 5. Post the review

Classify findings:
- **High** — Bugs, security issues, broken behavior, leaked tracebacks. Must fix before merge.
- **Medium** — Design issues, inconsistencies, missing tests for important paths. Should fix.
- **Low** — Style nits, minor improvements. Optional.

Use `gh pr review` with:
- `--request-changes` if any High issues
- `--comment` if only Medium/Low
- `--approve` if everything looks good

Format:
```
## Review

[1-2 sentence assessment]

### High: [title]
[file:line — explanation + suggested fix]

### Medium: [title]
[file:line — explanation + suggested fix]

### Low: [title]
[explanation]

### What looks good
[2-3 specific bullets]
```

## Rules

- Never combine your own findings with comments from external sources into one review. Keep them separate.
- Fewer accurate comments beat many questionable ones.
- Do not flag formatting — ruff handles it.
- Do not suggest adding docstrings or comments to working code.
- Do not suggest improvements beyond what the PR set out to do.
