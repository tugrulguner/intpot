---
name: sync-skills
description: Update intpot's agent-facing docs when architecture, patterns, or conventions change. TRIGGER when base classes change (BaseInspector, BaseGenerator, ToolInfo, ParameterInfo), new commands/inspectors/generators are added, error handling or return-type rules change, template filters or structure change, test conventions change, or the public API changes.
user-invocable: true
allowed-tools: Read Grep Glob Edit Write Agent
paths: "src/intpot/core/models.py, src/intpot/core/inspectors/base.py, src/intpot/core/generators/base.py, src/intpot/core/generators/_render.py, src/intpot/core/transforms.py, src/intpot/core/detector.py, src/intpot/core/discovery.py, src/intpot/commands/*, src/intpot/templates/*.j2, tests/conftest.py, AGENTS.md"
---

# Sync agent docs

intpot has two sets of agent-facing docs, and they rot for different reasons.

| What | Who reads it | Goes stale when |
|------|--------------|-----------------|
| `AGENTS.md` | Anyone working **on** intpot — every agent, every human | Internal contracts change |
| `src/intpot/templates/skills/*.md` | **Users'** agents, via `intpot add skills` | The public API changes |

`.claude/skills/*/SKILL.md` deliberately hold no criteria — only procedure. If you find
yourself adding a rule to one of them, it belongs in `AGENTS.md` instead. Three copies of
the same checklist is what this repo had before, and two of them were wrong.

## Steps

### 1. Identify what changed

Read the changed files and decide which side is affected:

- **Internal contract** — a field on `ToolInfo`/`ParameterInfo`, a base-class signature, a
  new inspector/generator/command, a new exception, a new Jinja filter, a return-type
  rule, a test convention → `AGENTS.md`
- **Public API** — anything a user writes in their own code: `@app.tool()`, `App.serve`,
  `App.eject`, `intpot.load`, CLI commands and flags → `templates/skills/*.md`, **and**
  the README's CLI reference

Both can be true of one change.

### 2. Check against reality, not against the old text

For every claim you are about to write or keep, verify it in the source. The two rules
that went stale here survived a rewrite because nobody re-read the code:

- "API return type is always `dict`" — false since #56; it is `None` for a body with no
  top-level return
- "`discover_sources()` silently skips files" — false since #59; import failures always
  report to stderr

### 3. Edit

Make targeted edits. Don't rewrite for style. If a rule came from a real bug, say which
bug — that is what stops someone deleting it later as noise.

### 4. Verify

- `.venv/bin/pytest tests/test_skills_content.py tests/test_docs.py` — these guard the
  shipped skills against API drift and the docs against dead paths and undocumented flags
- Confirm no path or symbol you referenced has since moved

### 5. Report

One short summary: what changed, which files you updated, what you verified.
