---
name: sync-skills
description: Update all .claude/skills/ when intpot's architecture, patterns, or conventions change. TRIGGER when base classes change (BaseInspector, BaseGenerator, ToolInfo, ParameterInfo), new commands/inspectors/generators are added, error handling patterns change, template filters or structure change, test conventions change, or CLAUDE.md is updated.
user-invocable: true
allowed-tools: Read Grep Glob Edit Write Agent
paths: "src/intpot/core/models.py, src/intpot/core/inspectors/base.py, src/intpot/core/generators/base.py, src/intpot/core/generators/_render.py, src/intpot/core/transforms.py, src/intpot/core/detector.py, src/intpot/core/discovery.py, src/intpot/commands/*, src/intpot/templates/*.j2, tests/conftest.py, CLAUDE.md"
---

# Sync Skills

When intpot's architecture, patterns, or conventions change, update the review skills in `.claude/skills/` so they stay accurate.

## When to run

This skill should activate when any of these change:

- **Core models** (`models.py`): New fields on `ToolInfo`/`ParameterInfo`, new enums, sentinel changes
- **Base classes** (`base.py` in inspectors/generators): Contract changes to `inspect()` or `generate()`
- **New inspectors/generators/commands**: A new file appears in those directories
- **Detector/discovery** (`detector.py`, `discovery.py`): New exception types, new detection patterns
- **Templates** (`*.j2`): New filters, new template variables, structural changes
- **Transforms** (`transforms.py`): New AST transformations, new return type rules
- **Test conventions** (`conftest.py`): New fixtures, changed patterns
- **CLAUDE.md**: New environment or workflow rules

## Steps

### 1. Identify what changed

Read the changed files. Determine which category of change occurred:
- New contract or field (affects architecture checks in skills)
- New pattern or convention (affects what skills tell Claude to look for)
- New error type or handling pattern (affects error handling checks)
- New command/inspector/generator (needs to be referenced in skills)
- Environment or tooling change (affects allowed-tools or run instructions)

### 2. Read current skills

Read all SKILL.md files:
- `.claude/skills/pr-review/SKILL.md`
- `.claude/skills/review-code/SKILL.md`
- Any other skills in `.claude/skills/`

### 3. Determine what's stale

Compare the current skill content against the actual codebase state. Look for:
- References to classes, functions, or patterns that no longer exist
- Missing references to new classes, functions, or patterns that should be checked during review
- Outdated test conventions or fixture names
- Wrong file paths or directory structures
- Stale allowed-tools lists
- Outdated architecture descriptions

### 4. Update skills

Edit only the parts that are stale. Do not rewrite entire skills — make targeted edits.

**Common updates:**

| Change | What to update in skills |
|--------|------------------------|
| New field on `ParameterInfo`/`ToolInfo` | Add to the contracts section in pr-review |
| New inspector/generator subclass | Add to the architecture checks |
| New custom exception | Add to error handling checks |
| New Jinja2 filter | Add to template checks |
| New AST transform | Add to transform consistency checks |
| New test fixture | Add to testing patterns section |
| New command pattern | Add to command structure checks |
| CLAUDE.md env change | Update allowed-tools or run instructions |

### 5. Verify

After editing, read back each modified skill and confirm:
- No broken references to files or classes that don't exist
- No duplicate entries
- Instructions are still coherent and not contradictory
- Severity guidance still makes sense

### 6. Report

Output a short summary of what changed and which skills were updated.

## Rules

- Only update what's actually stale. Don't rewrite for style.
- If a change doesn't affect review guidance, don't touch the skills.
- Keep the same structure and tone as the existing skills.
- Never remove checks — only update or add. If a pattern is deprecated, note what replaced it.
