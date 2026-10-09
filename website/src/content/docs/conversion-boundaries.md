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

For converter calls (`intpot to ...`, `IntpotApp.project()`, and `to_cli()`/`to_api()`/`to_mcp()`), source recovery failure is distinct from a real no-op implementation. An unrecovered tool body remains visible in the inspectable schema and `app.assess()` reports `body_recovery_complete`, affected tool names under `missing_function_body`, and stable per-tool `diagnostics` (body recovery only, not general fidelity). JSON inspection adds an `assessment` when bodies are missing; public conversion refuses it before writing output. `--allow-scaffold` or `allow_scaffold=True` explicitly opts into a labeled `NotImplementedError` scaffold, never a successful dummy result. Direct low-level generators retain their historical behavior and do not perform converter assessment. This does not change live `App` or `eject` behavior. Callback and dependency safety refusals remain non-bypassable. See [the executable missing-body example](https://github.com/tugrulguner/intpot/blob/main/examples/missing_body.py).

## CLI parameter callbacks (v0.10)

Typer/Click parameter callbacks can reject or transform values before the command body runs. Intpot marks these parameters with `unsupported_callback=True`; JSON inspection includes the marker only when true. Assignment-style and `Annotated` options and arguments remain inspectable, including the registered-command fallback.

CLI-to-API/MCP projection and generation raise `intpot.UnsupportedCLIParameterCallbackError` with affected tool/parameter names and the requested target. The CLI exits with status 1, reports the refusal on stderr, and writes no output, including for directory conversion. Dry runs also refuse. This guard does not transpile callbacks or provide a general conversion assessment; the source CLI remains usable. See [the runnable callback example](https://github.com/tugrulguner/intpot/blob/main/examples/callback_cli.py).

## Validate output instead of trusting generation

Compile each output, then run it with its target framework and test the same inputs and failure cases as the source. Verify required and optional parameters, aliases, body/query/path placement, return encoding, async behavior, and any effectful behavior independently. For HTTP output inspect the generated OpenAPI document and exercise it through an HTTP client; for CLI invoke the generated command; for MCP use a FastMCP client. Generated source is ordinary editable Python, not a proof of behavioral parity.

## Next steps

See [schema and parameter reference](/schema-reference/), [architecture internals](/architecture-internals/), and the [source examples](https://github.com/tugrulguner/intpot/tree/main/examples). [Download this guide as Markdown](/downloads/conversion-boundaries.md).
