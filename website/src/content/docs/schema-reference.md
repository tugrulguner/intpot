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



## MCP-source numeric validation (unreleased)

`examples/inventory_reservation.py` is an MCP inventory reservation service with
bounded quantities and packs, defaults, a helper's stock-limit error and optional
receipts. Run `uv run --all-extras --with httpx python examples/mcp_application_conformance.py`
to compare its native MCP client with generated CLI and HTTP consumers. Required
quantity becomes a positional CLI argument; the HTTP adapter uses its projected route
and JSON request body. Valid calls write receipts; rejected inputs and stock-limit
failures do not. No mutable stock state or transaction semantics are claimed.

Ordinary primitive int/float inclusive finite Field/Annotated constraints retain the
existing minimum/maximum fields. Supported defaults embedded inside Annotated Field
metadata remain defaults, not required inputs. Constrained or validated None defaults
are explicitly refused. Numeric defaults are checked even without bounds: unsupported
strings, booleans, nonintegral integer defaults and nonfinite numbers refuse conversion
rather than changing omitted-input behavior. Additional numeric validators, exclusive/multiple-of/
strict constraints, unsupported defaults and factories are not silently discarded:
`unsupported_mcp_numeric_range` remains inspectable, assessment reports that code, and
`intpot.UnsupportedMCPNumericRangeError` refuses generation before writes, even with
scaffold permission. This is not general Pydantic, context, dependency, structured-model
or arbitrary MCP behavior conversion. Inputs are a documented shared numeric domain;
coercion, responses and errors remain framework-native. This capability is unreleased
and is not included in public v0.16.0.

## API-source numeric validation (unreleased)

The storage-cost service in `examples/storage_quote.py` is a second application-led
conformance case, with an HTTP API as its source. Run
`uv run --all-extras --with httpx python examples/api_application_conformance.py`.
It compares original HTTP, generated CLI and native MCP results, omitted defaults,
rejected/missing inputs, a helper's capacity error and receipts written only on success.

Ordinary primitive `int`/`float` FastAPI parameters retain finite inclusive `ge`/`le`
bounds in the existing `minimum`/`maximum` schema fields. Default-style and Annotated
Query/Body/Header/Path metadata use normalized FastAPI fields; ordinary required
parameters and supported defaults retain their existing interface placement.
Generated CLI/MCP adapters enforce their native bounds before the business body.

Exclusive bounds, multiple-of/strict/custom numeric validation, unknown validation
metadata and unsupported constrained defaults are not silently stripped. Inspection
retains `unsupported_api_numeric_range`; assessment reports that code per target, and
`intpot.UnsupportedAPINumericRangeError` refuses projection/generation before writing,
even with scaffold permission. Existing dependency/callback refusal precedence remains.
The marker is preserved through immutable schemas, adapters, hashes and detached JSON;
false is omitted. This is a bounded numeric contract, not general Pydantic model or
validator conversion. String constraints and arbitrary annotation metadata are not
certified; input coercion and error/response formats remain target-native. Public
v0.16.0 does not include this source capability. No package release is implied.

## Bounded numeric-range conversion (unreleased)

**Availability:** source checkout containing this change only; public v0.16.0 does not
provide this numeric-validation guarantee.

A Typer CLI can declare inclusive numeric bounds with `typer.Option(min=..., max=...)`
or `typer.Argument(min=..., max=...)`. The bounded conversion slice preserves ordinary
integer/floating types and finite inclusive bounds, including one-sided ranges, through
the canonical parameter schema and generated CLI, HTTP API and MCP interfaces. Generated
targets enforce their native validation before calling the retained business body.

Parameters append optional `minimum` and `maximum` bounds and an
`unsupported_numeric_range` marker. Absent bounds/false markers are omitted from JSON.
`unsupported_cli_numeric_range` assessment diagnostics explain refusals;
`intpot.UnsupportedCLINumericRangeError` preserves the Python exception boundary.

Clamping, exclusive endpoints, unsupported range shapes and non-native or out-of-range
defaults remain explicitly refused;
scaffold permission must not bypass that refusal. Custom callbacks remain unsupported.
This CLI-source capture is complemented by the separately documented API-source
inclusive-bound slice; general MCP/Pydantic constraint or arbitrary metadata recovery
is not certified. Native input coercion and transport/error
formats remain framework-specific. The conformance example compares a finite shared input
domain rather than claiming arbitrary Python equivalence.

