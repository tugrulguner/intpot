# Reviewing a change to intpot

The procedure. The criteria are in [`AGENTS.md`](../AGENTS.md) — read the **Reviewing a
change** and **Rules that come from real bugs** sections before you start.

This is written for whoever is doing the review: a person, or an agent of any kind. It
assumes nothing beyond a shell, `git`, and `gh` for the pull-request case.

## 1. Gather

**A pull request:**

```bash
gh pr view <pr> --json title,body,state,additions,deletions,changedFiles,baseRefName,headRefName,author,commits
gh pr diff <pr>
gh pr view <pr> --json reviews,comments
```

If an earlier review exists and the author has pushed fixes since, review whether the
fixes address that feedback. Don't re-review unchanged code.

**Uncommitted work:**

```bash
git diff              # optionally scoped to a path
git diff --cached
git status            # untracked files count as part of the change
```

## 2. Understand what's there now

Read the files the change touches in their current `main` state before judging the diff.
A diff read on its own tends to produce comments about code that was already like that.

## 3. Apply the criteria

From `AGENTS.md`, then general correctness and security review on top.

## 4. Run the tests that matter

Always `make check` before signing off. While iterating, the narrower runs are:

| Changed | Run |
|---|---|
| `src/intpot/core/inspectors/` | `.venv/bin/pytest tests/test_inspectors/ -x` |
| `src/intpot/core/generators/` or `src/intpot/templates/` | `.venv/bin/pytest tests/test_generators/ -x` |
| `src/intpot/commands/` or `src/intpot/cli.py` | `.venv/bin/pytest tests/test_commands/ -x` |
| `src/intpot/core/transforms.py` | `.venv/bin/pytest tests/test_roundtrip.py tests/test_transforms.py -x` |
| `src/intpot/runtime.py`, `src/intpot/runtime_builders.py` | `.venv/bin/pytest tests/test_runtime.py tests/test_runtime_builders.py -x` |
| Anything public-facing | `.venv/bin/pytest tests/test_skills_content.py tests/test_docs.py -x` |

## 5. Verify every claim before you make it

This is the step that separates a useful review from a noisy one.

- Claiming a function doesn't exist → grep for it
- Claiming a code path is broken → trace it, or execute it
- Claiming an import is wrong → open the module
- Unsure → search the codebase instead of guessing

Don't raise anything you can't back with evidence. Four of the bugs this project has
shipped looked correct as text; if a claim is about generated code, run the generated
code.

## 6. Report

Classify:

- **High** — bugs, security issues, broken behaviour, tracebacks leaked to users. Blocks
  merge.
- **Medium** — design problems, inconsistency with a sibling module, an important path
  left untested. Should fix.
- **Low** — optional improvements.

For a pull request, post with `gh pr review <pr>` — `--request-changes` if anything is
High, `--comment` for Medium and Low only, `--approve` if it's clean. For local work, a
short summary and a verdict is enough.

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

- Keep your own findings separate from comments quoted from anywhere else. Never merge
  them into one review.
- Few accurate comments beat many plausible ones.
- Don't flag formatting — ruff owns it.
- Don't ask for docstrings or comments on working code.
- Don't propose improvements beyond what the change set out to do.
