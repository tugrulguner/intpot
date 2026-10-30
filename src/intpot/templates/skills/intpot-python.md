# intpot Python API

**intpot** exposes two APIs: `intpot.App` for defining tools once and serving them as a
CLI, API, or MCP server, and `intpot.load()` for converting existing framework code
programmatically.

## When to Use

- Define tools once and serve or export them in any framework — `App`
- Convert apps inside scripts, build tools, or CI — `load()`
- Inspect an app as stable framework-neutral data — `.schema`
- Generate from a live app instance rather than a file — `load(instance)`

## `intpot.App` — write once, serve everywhere

```python
from intpot import App

app = App("my-app")

@app.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
```

The tool's name and description default to the function name and its docstring. Override
either — useful when the docstring explains the code to a maintainer but an agent needs
different wording:

```python
@app.tool(name="lookup", description="Look up a customer by account number.")
def fetch_customer_record(account_id: str) -> dict:
    """Hit the accounts table. Caller must have validated account_id."""
    ...
```

`async def` tools work in every mode. Variadic tool signatures using `*args` or `**kwargs`
are rejected because they cannot expose one consistent CLI, API, and MCP interface; use
explicit named parameters instead.

### Serving and exporting

```python
app.serve(mode="cli")                     # run as a Typer CLI
app.serve(mode="api", port=8000)          # FastAPI on 127.0.0.1 by default
app.serve(mode="api", host="0.0.0.0")     # opt in to network exposure
app.serve(mode="mcp")                     # FastMCP server

cli_code = app.eject("cli")               # standalone source, as a string
api_code = app.eject("api")
mcp_code = app.eject("mcp")
```

`serve(mode="api")` and `eject("api")` expose the same HTTP interface: arguments come
from a JSON request body.

## `intpot.load(source)` — convert existing code

Accepts a file path or a live app instance; returns an `IntpotApp`.

```python
import intpot

app = intpot.load("mcp_server.py")

from fastmcp import FastMCP
mcp = FastMCP("my-server")

@mcp.tool()
def greet(name: str) -> str:
    return f"Hello, {name}!"

app = intpot.load(mcp)
```

`load()` executes the file to find the app instance — treat unfamiliar sources with the
same caution as `exec`.

### `IntpotApp`

```python
app = intpot.load("server.py")

cli_code = app.to_cli()                   # generated source, as a string
mcp_code = app.to_mcp()
api_code = app.to_api()

app.write("output/cli_app.py", "cli")     # generate and write, returns the Path

print(app.source_type)                    # SourceType.MCP / CLI / API
print(app.schema.to_dict())               # inspect canonical source semantics
api_schema = app.project("api")           # inspect target semantics before generation
```

Calling `to_cli()` on a source that is already a CLI raises `ValueError`; same for the
other two.

Generated strings still need runtime verification. Successful generation does not prove
the result works: compile it, import it with its runtime dependencies installed, then
invoke a real CLI command, API request, or MCP tool.

Current unsupported or lossy conversions include nested Typer sub-apps, repeatable CLI
options, some FastAPI `Annotated[..., Body(...)]` parameters, factory-created apps, and
routes with multiple HTTP methods. FastAPI `Depends()`, `Security()`, nested, and
route/router/app-level dependencies remain available through `.tools` and `inspect_app`,
but `.to_cli()`, `.to_mcp()`, and `.write()` raise
`intpot.UnsupportedFastAPIDependencyError` rather than emit broken code. Full dependency
mapping remains tracked in issue #20. A body that cannot be recovered becomes a
missing implementation; conversion raises `intpot.MissingFunctionBodyError` before output
writes. Use `allow_scaffold=True` only to generate explicitly unimplemented scaffolds.

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
external services.

## Canonical application schema

Both `intpot.App` and `IntpotApp` expose `.schema`, an immutable
`ApplicationSchema`. It contains immutable `ToolSchema` and `ParameterSchema` records;
`.project("cli" | "mcp" | "api")` returns the exact target semantics used for
generation without mutating the source snapshot. `.to_dict()` provides a sentinel-free,
JSON-compatible representation for inspection. Non-JSON-native defaults use unambiguous
`{"$intpot": {"type": ...}}` envelopes. Enum and opaque defaults, plus temporal defaults
with timezone or `fold` semantics, are rejected rather than exposed through the frozen
schema.

```python
schema = app.schema
print(schema.name, schema.source_type, schema.target_type)
print(schema.to_dict())

for tool in schema.tools:
    print(tool.name, tool.description, tool.return_type, tool.is_async)
    for param in tool.parameters:
        print(param.name, param.type_annotation, param.required)
```

`.tools` remains available for compatibility and returns copied mutable `ToolInfo`
metadata. Copyable defaults are detached; opaque defaults that Python cannot copy remain
available by identity, so mutating such a default can mutate runtime state. Canonical
generation still rejects those opaque values through `.schema`.

