# intpot CLI

**intpot** does two things: it lets you define tools once and serve them as a Typer CLI,
FastAPI app, or FastMCP server, and it converts existing apps between those three
frameworks.

## When to Use

- The user wants one set of functions available as a CLI, an HTTP API, **and** an MCP
  server without maintaining three codebases — use `intpot.App`
- The user has an existing Typer / FastMCP / FastAPI app and wants it in another
  framework — use `intpot to ...`
- The user wants to see what intpot extracts from a file before converting — use
  `intpot inspect`
- The user wants a new project skeleton — use `intpot init`

Scaffold commands require a project name followed by `--type`:

```bash
intpot init my-project --type cli
intpot init my-project --type mcp
intpot init my-project --type api
```

## Write once, serve everywhere

Define tools with `@app.tool()` in a plain Python file:

```python
from intpot import App

app = App("my-app")

@app.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
```

Serve the same file in any mode:

```bash
intpot serve app.py --cli          # Typer CLI
intpot serve app.py --api          # FastAPI on 127.0.0.1:8000
intpot serve app.py --mcp          # FastMCP server
```

In `--cli` mode, arguments after the flags go to the app:

```bash
$ intpot serve app.py --cli add 2 3
5
```

Use `--` when the app defines a flag intpot also defines (`--host`, `--port`):

```bash
intpot serve app.py --cli -- mytool --port 5
```

Export the same app as standalone framework code, with no intpot dependency:

```bash
intpot eject app.py --to api       # or cli, mcp
intpot eject app.py --to cli --output cli_app.py
```

## Convert an existing app

```bash
intpot to cli server.py            # MCP or API source -> Typer CLI
intpot to mcp app.py               # CLI or API source -> FastMCP server
intpot to api app.py               # CLI or MCP source -> FastAPI app

intpot to cli server.py --output cli_app.py
intpot to cli ./myproject/         # every app in a directory
intpot to cli server.py --dry-run  # print output; do not write generated files
intpot to mcp app.py --verbose     # detection details on stderr
```

## Inspect without generating

```bash
intpot inspect server.py           # table of extracted tools
intpot inspect server.py --json    # canonical tool schema as JSON
```

Prefer `--json` when you need to reason about the result programmatically.

## Options

| Option | Applies to | Description |
|--------|-----------|-------------|
| `--output`, `-o` | `to *`, `eject` | Output path (prints to stdout if omitted) |
| `--dry-run` | `to *` | Preview generated code without writing files |
| `--allow-scaffold` | `to *` | Opt in to `NotImplementedError` stubs when source recovery fails |
| `--verbose`, `-v` | `to *`, `inspect` | Show detection details on stderr |
| `--json` | `inspect` | Emit JSON instead of a table |
| `--host` / `--port` | `serve --api` | Defaults `127.0.0.1` / `8000` |
| `--version`, `-V` | top level | Print the installed version |

## Things to know

- **Detection imports the source file.** `intpot to ...` and `intpot inspect` execute the
  module to find the app instance, so arbitrary module-level code still runs. `--dry-run`
  only prevents generated output files from being written; it is not a sandbox. Only
  convert source code you trust.
- **`serve --api` binds `127.0.0.1`.** Pass `--host 0.0.0.0` to expose it on the network.
  Code from `eject --to api` and `init --type api` binds loopback too; change the `host=`
  argument in the generated file to opt in.
- **`serve --api` reads arguments from a JSON body**, not the query string — the same
  shape `eject --to api` generates.
- **Converted code carries the original body over** where the frameworks agree, and
  rewrites it where they don't. A tool whose body can't be recovered gets a
  refusal by default; `--allow-scaffold` opts into a labeled failing implementation.

## Verify generated code

Successful generation does not prove that the generated program works. After every
conversion or eject:

1. **Compile** it with `python -m py_compile generated.py`.
2. **Import** the generated module in the environment where it will run.
3. **Invoke** real behavior: run a generated CLI command, issue a request with FastAPI's
   `TestClient`, or call a generated MCP tool. Checking text or `--help` alone is not a
   behavioral test.

Current unsupported or lossy cases include nested Typer sub-apps, repeatable CLI options,
some FastAPI `Annotated[..., Body(...)]` parameters, factory-created apps, and routes with
multiple HTTP methods. FastAPI `Depends()`, `Security()`, nested, and route/router/app-level
dependencies remain visible to `intpot inspect`, but API-to-CLI/MCP conversion refuses
them instead of emitting broken code; full mapping remains tracked in issue #20. A missing
recoverable body makes conversion refuse before output writes. `--allow-scaffold`
explicitly requests labeled `NotImplementedError` implementations, not working programs.
`inspect --json` adds an `assessment` with per-tool body-recovery diagnostics when missing.
This is not general fidelity assessment and never bypasses callback/dependency guards.

