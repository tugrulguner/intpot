---
name: sync-skills
description: Update intpot's agent-facing docs when architecture, patterns, or conventions change. TRIGGER when base classes change (BaseInspector, BaseGenerator, ToolInfo, ParameterInfo), new commands/inspectors/generators are added, error handling or return-type rules change, template filters or structure change, test conventions change, or the public API changes.
user-invocable: true
allowed-tools: Read Grep Glob Edit Write Agent
paths: "src/intpot/core/models.py, src/intpot/core/inspectors/base.py, src/intpot/core/generators/base.py, src/intpot/core/generators/_render.py, src/intpot/core/transforms.py, src/intpot/core/detector.py, src/intpot/core/discovery.py, src/intpot/commands/*, src/intpot/templates/*.j2, tests/conftest.py, AGENTS.md"
---

# Sync agent docs

Follow the **Keeping the docs honest** section of [`AGENTS.md`](../../../AGENTS.md): work
out which of the two doc surfaces the change affects, verify every claim against the
source rather than against the old wording, and make targeted edits.

Then run `.venv/bin/pytest tests/test_skills_content.py tests/test_docs.py` and report
what you changed and what you verified.