```python
for tool in app.tools:
    print(tool.name, tool.description, tool.return_type, tool.is_async)
    for param in tool.parameters:
        print(f"  {param.name}: {param.type_annotation}")
        print(f"    required={param.required} default={param.default}")
```

`ToolInfo` fields: `name`, `description`, `parameters`, `return_type`, `http_method`,
`function_body`, `is_async`, `route_path`, `dependencies`, `source_imports`,
`interface_name`, `operation_id`, `route_summary`, `route_description`, `route_tags`,
`route_deprecated`, `support_definitions`, `source_location`, `support_source_locations`,
`source_digest`, `support_source_digests`. `name` is a Python-safe binding; `interface_name` preserves an explicit
framework-visible spelling such as `send-email` when it differs.

`ParameterInfo` fields: `name`, `type_annotation`, `default`, `description`,
`param_source`, `placement`, `binding_name`, `interface_name`, `aliases`,
`unsupported_callback`, `minimum`, `maximum`, `unsupported_numeric_range`, plus a
`required` property. `binding_name` preserves a source callable's valid Python parameter
spelling when canonical sanitization changes it. `interface_name` is the primary
framework-visible parameter spelling; `aliases` retains exact additional Typer/Click
option declarations such as `--customer-id` and `-c`. `placement` is the explicit target
location selected by a projection (`cli_argument`, `cli_option`, `api_body`, `api_query`,
`api_header`, `api_path`, or `mcp_parameter`); source inspection may leave it as `None`.
**The type field is `type_annotation`, not `annotation`.** `default` is a private sentinel
when the parameter is required — check `param.required` rather than comparing against
`None`.

`unsupported_callback` records a source CLI parameter callback as a boolean, never the
callable itself. It survives immutable schema and detached compatibility round trips;
API/MCP generation refuses it. This does not add callback support to `App.tool()`.

`param_source` is `ParamSource.query` / `header` / `path` / `body` for FastAPI sources
that declared one, otherwise `None`.

### `intpot.inspect_app(source_type, app_instance)`

Low-level: extract `ToolInfo` from a live instance without wrapping it.

```python
from intpot import SourceType, inspect_app

tools = inspect_app(SourceType.MCP, mcp_instance)
```

## Installation

```bash
pip install intpot[all]   # install both framework runtimes
```

Install `[mcp]` or `[api]` when intpot must inspect or load a source using that framework,
or when you import, serve, or invoke that target. Emitting source text alone does not
require the target extra, but verifying or running the emitted program does.


### Missing implementation source

`app.assess()` returns `body_recovery_complete`, `missing_function_body`, and per-tool
`diagnostics` as JSON-compatible data while keeping `app.schema` inspectable. The
body-recovery fields do not imply general conversion readiness. `.project()`, `.to_cli()`,
`.to_api()`, `.to_mcp()`, and `.write()` raise `intpot.MissingFunctionBodyError` by default.
Explicit `allow_scaffold=True` emits labeled `NotImplementedError` implementations and
does not override callback/dependency guards. Low-level generators retain legacy scaffold
behavior; live `App` behavior is unchanged.

`ToolSchema.support_definitions` (and mutable `ToolInfo.support_definitions`) carries ordered recovered source definitions; it is separate from `source_imports`.

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
This initial capture capability is for CLI source ranges, not general recovery of API/MCP
constraints or arbitrary annotation metadata. Native input coercion and transport/error
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

Requires v0.13.0 or newer. v0.12.0 does not include these additional fields. The three missing-binding
diagnostic codes expose `references`
(each missing `name` and its `generated_definition`), `suggested_action`, and
`source_location`. Generated names identify owned helpers, wrappers and implementations;
they are not source locations. Published v0.13.0 uses `None`/JSON `null`; v0.14.0
adds bounded definition provenance (until publication, use its source checkout). Never
infer original coordinates from `source_path`. Existing codes, tool/target/names/message fields and refusal exceptions
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

## Callback and dependency refusal diagnostics (v0.13.0)

Requires v0.13.0 or newer. `app.assess()` and `intpot inspect --json`
expose `unsupported_cli_parameter_callback` and `unsupported_fastapi_dependency`
diagnostics. Callback entries identify `tool`, `parameter`, and `target`; dependency
entries identify `tool`, `target`, normalized `dependencies`, and `route` context
(`path`, `operation_id`, `name`). Each refusal includes `source_location: null`,
`consequence`, `suggested_action`, and `reference_analysis: "skipped_due_to_refusal"`.
This status means target binding analysis was skipped, not that bindings are known good.
Consequences describe what would be lost without equivalent implementation; conversion
is refused. Scaffold permission cannot bypass these guards. FastAPI dependency
diagnostics apply only to API source schemas. See `examples/conversion_refusals.py`.
