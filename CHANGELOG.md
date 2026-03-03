# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
