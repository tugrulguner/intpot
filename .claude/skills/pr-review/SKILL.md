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

Apply these in addition to general correctness/security review:

**Architecture**
- Inspectors (`src/intpot/core/inspectors/`) must subclass `BaseInspector` and return `list[ToolInfo]` from `inspect()`
- Generators (`src/intpot/core/generators/`) must subclass `BaseGenerator` and return `str` from `generate()`
- Commands (`src/intpot/commands/`) should use `typer.Argument` / `typer.Option` and return `None`
- Conversion commands should delegate to `_convert.py`'s shared `convert()` function
- New models belong in `src/intpot/core/models.py`

**ToolInfo / ParameterInfo contracts**
- `ParameterInfo.default` uses `_SENTINEL` for required params — check that new code uses the `.required` property instead of comparing against `_SENTINEL` directly, especially outside of `core/`
- `ParameterInfo.name` and `ToolInfo.name` are auto-sanitized via `sanitize_identifier()` — don't duplicate that logic
- Changes to these dataclasses affect all inspectors, generators, and transforms — check ripple effects

**Templates (src/intpot/templates/*.j2)**
- Templates use custom Jinja2 filters: `repr`, `pascal`, `escape_doc` — verify any new filter usage is registered in `_render.py`
- Generated code must include correct imports (check the import block logic)
- Path params in API template should NOT get `= Path(...)` — FastAPI infers them from the route

**Transforms (src/intpot/core/transforms.py)**
- AST transformations handle `typer.echo` ↔ `return` and `typer.Exit` ↔ `raise` — verify new transforms don't break these
- Return type adjustments: CLI → `None`, API → `dict`, MCP → preserves or `str`

**Detection and discovery**
- `detect_source()` raises `DetectionError` — commands must catch this and show a user-friendly message, not a traceback
- `discover_sources()` silently skips unrecognizable files — this is intentional

**Error handling**
- Commands should catch `DetectionError` and exit with `typer.Exit(1)` + a message to stderr
- Never let internal exceptions (DetectionError, import errors, AST errors) leak as tracebacks to CLI users

**Testing patterns**
- Tests use `tmp_source` fixture from `conftest.py` (factory that writes temp Python files)
- CLI tests use `typer.testing.CliRunner`
- Test names follow `test_<scenario>` or `test_<framework>_<scenario>`
- Tests should assert specific behavior, not just `exit_code == 0` — check that outputs contain expected content
- Exception tests use `pytest.raises(ErrorClass, match="...")`

**Code style**
- All files start with `from __future__ import annotations`
- Ruff handles formatting (line length 88, double quotes, isort with intpot first-party)
- B008 is suppressed — `typer.Option()` / `typer.Argument()` as defaults are intentional
- No unnecessary abstractions, docstrings, or type annotations on existing code

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
