---
title: Schema and parameter reference
description: Reference for Intpot App, schema records, CLI operations, route metadata, defaults, async tools, and conversion errors.
---

Intpot's registered-app and conversion APIs meet through the normalized schema below; the shared flow is shown in the [architecture overview](/architecture-internals/).

<figure class="supporting-diagram">
  <a href="/intpot-flow.png?v=canonical-schema-2" target="_blank" rel="noopener"><img src="/intpot-flow.png?v=canonical-schema-2" alt="Two Intpot workflows meet at the canonical ApplicationSchema: registered Python tools are served or ejected as CLI, API, or MCP interfaces; existing Typer, FastAPI, or FastMCP apps are inspected and converted to standalone code." loading="lazy" /></a>
  <figcaption>How app registration and framework conversion converge. <a href="/intpot-flow.png?v=canonical-schema-2">Open the full-size diagram</a>.</figcaption>
</figure>

## `App`

`App(name: str = "intpot-app")` stores registered functions. `App.tool(*, name: str | None = None, description: str | None = None)` returns a decorator and registers the original function. The name defaults to the function name; the description defaults to its docstring (or the empty string). Names are normalized for generated interfaces while the declared interface name is retained.

Registration rejects variadic positional (`*args`) and keyword (`**kwargs`) parameters with `ValueError`; their shape cannot be consistently represented in CLI, HTTP, and MCP modes. Explicit parameters use evaluated annotations when available, annotation text otherwise, and fall back to `str` when none is declared. Return annotations are retained; missing annotations remain distinct from `-> None`.

`app.serve(mode, *, host="127.0.0.1", port=8000)` supports `cli`, `api`, and `mcp`. It raises `RuntimeError` when no tools are registered and `ValueError` for unknown modes. API serving uses Uvicorn and defaults to loopback. `app.eject(target)` supports `cli`, `api`, and `mcp`, returns source text, and raises `ValueError` for an unknown target. The generated source depends on its target framework, not on Intpot as a runtime.

## CLI operations

- `intpot serve SOURCE --cli|--api|--mcp [--host HOST] [--port PORT]`: exactly one mode is required. HTTP defaults to `127.0.0.1:8000`; host and port apply to API mode.
- `intpot inspect SOURCE [--json] [--verbose]`: inspect one source or discover a directory; JSON includes source path, source type, and serialized tools.
- `intpot eject SOURCE --to cli|api|mcp [--output PATH]`: eject an Intpot `App` to standalone source; without output it writes code to stdout.
- `intpot to cli|api|mcp SOURCE [--output PATH] [--verbose] [--dry-run]`: convert detected framework apps; output may be a file or directory. A same-target source is rejected.
- `intpot init` scaffolds a project; `intpot add skills` installs supported agent guidance. Run `intpot COMMAND --help` for the installed version's exact flags.

## `ApplicationSchema`

The frozen schema is the normalized boundary between inspection/registration and generation:

| Field | Meaning |
|---|---|
| `name` | Display/application name |
| `source_type` | `python`, `cli`, `api`, or `mcp` |
| `tools` | Immutable tuple of `ToolSchema` records |
| `source_path` | Resolved input path when compiled from a file |
| `target_type` | Target kind on a projected schema, otherwise absent |

`ApplicationSchema.from_tools(...)` compiles compatibility `ToolInfo` instances; `.to_tools()` returns detached mutable records; `.to_dict()` yields a JSON-compatible representation. `compile_app(source_type, app_instance, source_path=...)` compiles a live app. `load(path_or_instance)` detects a source and returns `IntpotApp`; its cached `.schema`, detached `.tools`, `.project(target)`, `.to_cli()`, `.to_api()`, `.to_mcp()`, and `.write(path, target)` provide the Python conversion API. Passing the same source target to `.project()` is rejected.



## Bounded definition provenance (v0.14.0)

**Availability:** requires v0.14.0 or newer; until v0.14.0 is published, use a
source checkout containing this change. v0.13.0 does not include captured definition
coordinates.

Inspected `ToolInfo` and immutable `ToolSchema` carry optional `source_location`
and `support_source_locations`. JSON locations have `path`, `line`, and `end_line`:
an absolute owning-file path and inclusive, 1-based definition bounds. The first
line is the `def`/`async def`, not its decorators. Helper locations are keyed by
recovered helper name. Schema adapters and projections preserve these snapshots.

Capture reads and compiles the owning file without executing it, then requires a
matching existing function code object. Where existing inspector recovery unwraps
a callable, provenance describes the recovered original, not wrapper execution.
Dynamic functions, closures and otherwise unverifiable callables have no captured
location. Missing, unreadable or
changed function bodies also yield no location. This is bounded code/definition
provenance at inspection time, not proof that annotations/default values or the
whole application are unchanged. Manually supplied schema metadata is caller-owned.

