# Roadmap

## v0.4 (current) — Write Once, Serve Everywhere

intpot v0.4 adds the `App` runtime framework: define tools once with `@app.tool()` and serve them as CLI, API, or MCP server with a single command. Eject to standalone framework code at any time.

### Remaining polish

- [ ] Handle `Annotated[str, Body(...)]` style FastAPI parameters
- [ ] Support Click groups / Typer sub-apps (nested command hierarchies)
- [ ] Preserve parameter descriptions through all conversion directions
- [ ] `--all` mode for `intpot serve` — serve CLI, API, and MCP simultaneously

## v2 — Full AST Transform Pipeline

v2 will introduce a proper AST-based transformation stage that rewrites function bodies between frameworks, not just signatures.

### Planned features

- **Deep body transforms** — rewrite framework-specific calls in function bodies (e.g. `typer.echo()` → `return`, `raise typer.Exit()` → `raise RuntimeError()`, request/response pattern adaption)
- **Import graph resolution** — full analysis of what the function body actually needs, including transitive imports and third-party dependencies
- **Dependency injection mapping** — convert FastAPI `Depends()` into equivalent patterns in CLI/MCP (e.g. setup/teardown, context managers)
- **Error handling conversion** — map between `typer.Exit`/`typer.Abort`, HTTP exceptions, and MCP error patterns
- **Type coercion layer** — automatically adapt return types and serialization between frameworks (dicts ↔ strings ↔ Pydantic models)
- **Round-trip fidelity tests** — verify that `A → B → A` produces functionally equivalent code

### Non-goals for v2

- Runtime interop / adapter layer (intpot is a code generator, not a runtime bridge)
- Supporting frameworks beyond Typer, FastMCP, and FastAPI
