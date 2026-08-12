# AGENTS.md

Guidance for coding agents working **on intpot**. If you want intpot's skills for your
*own* project instead, run `intpot add skills`.

## What intpot is

Two halves that meet at one schema:

- **Runtime** — `@app.tool()` registers a function; `App.serve()` builds a live Typer /
  FastAPI / FastMCP instance, `App.eject()` writes standalone source.
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

## Rules that come from real bugs

**Tests must execute generated code.** Every generator test used to assert on the
generated *string*. Four separate bugs shipped that way — FastAPI handlers that returned
500 on every request, Typer commands that printed nothing — because the output looked
correct as text. `exec` the module and issue a real request or invoke a real command.

**A change to one template probably belongs in the other two.** The CLI and API templates
once hardcoded return annotations while the MCP one used the real type; that asymmetry
was the bug. When you touch `templates/*.j2`, check the sibling templates.

**`serve` and `eject` must expose the same interface.** They are the same app in two
forms. They once disagreed about whether parameters came from the query string or the
body. `tests/test_runtime_builders.py` asserts they match — keep that passing.

**Annotations must describe what the body actually returns.** FastAPI validates the
response against the return annotation, so `-> dict` over a body returning an `int` is a
runtime 500, not a type-checker complaint.

**Detection executes user code.** `detect_source` imports the module. Anything that scans
many files must tolerate one of them raising — see `core/discovery.py`.

## Workflow

```bash
uv sync --all-extras     # never install globally; never use bare pip
make check               # ruff + pyright + pytest — must pass before a PR
```

Run Python through `.venv/bin/python` or `uv run`.

**Every PR needs a changelog fragment**: one file at `changelog.d/<pr-number>.<type>.md`
where type is `added`, `changed`, `deprecated`, `removed`, or `fixed`. Write one sentence
about what changed *for a user*, not what you did to the code. CI fails without it; a
maintainer applies the `skip-changelog` label for refactors and CI-only work. Never edit
`CHANGELOG.md` by hand — it is assembled at release time. See `changelog.d/README.md`.

**Never hand-edit the version.** It lives only in `pyproject.toml`; `uv version 0.5.1`
updates it and the lockfile together. `__version__` reads it back through
`importlib.metadata`.

**Do not commit** conflict copies (`file 2.py`), `.venv`, or `.claude/settings.local.json`.
Stage explicit paths rather than `git add -A`.

## When you change the public API

`src/intpot/templates/skills/*.md` are installed into users' projects and read by their
agents. They went five months describing an API that no longer existed.
`tests/test_skills_content.py` guards the obvious cases; update the skills in the same PR
as the API change.
