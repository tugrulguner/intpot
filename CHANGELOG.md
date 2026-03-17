# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
