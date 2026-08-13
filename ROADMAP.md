# Roadmap

## v0.5 (current) — Write Once, Serve Everywhere

Define tools once with `@app.tool()` and serve them as a CLI, API, or MCP server, or
eject them to standalone framework code. The converter handles all six directions between
existing Typer, FastMCP, and FastAPI apps.

### Remaining polish

- [ ] Handle `Annotated[str, Body(...)]` style FastAPI parameters ([#1](https://github.com/tugrulguner/intpot/issues/1))
- [ ] Support Click groups / Typer sub-apps, i.e. nested command hierarchies ([#2](https://github.com/tugrulguner/intpot/issues/2))
- [ ] Preserve parameter descriptions through all conversion directions ([#3](https://github.com/tugrulguner/intpot/issues/3), [#9](https://github.com/tugrulguner/intpot/issues/9))
- [ ] `--all` mode for `intpot serve` — serve CLI, API, and MCP simultaneously ([#32](https://github.com/tugrulguner/intpot/issues/32))

## Already shipped

These were listed as v2 goals when this roadmap was first written, and landed earlier
than planned:

- **Basic body transforms** — `typer.echo(x)` becomes `return x` on the way to MCP/API
  and back again, and `raise typer.Exit(code)` becomes `raise RuntimeError(...)`. See
  `core/transforms.py`.
- **Return-type coercion for FastAPI** — a scalar return is wrapped as
  `{"result": ...}` so the generated handler matches the response model FastAPI validates
  against.
- **Round-trip fidelity tests** — `tests/test_roundtrip.py` covers all three pairings.
- **Direct import resolution** — imports referenced by a function body are carried into
  the generated file. Transitive dependencies are not yet followed.

## v2 — Full AST Transform Pipeline

v2 goes past the signature-level and single-call rewrites that exist today, into
transformations that need real understanding of what a function body does.

### Planned

- **Deep body transforms** ([#19](https://github.com/tugrulguner/intpot/issues/19)) —
  beyond the `typer.echo`/`typer.Exit` pairs already handled: request/response pattern
  adaptation, framework-specific context objects, streaming and background-task idioms
- **Dependency injection mapping** ([#20](https://github.com/tugrulguner/intpot/issues/20)) —
  FastAPI `Depends()` is currently recorded as a comment in the generated file; v2 should
  convert it into the target's equivalent, such as a context manager or setup/teardown
- **Pydantic model parameters** ([#17](https://github.com/tugrulguner/intpot/issues/17)) —
  expand a model argument into individual CLI/MCP parameters instead of treating it as one
  opaque value
- **Transitive import resolution** — follow what the body's own dependencies need, not
  just the names it mentions directly
- **Full error-handling conversion** — Typer exits are mapped today; HTTP exceptions and
  MCP error patterns are not

### Non-goals for v2

- Runtime interop / adapter layer (intpot is a code generator, not a runtime bridge)
- Supporting frameworks beyond Typer, FastMCP, and FastAPI

---

Every item above is tracked as an issue. If something here interests you,
[CONTRIBUTING.md](CONTRIBUTING.md) has the setup and
[good first issues](https://github.com/tugrulguner/intpot/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are a gentler place to start.
