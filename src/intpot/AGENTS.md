# AGENTS.md — `src/intpot/`

Rules for changing intpot source. The root `AGENTS.md` covers what intpot is, the
workflow, and keeping docs honest; this file covers the code itself.

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
body. `tests/test_runtime_builders.py` checks representative body-parameter parity, not
every Python signature shape. Extend the parity cases whenever the signature contract
changes rather than assuming that one case proves the whole interface.

**Annotations must describe what the body actually returns.** FastAPI validates the
response against the return annotation, so `-> dict` over a body returning an `int` is a
runtime 500, not a type-checker complaint.

**Detection executes user code.** `detect_source` imports the module. Anything that scans
many files must tolerate one of them raising — see `core/discovery.py`.

**Identify framework objects structurally, never with `isinstance`.** typer 0.26 vendored
its own copy of click as `typer._click`, so a Typer app stopped being an instance of
anything in the standalone `click` package. Every check written against click failed at
once: the inspector found zero tools in any Typer app, silently, for two and a half
months. Match on what an object *has* — a `commands` mapping, a type's `name` — the way
`detector.py` and `_is_depends` already do. The same applies to any framework we don't
control, which is all of them.

**Generated code must parse whatever the source contains.** Descriptions, parameter names
and project names all come from someone else's code. A quote or newline in a description
produced an unterminated string literal; two parameter names sanitising onto one
identifier produced a duplicate argument. Never hand-write quotes around interpolated
text — use the `repr` filter, which is Python's own literal writer. Tests must `compile()`
the output, not inspect it.

**A guard that can collect nothing must assert it found something.** The test asserting
every CLI flag appears in the README derives its cases by walking the command tree. When
that walk broke, the test quietly went from 22 assertions to 1 and kept reporting green —
worse than having no test, because it still looked like coverage. Any parametrised test
whose inputs come from introspection needs a floor on what discovery returns.

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
  `core/generators/_render.py`. An unknown filter raises `TemplateAssertionError` while
  loading the template.
- Path parameters in the API template must not get `= Path(...)`; FastAPI infers them
  from the route.
- Generated code carries its own imports — review the import block, not just the body.

**Transforms and return types** (`transforms.py`)

- The AST pass maps `typer.echo` ↔ `return` and `typer.Exit` ↔ `raise`. A new transform
  that breaks either direction breaks round-tripping.
- `_target_return_type` decides the annotation. CLI is always `None`.
- API annotations must describe every reachable path. Scalar returns are wrapped as
  `{"result": ...}`, but the presence of one `return` does not prove that a conditional
  body cannot fall through to `None`. Treating `dict` as unconditional is what made every
  generated FastAPI handler 500 before #56; ignoring fallthrough creates the same failure
  on only some requests.
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