Typer/Click parameter callbacks remain inspectable as `unsupported_callback=True` on
parameter metadata (`to_dict()` includes the marker only when true). CLI-to-API/MCP
projection and generation raise `intpot.UnsupportedCLIParameterCallbackError`, naming
all affected tools/parameters and the target, rather than dropping callback validation or
transformation. Assignment-style and `Annotated` declarations are detected. The CLI
reports refusal on stderr with exit status 1 before writing output; `--dry-run` also
refuses. This is a focused known-loss guard, not a general conversion assessment or
callback transpiler. Source CLI behavior is unchanged.

intpot carries direct import statements referenced by a tool body. It does not yet copy
same-module helpers, constants, classes, models, or closure values. It does not discover
or install transitive dependencies across imported modules. Direct file loading does not
add the source directory to `sys.path`, so sibling imports may require installing the
package or setting `PYTHONPATH`. intpot does not reproduce configuration or provision
external services; verify those explicitly rather than assuming generated code is
standalone.

## Installation

```bash
pip install intpot            # core: init, inspect, add skills, Typer CLI output
pip install intpot[mcp]       # + FastMCP support
pip install intpot[api]       # + FastAPI support
pip install intpot[all]       # everything
```

Install `[mcp]` or `[api]` when intpot must inspect or load a source using that framework,
or when you serve, import, or invoke that target. Emitting source text alone does not
require the target extra, but verifying or running the emitted program does.

## Missing body bindings (v0.11)

Public conversion now raises `intpot.MissingBindingError` before output writes when a
retained implementation refers to globals absent from the generated target module.
`app.assess()` and conditional `intpot inspect --json` assessment include per-target
`missing_binding` diagnostics with `tool`, `target`, and sorted `names`. Existing
`body_recovery_complete` and `missing_function_body` fields retain their meaning:
recovering a body does not mean its dependencies are available.

Analysis reuses Python scope-aware binding analysis against statically rendered target
implementations, accounting for locals, nested scopes, comprehensions, retained imports,
builtins and generated self-recursion bindings. It renders but does not execute generated
code. Binding availability assumes a normally file-loaded Python module, including
loader-provided `__file__`, `__cached__`, and other standard module globals. Their values
belong to the generated file; this does not preserve the original path, resources, or
package environment. Custom `exec` namespaces must provide their own module globals.
Targets blocked by existing rendering guards report `reference_analysis_unavailable`
in assessment instead of implying a successful binding check. Inspection still imports
trusted source code and is not a sandbox.

This first slice checks retained body bindings, not complete annotations/defaults,
import availability, conditional binding initialization, runtime state, validation parity,
or arbitrary Python equivalence. Recovery of the bounded subset is described below. Callback and
FastAPI dependency refusal remain authoritative; `allow_scaffold=True` / `--allow-scaffold`
does not bypass missing-binding refusal. Live `App` serving/ejection and direct low-level
generator compatibility are unchanged. See `examples/missing_binding.py` for an original
helper-based implementation with a dynamically initialized dependency that returns 21 and is explicitly refused.

## Definition-evaluation binding diagnostics

**Availability:** requires v0.11.1 or a source checkout containing this change. Repository documentation can precede package publication.

Run `uv run --all-extras --with httpx python examples/definition_bindings.py` from a source checkout for a working original HTTP API whose MCP export reports the eager missing `Model` annotation and whose CLI export reports the v0.12.0 postponed-annotation diagnostic described below. Both refuse before output, even with scaffold opt-in. The consumer check requires `httpx`.

Public converter assessment also reports `missing_definition_binding` when generated
function decorators, defaults, or non-postponed annotation expressions refer to an absent
or later module binding. Diagnostics retain `tool`, `target`, sorted `names`, and an
actionable message; provide the required import/definition before the affected function,
or adapt the source to the supported subset. Checks include generated wrappers and the
ordered support functions owned by each tool, without executing generated code.

Projection, conversion, and writes raise `MissingBindingError` for these diagnostics,
including `--dry-run` and `--allow-scaffold`; mixed-directory conversion writes nothing.
Inspection remains available, and body-recovery fields still describe bodies only.

This is a bounded ordered binding check, not full annotation/default readiness. Later
framework resolution, called initializer behavior, arbitrary conditional initialization,
import availability, and Python equivalence are not certified. Lambda bodies and generator
bodies are deferred; comprehension locals are not module dependencies. Live `App` and direct
low-level generators are unchanged.

