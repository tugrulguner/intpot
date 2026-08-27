# AGENTS.md

Guidance for coding agents working **on intpot**. If you want intpot's skills for your
*own* project instead, run `intpot add skills`.

## What intpot is

Two halves that meet at one schema:

- **Runtime** — `@app.tool()` registers a function; `App.serve()` builds a live Typer /
  FastAPI / FastMCP instance, `App.eject()` returns standalone source.
- **Converter** — `intpot to cli|mcp|api` reads an existing Typer / FastMCP / FastAPI app
  and generates the equivalent in another framework.

Both produce `ToolInfo` (`src/intpot/core/models.py`). Everything upstream builds it;
everything downstream consumes it. When you add a capability, ask which side of that
boundary it belongs on.

```
   @app.tool()                    source .py file
        |                    DETECT -> INSPECT
        +--------> ToolInfo[] <--------+
              |                  |
     live framework          GENERATE
       instance            (Jinja template)
```

## Layout

| Path | What's there |
|------|--------------|
| `core/models.py` | `ToolInfo`, `ParameterInfo`, `ParamSource`, `sanitize_identifier` |
| `core/detector.py` | Identifies the framework; **imports the source file to do it** |
| `core/inspectors/` | Framework → `ToolInfo` |
| `core/generators/` + `templates/*.j2` | `ToolInfo` → source code |
| `core/transforms.py` | Rewrites bodies and return types between frameworks |
| `runtime.py`, `runtime_builders.py` | The `App` class and live instance builders |
| `commands/` | One module per CLI command; `cli.py` wires them together |
| `templates/skills/` | Shipped to *users* by `intpot add skills` |

## Coding guidelines

Rules for changing intpot source — including the ones that each cost a real bug — and
the architectural contracts a change has to keep live in
[`src/intpot/AGENTS.md`](src/intpot/AGENTS.md). Agents read the nearest file in the
directory tree, so editing source picks them up automatically.

## Workflow

```bash
uv sync --all-extras     # never install globally; never use bare pip
make check               # ruff + pyright + pytest — must pass before a PR
```

Run Python through `.venv/bin/python` or `uv run`.

**Every user-facing change needs a changelog fragment.** Tracked work uses
`changelog.d/<issue-number>.<type>.md`. For a small direct change without an issue, run
`uv run towncrier create +.changed.md` and replace `changed` with `added`, `deprecated`,
`removed`, or `fixed` when appropriate. Numeric fragments refer to issues, never pull
requests. Write one sentence about what changed *for a user*, not what you did to the code.
CI rejects removed-only fragments and PR-number identifiers; a maintainer applies the
`skip-changelog` label for genuinely internal work. Never edit `CHANGELOG.md` by hand—it is
assembled at release time. See `changelog.d/README.md`.

**Never hand-edit the version**, and never bump it as part of a feature PR. It lives only
in `pyproject.toml`; `uv version 0.5.1` updates it and the lockfile together, and
`__version__` reads it back through `importlib.metadata`. Cutting a release is a
maintainer task — see `docs/releasing.md`.

**Do not commit** conflict copies (`file 2.py`), `.venv`, or your agent's own config
directory. Stage explicit paths rather than `git add -A`.

## Keeping the docs honest

Two doc surfaces rot, for different reasons, and both are read by agents rather than by
people who would notice:

| What | Read by | Update it when |
|------|---------|----------------|
| This file, and `docs/reviewing.md` | Anyone working **on** intpot | An internal contract changes: a field on `ToolInfo`/`ParameterInfo`, a base-class signature, a new inspector/generator/command, a new exception, a new Jinja filter, a return-type rule, a test convention |
| `src/intpot/templates/skills/*.md` | **Users'** agents, via `intpot add skills` | The public API changes: `@app.tool()`, `App.serve`, `App.eject`, `intpot.load`, any CLI command or flag — and update the README's CLI reference in the same PR |

The shipped skills went five months describing an API that no longer existed. Update
whichever surface applies in the same PR as the change, not afterwards.

**Verify each claim against the source, not against the previous wording.** Two rules in
this repo's review criteria survived a rewrite while being wrong, because they were edited
as prose: "the API return type is always `dict`" (false since #56) and "`discover_sources`
skips files silently" (false since #59). If a rule came from a real bug, name the bug —
that is what stops the next person deleting it as noise.

`tests/test_skills_content.py` and `tests/test_docs.py` catch the mechanical cases: a
shipped skill naming a field that no longer exists, a CLI flag missing from the README, a
path in this file that git doesn't know about. They can't catch a rule that is merely
wrong.

**Nothing vendor-specific is tracked in this repo.** There is no `.claude/`, `.cursor/`,
or `.windsurf/` directory here, and there was: the review criteria lived in Claude-only
skill files, where no other agent could read them and nobody noticed two of them going
wrong. Guidance goes in this file or `docs/reviewing.md`, both of which every tool and
every human reads. If your agent wants a shortcut wrapping them, keep it untracked.

(`intpot add skills` writing `.claude/skills/` into a *user's* project is the product, and
unrelated — it emits six formats and privileges none of them.)
