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

## Actionable binding context (unreleased)

**Availability:** source checkout containing this change only; these additive fields are
not included in the published v0.12.0 package.

`loaded.assess()` and `intpot inspect app.py --json` expose `references`,
`suggested_action`, and `source_location` on `missing_binding`,
`missing_definition_binding`, and `missing_annotation_binding` diagnostics. Existing
codes, tool/target identity, names, messages and refusal exceptions remain unchanged.
Each reference pairs a missing `name` with its `generated_definition`, including owned
helpers and generated wrappers/implementations. These are emitted Python identifiers,
not original-source coordinates. References are sorted by generated definition then name.
Suggestions name the missing bindings; eager definition dependencies must exist before
those definitions, while body and deferred-annotation dependencies must exist before use.

`source_location` is currently always `null` (`None` in Python): this schema does not
retain verified original callable/helper coordinates. An application `source_path` is
not sufficient provenance. No generated AST position is presented as an original line.
Source-location capture remains separate future work. Diagnostics are observations of
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
