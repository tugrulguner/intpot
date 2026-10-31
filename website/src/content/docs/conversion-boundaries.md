---
title: Convert, inspect, and eject applications
description: How Intpot loads Typer, FastAPI, and FastMCP apps, projects their schema, and where conversion refuses unsafe mappings.
---

Intpot's converter is a source-code importer and generator, not a general-purpose framework migration engine. This guide describes the current import, inspection, projection, and generation path and the boundaries callers must test.

## Supported source and target mapping

The framework inputs are Typer (`cli`), FastAPI (`api`), and FastMCP (`mcp`). Each can convert to the other two; converting a source to itself is rejected. Intpot-authored apps use the separate `App` runtime path: `serve` and `eject` accept an Intpot `App`, while `intpot to ...` converts detected Typer/FastAPI/FastMCP sources.

| Source | CLI target | HTTP API target | MCP target |
|---|---|---|---|
| Typer | already CLI; rejected | `intpot to api` | `intpot to mcp` |
| FastAPI | `intpot to cli` | already API; rejected | `intpot to mcp` |
| FastMCP | `intpot to cli` | `intpot to api` | already MCP; rejected |

For example, starting with a FastAPI source file:

```sh
intpot inspect existing_api.py --json
intpot to cli existing_api.py --dry-run
intpot to cli existing_api.py --output generated_cli.py
```

`--dry-run` prints the generated source without writing it. `--output` accepts a file for one source or a directory for a source tree. Directory conversions discover sources and preserve subdirectories in destination paths; dry runs report planned paths. Inspect JSON before generation when you need to review the normalized parameter and route metadata.

## What loading does

For a file, detection first parses Python syntax and checks for a module-level `FastAPI()`, `Typer()`, or `FastMCP()` assignment. It then imports that file to identify the live app instance and inspect framework routes/commands/tools. Import-time code therefore executes. Detection does not sandbox source, and it does not add the source file's directory to `sys.path`; guard executable startup with `if __name__ == "__main__":` and avoid side effects during import.

`intpot inspect path.py` displays normalized operations without generating code; `--json` emits structured data, and `--verbose` prints detection details to stderr. A directory may be inspected recursively. Malformed Python, failed imports, and missing app definitions are errors, not silently skipped files.

## Canonical schema and projection

Inspected and registered tool metadata is compiled into immutable `ApplicationSchema`, containing a source kind, app name, optional source path/target kind, and a tuple of `ToolSchema` records. A tool records its name and description, parameters, return annotation, function body/imports where recoverable, async marker, and API method/path/operation metadata. Each parameter records type, required/default state, API source/placement, aliases, and interface-specific naming. Compatibility APIs return detached mutable `ToolInfo` objects at the edges; generators consume schema projections.

The source-to-target transform adjusts parameter placement, names, and aliases before the target generator renders Python. For instance, FastAPI path/query/body inputs cannot all become an equivalent CLI option or MCP argument: the transformer records the source semantics and only maps shapes it supports. Do not treat two schemas with similar field names as proof of equivalent validation or wire behavior—test the generated target itself.

## Explicit tool selection (unreleased)

`selected = app.select("mapping")` creates an independent conversion view after
inspection. Names are exact canonical `ToolSchema.name` values shown by schema/JSON
inspection, not interface aliases or patterns. Empty, duplicate and unknown names fail.
Selected tools retain source order and all normal guards; the original wrapper and
framework application are unchanged. Selection cannot fix an uninspectable source.

```python
import intpot
app = intpot.load("existing_cli.py")
app.select("mapping").write("mapping_api.py", "api")
```

```sh
intpot to api existing_cli.py --tool mapping -o mapping_api.py
intpot to mcp existing_cli.py --tool mapping -o mapping_mcp.py
```

Repeat `--tool NAME` for several tools. Directory conversion requires every requested
name in every source and refuses before any writes when a source lacks one. This does
not remove parameters from selected tools or bypass their callbacks/dependencies.
Group callbacks and application lifecycle/configuration remain separate fidelity limits.

