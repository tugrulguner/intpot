---
name: review-code
description: Review uncommitted or staged code changes in the intpot repo. Use when asked to review local changes, check current diff, or review before committing.
disable-model-invocation: true
allowed-tools: Bash(git *) Bash(.venv/bin/python *) Bash(.venv/bin/pytest *) Read Grep Glob Agent
argument-hint: [file-path]
---

# intpot Local Code Review

Review uncommitted changes in the working tree before they become a PR.

## Input

`$ARGUMENTS` is an optional file path to scope the review. If empty, review all uncommitted changes.

## Steps

### 1. Gather the diff

- If `$ARGUMENTS` is provided: `git diff $ARGUMENTS` and `git diff --cached $ARGUMENTS`
- Otherwise: `git diff` and `git diff --cached` for all changes
- `git status` to see untracked files

### 2. Read context

For each changed file, read enough of the unchanged surrounding code to understand the intent.

### 3. Review

Read the **Reviewing a change** and **Rules that come from real bugs** sections of
[`AGENTS.md`](../../../AGENTS.md) and apply them. That file is the single copy of this
codebase's criteria — it also tells you what *not* to flag (formatting, docstrings on
untouched code, scope creep).

### 4. Run tests

Run `git diff --name-only` to find changed files, then run relevant tests:
- Changes in `src/intpot/core/inspectors/` → `.venv/bin/pytest tests/test_inspectors/ -x`
- Changes in `src/intpot/core/generators/` → `.venv/bin/pytest tests/test_generators/ -x`
- Changes in `src/intpot/commands/` → `.venv/bin/pytest tests/test_commands/ -x`
- Changes in `src/intpot/core/transforms.py` → `.venv/bin/pytest tests/test_roundtrip.py -x`
- Otherwise → `.venv/bin/pytest -x --tb=short`

### 5. Report

Output a short summary:
- List issues found with severity (High/Medium/Low) and file:line references
- Test results (pass/fail)
- One line verdict: ready to commit, or what needs fixing