Run `uv run --all-extras --with httpx python examples/application_conformance.py`.
It loads the real `examples/batch_quote.py` CLI, executes the source and generated CLI,
HTTP and MCP consumers, compares business totals and omitted defaults, checks rejected
inputs and business errors, and verifies receipts are written only after successful
validation. Public same-source conversion remains refused; the generated CLI check
uses the existing low-level schema renderer. The source now uses plain terminal numeric
`typer.echo(total)`: the unreleased CLI-to-MCP fix evaluates that expression once and
returns text matching the MCP `str` output schema. Plain numeric/text/None terminal echoes
are covered; API scalar result types are unchanged. This is not general terminal capture:
output options, binary streams, arbitrary explicit returns and all echo/control-flow
forms are not certified. The MCP client still validates results against the output schema.
This is executable application evidence, not a generated-text snapshot.

## Exact body-reference locations (v0.16.0)

**Availability:** requires v0.16.0 or newer. Until publication, use a source checkout
containing this change; v0.15.0 does not include
`references[*].reference_locations`, `source_digest` or `support_source_digests`.

Each binding reference adds `reference_locations`: a source-ordered list of original
identifier ranges, or `null` when exact attribution is unavailable. Each range has
`path`, `line`, `column`, `end_line` and `end_column`. Lines and Unicode character
columns are 1-based; the end position is exclusive. These are identifier occurrences,
not whole-definition bounds, runtime traces or proof that a branch executes.

The first slice maps only body-global name loads in a plain function body. Definition
headers, defaults, decorators, string/forward annotations, generated wrappers, nested
scopes (including comprehensions and lambdas), global/nonlocal rebinding and unmatched
transforms remain unavailable. Local variable annotations are not treated as executed
body loads. At most 64 occurrences per name are reported; exceeding that bound declines
the owner's occurrence mapping rather than returning a misleading partial list.

Inspected `ToolInfo`/immutable `ToolSchema` add optional `source_digest` and
`support_source_digests`. They contain lowercase SHA-256 fingerprints of decoded source
text encoded as UTF-8, captured from the same code-verified source used for definition
provenance. Helper mappings are detached/sorted immutable tuples in the canonical schema
and objects in JSON. Absent digest metadata is omitted from tool JSON.

Assessment rereads the owning file without executing it, requires the captured fingerprint
and definition bounds to match, and compares the complete retained body with both the
original body and an emitted suffix after generator argument guards. Docstrings are
excluded from that comparison. Missing, changed or unmatched source yields `null`.
Existing cached definition locations and dependency chains are unchanged. Schema-provided
metadata remains caller-owned, not authenticated provenance; an application path alone
never establishes an occurrence location.

Python `assess()` and CLI `inspect --json` carry the same ranges. No recovery or conversion
policy is broadened, no generated code is executed for assessment, and existing exception,
scaffold and before-write refusal behavior remains intact. Run the real-source example:
`uv run --all-extras --with httpx python examples/reference_locations.py`.

## Bounded binding chains (v0.15.0)

**Availability:** requires v0.15.0 or newer. Until v0.15.0 is published, use a source
checkout containing this change; v0.14.0 does not include
`references[*].dependency_chain`.

For `missing_binding`, `missing_definition_binding` and `missing_annotation_binding`,
each reference adds `dependency_chain`: one shortest list of emitted Python definition
names from the target's public wrapper to that reference's owning definition. The
missing binding remains `reference.name`, separate from the list. For example,
`["calc", "_calc_impl", "scale", "leaf"]` ends at the helper using the missing name.
Equal-length paths use lexically sorted edges, and cycles are visited once.

This is a static binding-reference explanation, not an execution trace, call graph,
proof of reachability, or evaluation-order guarantee. Edges use the existing scope-aware
body-global analysis and only that tool's emitted implementation, wrapper and retained
helpers. Local/parameter shadowing does not create a global helper edge. Global
rebinding or an unanalyzable owner makes its path unavailable; an unconnected helper
keeps `dependency_chain: null`. Attribute calls, dynamic dispatch, imports and arbitrary
alias/type/default evaluation are not resolved into additional edges.

Existing codes, missing names, suggestions, source-definition locations and ordering
remain intact. Generated wrapper origins remain unavailable. Paths add no recovery
capability, change no conversion policy and do not bypass before-write refusal or
scaffold restrictions. Python `assess()` and CLI `inspect --json` expose the same paths;
source-code output and string-returning conversion APIs are unchanged.

Run `uv run --all-extras --with httpx python examples/binding_chains.py` from the
source checkout. It executes an original helper-backed HTTP API and its generated CLI,
uses an explicitly caller-authored incomplete schema for the transitive missing-name
fixture, and separately checks real source-loading CLI/Python parity and refusal before
writes. Source inspection does not gain unresolved-helper recovery from that fixture.

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