## Actionable binding context (unreleased source only)

The published v0.12.0 does not include these additional fields. In a source checkout
containing this change, the three missing-binding diagnostic codes expose `references`
(each missing `name` and its `generated_definition`), `suggested_action`, and
`source_location`. Generated names identify owned helpers, wrappers and implementations;
they are not source locations. `source_location` is currently always `None`/JSON `null`
because original callable/helper coordinates are not retained. Never infer them from
`source_path`. Existing codes, tool/target/names/message fields and refusal exceptions
stay unchanged. Suggestions distinguish eager before-definition ordering from body and
postponed-annotation availability before use. Inspection remains available; scaffold
permission does not bypass refusal. Run `examples/diagnostic_context.py` from source.

## String/postponed annotation bindings (v0.12.0)

**Availability:** requires v0.12.0 or newer. Older versions, including v0.11.1, do not
include `missing_annotation_binding`. Until v0.12.0 is available from your package index,
use a source checkout containing this change.

Public assessment reports `missing_annotation_binding` for missing global roots in parsed
string annotations and annotations postponed by an emitted future import. It checks the
actual generated implementations, wrappers and owned support functions against bindings
in the completed emitted module, not just those preceding a function. Names are sorted
and deduplicated per tool/target. Annotation-only declarations do not create bindings.
Projection and writes refuse before output, including dry-run and scaffold opt-in;
inspection and body-recovery fields remain unchanged.

Type-position strings are parsed inside nested quotes, unions and recognized builtin/typing
generics. Unknown/custom subscriptions and assignment aliases keep strings as values;
their type-argument semantics are not certified. Imported
`typing`/`typing_extensions` aliases for `Literal` and `Annotated` preserve value strings:
`Literal["red"]` and `Annotated[int, "label"]` do not invent type dependencies. Strings in
call arguments are values, not recursively parsed types. Analysis never evaluates the
annotation expression; source detection still imports trusted user code and is not a sandbox.

This is name availability, not type resolution, alias-value validation or class recovery.
Late framework registration/resolution, imported attributes, dynamic aliases, malformed or
excessively nested annotation syntax and arbitrary expression behavior remain uncertified.
An empty diagnostic list is not a guarantee that `get_type_hints()` or a framework succeeds.

## Bounded helper recovery (v0.11)

Converters recover required undecorated functions and immutable literal constants from
an inspected callable's owning module, including transitive helpers, ordinary imports,
and recursive helper calls. Ordered `support_definitions` is separate from
`source_imports`, immutable in `ToolSchema`, and detached in `ToolInfo` compatibility views.
Generated output remains ordinary framework Python with no intpot runtime bridge.

Recovery reads the actual callable's globals and source file, verifies helper code and
literal defaults against the live function, and rejects ambiguous or rebound bindings.
It does not copy unrelated startup statements or app registration. Mutable globals,
closures, decorated helpers, classes, dynamic defaults/global lookup, and helpers that
write global/nonlocal state remain outside the supported subset. Unsupported dependencies
still diagnose/refuse before writes; explicit scaffold permission does not bypass them.
Conflicting support bindings and collisions with generated public names are refused.
This is bounded source recovery, not purity analysis or arbitrary Python equivalence.
Live `App` serving/ejection is unchanged; recovery currently applies to existing framework
applications inspected by the CLI, API, and MCP inspectors.

Run `uv run python examples/helper_recovery.py` to exercise the helper chain returning 21
through generated CLI, HTTP API, and MCP consumers. `examples/missing_binding.py` retains
a refusal control using a dynamically initialized module value rather than a recoverable
literal. These capabilities are included in v0.11.0; the documented unsupported cases remain explicit.

## Callback and dependency refusal diagnostics (unreleased)

In source checkouts containing this change, `app.assess()` and `intpot inspect --json`
expose `unsupported_cli_parameter_callback` and `unsupported_fastapi_dependency`
diagnostics. Callback entries identify `tool`, `parameter`, and `target`; dependency
entries identify `tool`, `target`, normalized `dependencies`, and `route` context
(`path`, `operation_id`, `name`). Each refusal includes `source_location: null`,
`consequence`, `suggested_action`, and `reference_analysis: "skipped_due_to_refusal"`.
This status means target binding analysis was skipped, not that bindings are known good.
Consequences describe what would be lost without equivalent implementation; conversion
is refused. Scaffold permission cannot bypass these guards. FastAPI dependency
diagnostics apply only to API source schemas. This delivery is unreleased and
unavailable in published packages until release. See `examples/conversion_refusals.py`.