A diagnostic's top-level `source_location` identifies the affected tool definition,
including callback/dependency refusals; it does not locate the callback, dependency,
or exact missing-name occurrence. When provenance is available, binding references
also carry the originating implementation/helper definition location. Synthetic
public wrappers have `source_location: null`. Without provenance, reference shapes
remain compatible and top-level locations stay `null`. Cached schemas retain their
inspection snapshot; they do not continuously track filesystem edits.

Conversion policy, code-string return types, exception precedence and refusal
before writes are unchanged. Inspection still imports trusted source code and is
not a sandbox. Run `uv run --all-extras --with httpx python examples/source_provenance.py`
for source behavior, helper coordinates, Python/CLI report parity and refusal checks.

## Actionable binding context (v0.13.0)

**Availability:** requires v0.13.0 or newer; v0.12.0 does not include these
additive fields.

`loaded.assess()` and `intpot inspect app.py --json` expose `references`,
`suggested_action`, and `source_location` on `missing_binding`,
`missing_definition_binding`, and `missing_annotation_binding` diagnostics. Existing
codes, tool/target identity, names, messages and refusal exceptions remain unchanged.
Each reference pairs a missing `name` with its `generated_definition`, including owned
helpers and generated wrappers/implementations. These are emitted Python identifiers,
not original-source coordinates. References are sorted by generated definition then name.
Suggestions name the missing bindings; eager definition dependencies must exist before
those definitions, while body and deferred-annotation dependencies must exist before use.

In published v0.13.0, `source_location` is always `null` (`None` in Python).
v0.14.0 adds bounded definition provenance as described above; until publication,
use a source checkout containing this change.
An application `source_path` is not sufficient provenance, and no generated AST
position is presented as an original line. Diagnostics are observations of
bounded rendered-name checks, not a dependency graph or a proof of conversion readiness.
Scaffold permission cannot bypass refusal, and inspection still imports trusted code.

Run [the diagnostic-context example](https://github.com/tugrulguner/intpot/blob/main/examples/diagnostic_context.py)
from the source checkout. It checks the original API via TestClient, prints real JSON
context, and verifies that CLI/MCP refusal leaves output directories absent.

## `ToolSchema` and `ParameterSchema`

A tool includes `name`, `description`, `parameters`, `return_type`, `function_body`, `is_async`, HTTP `http_method` and `route_path`, operation ID/summary/description/tags/deprecation, dependency identifiers, source imports, and original interface name. Values may be absent when a framework does not provide them or the inspector cannot recover them.

A parameter includes its name, type annotation, default/required state, description, HTTP parameter source and placement, binding name, interface name, and aliases. The v0.10 `unsupported_callback` boolean records a source CLI parameter callback without storing the callable. It survives schema/compatibility adapters and equality/hash; JSON includes it only when true. API/MCP projection and generation refuse marked parameters with `intpot.UnsupportedCLIParameterCallbackError` rather than dropping validation or transformation. In FastAPI, supported route metadata is read from registered routes and carried into API output. `Depends` and `Security` dependencies are recorded for diagnostics, not executed or translated: API-to-CLI/MCP conversion rejects them, including nested, router-level, and application-level dependencies.

Schema immutability protects the compiled snapshot: nested parameter/tool collections and supported mutable defaults are detached/frozen. Compatibility objects returned by `.tools` are detached copies. A default the schema cannot safely preserve (for example, a locally defined Enum or unsupported object) can fail schema compilation rather than becoming misleading generated source.

## Runtime and generated behavior

At runtime, `App` retains the registered callable and metadata. The runtime builders create a Typer command app, FastAPI app, or FastMCP server. Async functions are recognized and routed through async-compatible builders; confirm the target framework's behavior by executing generated code. Parameter annotations and defaults drive the interface schema, but framework-specific validation and coercion can differ. An output file is inspectable source; generation does not carry arbitrary source framework lifecycle, middleware, dependencies, or configuration.

## Dependency extras

| Target | Install |
|---|---|
| Base and CLI | `pip install intpot` |
| FastAPI and Uvicorn | `pip install 'intpot[api]'` |
| FastMCP | `pip install 'intpot[mcp]'` |
| Both optional targets | `pip install 'intpot[all]'` |

Intpot requires Python 3.11 or newer. The current declared minimums are Typer 0.9.0, FastAPI 0.100.0, and FastMCP 2.0.0; actual resolved versions come from the package installer and should be tested in your environment.

## Related references

- [Build and run an Intpot app](/build-an-app/)
- [Convert, inspect, and eject applications](/conversion-boundaries/)
- [Architecture internals](/architecture-internals/)
- [CLI reference in README](https://github.com/tugrulguner/intpot#cli-reference)
- [Download this guide as Markdown](/downloads/schema-reference.md)

### Recovered support definitions (v0.11)

`ToolSchema.support_definitions` is an ordered immutable tuple of statically recovered helper/constant/import source; `ToolInfo` exposes a detached list. Serialization includes `support_definitions` only when nonempty. This is separate from the tool body and filtered source imports. Generators validate shared bindings before emitting support definitions and tools. See the bounded recovery limits in the conversion-boundaries reference.
