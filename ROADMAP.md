# Roadmap

## v0.7 (current) — Write Once, Serve Everywhere

Define tools once with `@app.tool()` and serve them as a CLI, API, or MCP server, or
eject them to standalone framework code. The converter handles all six directions between
existing Typer, FastMCP, and FastAPI apps.

### Conversion correctness

- [ ] Carry the complete dependency closure within one source module: referenced helper
      functions, constants, classes, models, defaults, decorators, annotations, and base
      classes. This stops generated tools raising `NameError` without following imports
      into other modules.
- [ ] Preserve repeatable Typer/Click options and collection cardinality when converting
      to API or MCP schemas.
- [ ] Support package and sibling imports when detecting a source file directly. Detection
      currently imports by file path without adding the source directory to `sys.path`.
- [ ] Detect apps created by factories such as `app = create_app()` without broadening
      directory discovery into importing every Python file.
- [ ] Define and preserve multi-method FastAPI route semantics. `ToolInfo` currently stores
      one HTTP method, so a route registered for several methods is lossy.

### Framework polish

- [ ] Handle `Annotated[str, Body(...)]` style FastAPI parameters ([#1](https://github.com/tugrulguner/intpot/issues/1))
- [ ] Emit nested command hierarchies. Reading them works; see "Already shipped". What's
      missing is the other direction — generating a Typer sub-app rather than a flat
      command ([#2](https://github.com/tugrulguner/intpot/issues/2))
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
  against. The annotation is derived from every reachable outcome of the body, not from
  whether a `return` appears somewhere: a function that returns on one branch and falls
  through on another is annotated `dict | None`, because FastAPI rejects the response
  otherwise.
- **Reading nested command hierarchies** — `app.add_typer(db, name="db")` is walked to any
  depth and each command extracted, named by its path: `db migrate` becomes `db_migrate`.
  Generating a nested hierarchy back out is still open (#2).
- **Round-trip fidelity tests** — `tests/test_roundtrip.py` covers all three pairings.
- **Direct import resolution** — imports referenced by a function body are carried into
  the generated file, including dotted and mixed import statements. Same-module
  declarations and dependencies across imported modules are not yet followed.
- **Collision-safe directory output** — directory conversion mirrors the source tree, so
  files with the same basename in separate packages cannot overwrite each other.
- **Actionable source failures** — import errors, syntax errors, and import-time
  `sys.exit()` calls are reported without a traceback. Directory scans report a bad file,
  continue, and convert the remaining apps.

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
- **Cross-module dependency resolution** — after same-module dependency closure is
  reliable, follow dependencies through imported project modules and packages
- **Full error-handling conversion** — Typer exits are mapped today; HTTP exceptions and
  MCP error patterns are not

### Non-goals for v2

- Runtime interop / adapter layer (intpot is a code generator, not a runtime bridge)
- Supporting frameworks beyond Typer, FastMCP, and FastAPI
- **Variadic tool signatures.** `*args` and `**kwargs` have no representation that means
  the same thing as a CLI argument, an HTTP request body, and an MCP tool schema, so
  `@app.tool()` rejects them outright rather than guessing. Use explicit named parameters.

---

Linked items above are tracked as issues; unlinked items are directional roadmap work and
should get a focused issue before implementation. If something here interests you,
[CONTRIBUTING.md](CONTRIBUTING.md) has the setup and
[good first issues](https://github.com/tugrulguner/intpot/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are a gentler place to start.
