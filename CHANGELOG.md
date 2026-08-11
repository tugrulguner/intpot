# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Unreleased changes live as fragment files in [`changelog.d/`](changelog.d/) until a
release assembles them here — run `make changelog-draft` to preview them.

<!-- towncrier release notes start -->

## [0.5.0] - 2026-08-10

### Changed

- `intpot serve --api` now reads tool arguments from the request body instead of the
  query string, matching the code that `intpot eject --to api` generates. Serving and
  ejecting the same app previously produced two different HTTP interfaces. Parameters
  carrying an explicit source — `Query`, `Header`, or `Path` — are honoured as declared.
  **If you call a served app with query-string arguments, send a JSON body instead.** ([#54](https://github.com/tugrulguner/intpot/pull/54))
- The package description now reflects what intpot does — define tools once and serve them
  as a CLI, API, or MCP server, as well as converting between the three. The old text
  described only the converter, which predates the `intpot.App` runtime. ([#55](https://github.com/tugrulguner/intpot/pull/55))
- `intpot serve --api` and `App.serve(mode="api")` now bind `127.0.0.1` instead of
  `0.0.0.0`, so a served app is no longer reachable from the network by default. **Pass
  `--host 0.0.0.0` if you were relying on that.** Alongside it, `intpot --version` no
  longer crashes when package metadata is unreadable, and identifiers keep their leading
  underscores — `_name` used to be rewritten to `name`, which could collide with a real
  `name` in generated code. ([#60](https://github.com/tugrulguner/intpot/pull/60))

### Fixed

- `intpot eject --to api` no longer generates code that fails on every request. The
  handler was annotated `-> dict` regardless of what the preserved function body actually
  returned, so FastAPI validated the response against `dict` and raised
  `ResponseValidationError`. The annotation now follows the tool's real return type. ([#52](https://github.com/tugrulguner/intpot/pull/52))
- Generated Typer CLIs now print what their commands return. `intpot eject --to cli`
  emitted the preserved function body directly under `@app.command()`, and Typer discards
  return values, so the command computed its result and printed nothing — the same bug
  fixed for `intpot serve --cli` in 0.4.1, which never reached the code generator. Async
  tools are also fixed: the generated command was `async def`, which Typer never awaits,
  and now runs the body through `asyncio.run`. ([#53](https://github.com/tugrulguner/intpot/pull/53))
- `intpot to api` no longer generates handlers that fail on every request. Converted
  handlers are annotated `-> dict`, but the body returned whatever the source function
  returned, so FastAPI rejected the response. Scalar returns are now wrapped as
  `{"result": ...}` — matching the stub the converter already emits for tools with no
  body — while sources that already return a mapping are left as they are. ([#56](https://github.com/tugrulguner/intpot/pull/56))
- The worked examples in the README and `examples/conversions/` now match what the
  generators actually emit. Every example showed output from an older version of the
  templates — one of them a Pydantic request model that has not been generated in a long
  time. ([#57](https://github.com/tugrulguner/intpot/pull/57))
- `intpot serve --cli` can now actually run your tools. Arguments meant for the served app
  were rejected by intpot's own argument parser, and any that got past it were discarded
  before Typer saw them, so the command could only ever print an error. Use `--` to pass
  through a flag that intpot also defines, such as `--port`. ([#58](https://github.com/tugrulguner/intpot/pull/58))
- Converting a directory no longer aborts when one file fails to import. Discovery
  executes each candidate module to find its app instance, and any error other than a
  missing app propagated out and killed the whole scan, so none of the working files were
  converted either. Bad files are now skipped with a message on stderr. ([#59](https://github.com/tugrulguner/intpot/pull/59))
- Tools declaring `*args` or `**kwargs` no longer break `intpot serve --api` — variadic
  parameters have no HTTP equivalent and are left out of the route instead of producing a
  signature FastAPI cannot serve. Generated code also stops reformatting the blank lines
  inside a preserved function body; only the spacing between top-level definitions is
  normalised. ([#61](https://github.com/tugrulguner/intpot/pull/61))

## [0.4.2] - 2026-08-08

### Added

- `@app.tool()` accepts a `description` argument to override the description that would
  otherwise be derived from the function's docstring — useful when the docstring is
  written for developers reading the code rather than for the agent calling the tool.
  Thanks @itniuma2026 for a first contribution! ([#44](https://github.com/tugrulguner/intpot/pull/44))

### Fixed

- `async def` tools now actually run under `intpot serve --cli`. The CLI wrapper called
  the function but never awaited it, so an async tool printed a coroutine repr instead of
  its result; the coroutine is now run to completion before its return value is echoed.
  Thanks @guyua9 for a first contribution! ([#45](https://github.com/tugrulguner/intpot/pull/45))
- Converting a FastAPI app no longer collapses every parameter into a request body.
  `Query`, `Header`, `Path`, and `Body` sources are now detected during inspection and
  preserved in generated code, so a query parameter stays a query parameter instead of
  becoming `Body(...)`. Thanks @MhussainD4772 for a first contribution! ([#47](https://github.com/tugrulguner/intpot/pull/47))

## [0.4.1] - 2026-04-08

### Fixed

- `intpot serve --cli` now prints return values — tool functions were executing but silently dropping output because Typer commands require explicit `typer.echo()` calls. The CLI builder now wraps registered functions so return values are printed automatically.

## [0.4.0] - 2026-04-07

### Added

- **`intpot.App` — write once, serve everywhere runtime** — define tools with `@app.tool()` and serve them as CLI, API, or MCP server without any conversion step
- **`intpot serve` command** — `intpot serve app.py --cli/--api/--mcp` serves an intpot App as a Typer CLI, FastAPI server, or FastMCP server
- **`intpot eject` command** — `intpot eject app.py --to cli/api/mcp` exports an intpot App as standalone framework code (uses existing generators)
- `App.tool()` decorator — registers functions with full signature introspection (types, defaults, docstrings, async support)
- `App.serve(mode, host, port)` — programmatic serving in any mode
- `App.eject(target)` — programmatic code generation returning standalone framework code as a string
- `App.tools` property — access normalized `ToolInfo` list for all registered tools
- Runtime builders: `build_typer_app`, `build_fastapi_app`, `build_fastmcp_app` — dynamically construct live framework instances from registered tools
- `examples/universal_app.py` — example demonstrating the new App pattern
- 32 new tests covering App class, runtime builders, serve command, and eject command (136 total)

### Changed

- The existing conversion pipeline (`intpot to cli/mcp/api`, `intpot.load()`, `IntpotApp`) is fully preserved and unchanged

## [0.3.0] - 2026-03-26

### Added

- **`intpot add skills` command** — install intpot skills/rules for AI coding agents directly into your project
- Auto-detects which agents are configured by checking for `.claude/`, `.cursor/`, `.windsurf/`, `.github/`, `.clinerules/`, and `AGENTS.md`
- Supports 6 agents: **Claude Code**, **Cursor**, **Windsurf**, **GitHub Copilot**, **Cline**, and **OpenAI Codex CLI**
- `--agent` flag to target a specific agent (e.g. `intpot add skills --agent claude`)
- `--path` flag to target a specific project directory
- Installs two skill files per agent: **intpot CLI** (command reference) and **intpot Python API** (programmatic usage)
- Idempotent — safe to run multiple times without duplicating content
- Each agent gets the correct file format: `.md` for Claude/Windsurf/Cline, `.mdc` with frontmatter for Cursor, appended sections for Copilot/Codex
- 14 new tests covering all agents, auto-detection, edge cases, and content quality

## [0.2.6] - 2026-03-16

### Fixed

- FastAPI `Body(...)` no longer emits `PydanticUndefined` as a literal default — parameters using `Body(...)` are now correctly treated as required
- MCP `ctx: Context` parameters are filtered out during inspection so they don't bleed into CLI/API output where `Context` is undefined
- `copy.deepcopy` in transforms no longer breaks `_SENTINEL` identity checks — `_SENTINEL` is now a singleton class that survives copy/deepcopy
- Generated code now includes source imports (e.g. `import json`) that the original function body references, preventing `NameError` at runtime
- CLI inspector now unwraps Typer-decorated callbacks before extracting source imports (Typer wraps callbacks, causing `inspect.getfile` to resolve to `typer/main.py` instead of the user's source file)
- Template whitespace cleanup — removed extra blank lines emitted when no extra imports are present

### Added

- `extract_source_imports(fn)` utility — AST-based extraction of imports referenced by a function body
- `source_imports` field on `ToolInfo` for carrying per-tool import requirements through the pipeline
- Extra imports rendering in all three output templates (CLI, MCP, API)
- Dependency injection comments in generated code — `Depends()` parameters are surfaced as `# NOTE:` comments
- Generated API code now includes `if __name__ == "__main__": uvicorn.run(...)` entry point, matching CLI and MCP templates
- Advanced example apps (`advanced_cli.py`, `advanced_mcp.py`, `advanced_api.py`) exercising real-world patterns
- `scripts/demo.sh` — full demo script that runs all conversions, scaffolding, and directory discovery, saving outputs to `examples/conversions/`
- `scripts/manual_test.py` — targeted verification script for all v0.2.4 bug fixes
- 8 new roundtrip tests validating generated code compiles and preserves tool signatures (90 total)

## [0.2.3] - 2026-03-04

### Fixed

- CLI inspector now converts hyphenated command names to underscores (e.g. `add-numbers` → `add_numbers`) to produce valid Python identifiers
- PascalCase generator handles camelCase, snake_case, and hyphenated names correctly (was using Jinja2 `capitalize` which lowercased everything)
- CLI inspector uses Click's `param.required` flag instead of checking `default is not None` — fixes false defaults for required params
- MCP inspector async fallback uses `ThreadPoolExecutor` instead of deprecated `get_event_loop()`
- Detector uses path-hashed module names to prevent collisions when loading multiple files with the same stem
- Detector cleans up `sys.modules` after loading source files
- Discovery narrows exception catching to `DetectionError | SyntaxError | ImportError | OSError` instead of bare `Exception`
- Templates escape triple-quotes in docstrings via `escape_doc` filter
- API template conditionally imports pydantic only when needed
- API template uses `http_method` from `ToolInfo` instead of hardcoding POST

### Added

- `--version` / `-V` flag on CLI
- `IntpotApp.__repr__()` for better debugging
- `IntpotApp.tools` public property
- `IntpotApp.write()` accepts `SourceType` enum in addition to strings
- `ToolInfo.http_method` field — API inspector captures HTTP methods from routes
- Friendly `ModuleNotFoundError` messages pointing to `pip install intpot[mcp]` / `intpot[api]`
- Path separator validation in `intpot init`
- 16 new tests (60 total)

### Changed

- Deduplicated CLI command logic into shared `_convert.py` module
- Shared `python_type_name` utility in `inspectors/_utils.py`
- Release workflow requires CI to pass before publishing
- Removed unused `rich` dependency
- Fixed README reference to `ToolDef` → `ToolInfo`

## [0.2.1] - 2026-03-02

### Added

- **Python API** — `intpot.load()` accepts file paths or live app instances (FastMCP, Typer, FastAPI) and returns an `IntpotApp` with `.to_cli()`, `.to_mcp()`, `.to_api()` methods
- **`.write(path, target)`** — generate and write to a file in one step from the Python API
- **Directory auto-discovery** — `intpot to cli ./myproject/` scans a directory for convertible apps
- `detect_instance()` function for detecting live Python objects (not just files)
- `discover_sources()` function for recursive directory scanning
- `IntpotApp` wrapper class for programmatic conversions
- Pyright type checking (`make typecheck`) with `[tool.pyright]` config
- pytest-cov for test coverage reporting
- CI typecheck job and coverage in test job
- Example conversion files with input/output headers for all 6 directions
- Full README rewrite with architecture diagram, Python API docs, CLI reference
- CONTRIBUTING.md project structure and type checking sections
- New tests for Python API, discovery, and `.write()` (44 total)

## [0.1.0] - 2026-03-02

### Added

- Core inspection engine for CLI (Typer), MCP (FastMCP), and API (FastAPI) apps
- Code generation for all 6 conversion directions (CLI↔MCP↔API)
- `intpot to cli` command — convert MCP/API source to a Typer CLI
- `intpot to mcp` command — convert CLI/API source to a FastMCP server
- `intpot to api` command — convert CLI/MCP source to a FastAPI app
- `intpot init` command — scaffold new CLI, MCP, or API projects
- Jinja2-based template rendering for generated code
- Auto-detection of source framework type
- Full test suite (29 tests)
