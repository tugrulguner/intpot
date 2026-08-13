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

## Reviewing a change

The rules above came from bugs that shipped — check those first. Beyond them, these are
the contracts a change has to keep.

**Architecture**

- Inspectors subclass `BaseInspector` and return `list[ToolInfo]` from `inspect()`;
  generators subclass `BaseGenerator` and return `str` from `generate()`.
- `to cli` / `to mcp` / `to api` all delegate to `commands/_convert.py`'s `convert()`.
  A conversion command that reimplements it will drift from the other two.
- Commands take `typer.Argument` / `typer.Option` parameters and return `None`.
- Shared models belong in `core/models.py`, not beside their first consumer.

**ToolInfo / ParameterInfo**

- A required parameter is one whose `default is _SENTINEL`. Outside `core/`, use the
  `.required` property rather than comparing against the sentinel.
- `name` on both dataclasses has already been through `sanitize_identifier()` — don't
  sanitize it again.
- These two dataclasses are the seam between both halves of intpot. A field added here
  ripples through every inspector, generator, and transform.

**Templates**

- The custom Jinja filters are `repr`, `pascal`, and `escape_doc`, registered in
  `core/generators/_render.py`. A template that reaches for any other filter renders
  blank.
- Path parameters in the API template must not get `= Path(...)`; FastAPI infers them
  from the route.
- Generated code carries its own imports — review the import block, not just the body.

**Transforms and return types** (`transforms.py`)

- The AST pass maps `typer.echo` ↔ `return` and `typer.Exit` ↔ `raise`. A new transform
  that breaks either direction breaks round-tripping.
- `_target_return_type` decides the annotation. CLI is always `None`.
- API is `dict` when the body returns something — a scalar return gets wrapped as
  `{"result": ...}` — and `None` when the body has no top-level return. Neither is
  unconditional. Treating `dict` as unconditional is what made every generated FastAPI
  handler 500 before #56.
- MCP keeps the source annotation, except from CLI, where it becomes `str`.

**Errors**

- `detect_source()` raises `DetectionError`. Commands catch it and exit through
  `typer.Exit(1)` with a message on stderr — never a traceback.
- `discover_sources()` stays quiet about files that simply aren't apps (verbose only),
  but always reports an import failure to stderr. A scan has to survive one bad file
  without going silent about it (#59).

**Tests**

- Use the `tmp_source` fixture from `conftest.py`; CLI tests use `typer.testing.CliRunner`.
- Assert on behaviour, not on `exit_code == 0`.
- Name them `test_<scenario>` or `test_<framework>_<scenario>`; assert on raised errors
  with `pytest.raises(ErrorClass, match="...")`.

**Style**

- Every file opens with `from __future__ import annotations`.
- Ruff owns formatting (88 columns, double quotes, isort with intpot first-party) —
  don't review it. B008 is suppressed deliberately, so
  `typer.Option()` and `typer.Argument()` as defaults are correct.
- Don't ask for docstrings, annotations, or abstractions on code the change didn't touch.

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
