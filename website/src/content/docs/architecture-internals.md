---
title: Architecture internals
description: Follow Intpot's registration, detection, schema, projection, and code-generation data flow from the implementation.
---

Intpot has two entry paths that converge on normalized tool metadata and target generators: an Intpot `App` registration path and a framework-app conversion path. The schema is an internal/public Python data model; generated source is the output boundary.

## Define path: registration to live framework

`App.tool()` in `src/intpot/runtime.py` inspects the function signature and type hints, rejects `*args` and `**kwargs`, records a `ToolInfo`, and retains the original callable. `App.schema` compiles those records into an immutable `ApplicationSchema` snapshot. The live runtime path (`App.serve`) calls a target builder from `runtime_builders.py`: Typer for CLI, FastAPI for HTTP, and FastMCP for MCP. The builder binds actual registered callables; it does not reconstruct function behavior from source text.

The API server starts Uvicorn on the configured host and port. It defaults to `127.0.0.1`, so opting into `0.0.0.0` changes network exposure. CLI invocation dispatches through the generated Typer application. MCP starts FastMCP's server behavior. These are real execution paths—an `App` tool can perform any side effect its function performs.

## Conversion path: detect to generate

For a source file, `core/detector.py` checks syntax and looks for module-level framework constructor assignments, then imports the Python module and identifies the live FastAPI, Typer, or FastMCP object. Import executes module-level statements; detection is not a sandbox. The inspectors under `core/inspectors/` read each framework's exposed commands, routes, or tools into compatibility `ToolInfo` records.

`converter.compile_app()` compiles inspected values into immutable `ApplicationSchema`. `project_schema()` applies validation and transformations in `core/transforms.py` and `core/projections.py`: framework-specific parameter placement, aliases, and names are projected for the selected target. The target generator in `core/generators/` renders a Jinja template under `templates/*.j2`. CLI `intpot to ...` and Python `IntpotApp.to_*()` share this broad normalization/projection/generation pipeline; `App.eject()` uses the same target generators for Intpot-authored declarations.

## Why the schema is immutable

The frozen `ApplicationSchema`, `ToolSchema`, and `ParameterSchema` records provide a stable snapshot between inspecting mutable framework objects and rendering target code. They capture supported defaults, source annotations, callable body/imports where recoverable, async status, and API operation metadata. Compatibility models remain at inspector/generator edges for existing callers, but projection works from the canonical snapshot. This separation makes target transformations explicit and lets callers inspect a projected schema before writing code.

Defaults must be serializable as valid standalone Python literals and supported values. Schema compilation freezes known containers and rejects unsupported values instead of pretending their identity or semantics can be preserved. A generated body may not retain an arbitrary closure, global object, framework dependency, or runtime state; use source inspection and tests to find those gaps.

## Boundaries, errors, and side effects

- Importing a source can run arbitrary top-level code. Only convert code you trust; use an `if __name__ == "__main__":` guard for startup.
- FastAPI dependencies (`Depends`/`Security`), including nested and app/router-level dependencies, are refused for CLI/MCP targets. They are not plain input parameters.
- Unsupported optional packages produce actionable missing-extra errors when identifiable. Do not mistake a missing user module for a missing FastAPI dependency.
- A conversion can preserve recovered bodies, annotations, defaults, async markers, and supported route conventions, but not arbitrary middleware, hooks, authentication, exception handlers, or app configuration.
- Ejected code is independent of the Intpot runtime, but needs the selected target framework and must be reviewed, compiled, and executed.

## Test strategy for a generated application

Test the layers independently: schema assertions for normalized fields; projection assertions for target placement and refusal cases; generated-source compilation; then target-framework integration tests with a success input and malformed/invalid input. For HTTP, request the actual generated route and inspect OpenAPI. For CLI, invoke the generated command. For MCP, call the generated server through its supported client interface. Compare source and target outcomes while accounting for intentionally unsupported framework behavior. Do not infer live parity from source-string tests.

The repository's `make check` runs Ruff, Pyright, and pytest. `scripts/verify_generated_examples.py` exercises generated examples. Website preview examples are separately labeled browser-local; they demonstrate bounded interface parsing, not a network call to a live app. See [build guide](/build-an-app/) and [conversion boundaries](/conversion-boundaries/).

## Implementation map

- `src/intpot/runtime.py` — `App`, registration, live serving, ejection.
- `src/intpot/runtime_builders.py` — framework instances for registered tools.
- `src/intpot/core/models.py` — immutable schema and compatibility records.
- `src/intpot/core/detector.py` — import-based source detection and errors.
- `src/intpot/core/inspectors/` — framework-to-tool inspection.
- `src/intpot/core/projections.py` and `transforms.py` — normalized target semantics.
- `src/intpot/core/generators/` and `src/intpot/templates/` — generated source.
- `src/intpot/commands/` — public CLI wrappers for serve, inspect, eject, and conversion.

[Download this guide as Markdown](/downloads/architecture-internals.md).