The [csv2vcard case study](https://github.com/tugrulguner/intpot/blob/main/examples/external-applications/csv2vcard.md)
compares an unchanged CLI mapping command with generated real HTTP and MCP clients.
The full application's parameter callback remains refused. Referenced absolute imports
under module-level if/try branches may be retained when their live binding matches an
already-loaded module export by identity, without evaluating conditions or importing
candidate modules. Unmatched conditional bindings remain refused; this is not a promise
of equivalent module startup or arbitrary dynamic import recovery.

## Preservation and explicit rejection

Intpot preserves only semantics it can recover from the supported app shape: callable names, parameter annotations/defaults, descriptions, recoverable source bodies/imports, async definitions, and supported framework conventions. For FastAPI-to-CLI or FastAPI-to-MCP conversion, `Depends`/`Security` parameters, nested dependencies, and route-, router-, or app-level dependencies are explicitly rejected with `UnsupportedFastAPIDependencyError`; they cannot be safely replaced with ordinary arguments. Arbitrary middleware, startup/shutdown hooks, custom exception handlers, authentication, state, and framework configuration are not a promise of conversion equivalence.

The importer executes module top-level statements. It can import a file with an unavailable optional framework only after the corresponding extra is installed. A missing FastAPI/Uvicorn module points to `intpot[api]`; missing FastMCP points to `intpot[mcp]`. An unrelated missing sibling module is not repaired by installing a framework extra.

## Missing implementation source (v0.10)

For converter calls (`intpot to ...`, `IntpotApp.project()`, and `to_cli()`/`to_api()`/`to_mcp()`), source recovery failure is distinct from a real no-op implementation. An unrecovered tool body remains visible in the inspectable schema and `app.assess()` reports `body_recovery_complete`, affected tool names under `missing_function_body`, and stable per-tool `diagnostics` (the v0.10 assessment checks body recovery, not general fidelity; the v0.11 binding extension is described below). JSON inspection adds an `assessment` when diagnostics are present; public conversion refuses it before writing output. `--allow-scaffold` or `allow_scaffold=True` explicitly opts into a labeled `NotImplementedError` scaffold, never a successful dummy result. Direct low-level generators retain their historical behavior and do not perform converter assessment. This does not change live `App` or `eject` behavior. Callback and dependency safety refusals remain non-bypassable. See [the executable missing-body example](https://github.com/tugrulguner/intpot/blob/main/examples/missing_body.py).

## CLI parameter callbacks (v0.10)

Typer/Click parameter callbacks can reject or transform values before the command body runs. Intpot marks these parameters with `unsupported_callback=True`; JSON inspection includes the marker only when true. Assignment-style and `Annotated` options and arguments remain inspectable, including the registered-command fallback.

CLI-to-API/MCP projection and generation raise `intpot.UnsupportedCLIParameterCallbackError` with affected tool/parameter names and the requested target. The CLI exits with status 1, reports the refusal on stderr, and writes no output, including for directory conversion. Dry runs also refuse. This guard does not transpile callbacks or provide a general conversion assessment; the source CLI remains usable. See [the runnable callback example](https://github.com/tugrulguner/intpot/blob/main/examples/callback_cli.py).

## Validate output instead of trusting generation

Compile each output, then run it with its target framework and test the same inputs and failure cases as the source. Verify required and optional parameters, aliases, body/query/path placement, return encoding, async behavior, and any effectful behavior independently. For HTTP output inspect the generated OpenAPI document and exercise it through an HTTP client; for CLI invoke the generated command; for MCP use a FastMCP client. Generated source is ordinary editable Python, not a proof of behavioral parity.

## Next steps

See [schema and parameter reference](/schema-reference/), [architecture internals](/architecture-internals/), and the [source examples](https://github.com/tugrulguner/intpot/tree/main/examples). [Download this guide as Markdown](/downloads/conversion-boundaries.md).

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
generator compatibility are unchanged. See [the runnable missing-binding example](https://github.com/tugrulguner/intpot/blob/main/examples/missing_binding.py) for an original
helper-based implementation with a dynamically initialized dependency that returns 21 and is explicitly refused.

## Conversion assessment before output

<figure class="supporting-diagram">
  <a href="/intpot-assessment.png" target="_blank" rel="noopener"><img src="/intpot-assessment.png" alt="Intpot inspects an application, checks bindings per target, and either generates supported standalone code or reports a missing name before any output writes." width="2000" height="1380" loading="lazy" /></a>
  <figcaption>Conceptual converter flow. Inspection remains available; scaffold permission cannot bypass missing-binding refusal. <a href="/intpot-assessment.png">Open the full-size assessment diagram</a>.</figcaption>
</figure>

The original HTTP API can work while the generated CLI lacks its `Model` annotation binding. The diagram illustrates that supported refusal case, not full conversion readiness or Python equivalence. Source inspection imports trusted code; this is not a sandbox. Live `App` and direct low-level generators are separate paths.



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

## Definition-binding diagnostics (v0.11.1)

**Availability:** requires v0.11.1 or a source checkout containing this change. Repository documentation can precede package publication.

Public conversion reports `missing_definition_binding` when generated function decorators,
defaults, or non-postponed annotation expressions refer to an absent or later module binding.
Diagnostics identify `tool`, `target`, sorted `names`, and an actionable message. The check
includes generated implementations, public wrappers, and ordered support functions without
executing generated code.

Projection, conversion, and writes raise `intpot.MissingBindingError` before any output
is created, including `--dry-run` and `--allow-scaffold`. Inspection remains available;
body-recovery fields still describe bodies only.

Run `uv run --all-extras --with httpx python examples/definition_bindings.py` from a source
checkout. The [runnable example](https://github.com/tugrulguner/intpot/blob/main/examples/definition_bindings.py)
requests a working original HTTP API and inspects its eager missing `Model` annotation in
the MCP target plus the v0.12.0 postponed CLI diagnostic described below. It proves both
refusals create no output directory, with and without scaffold opt-in.

This is a bounded ordered binding check, not full annotation/default readiness. Later
framework resolution, called initializer behavior, arbitrary conditional initialization,
import availability, and Python equivalence are not certified. Lambda bodies and generator
bodies are deferred; comprehension locals are not module dependencies. Live `App` and direct
low-level generators are unchanged.

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
