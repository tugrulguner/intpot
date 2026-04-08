# Contributing to intpot

Thanks for your interest in contributing!

## Development Setup

After forking and cloning (see [Pull Request Process](#pull-request-process) below):

1. Install dependencies (requires [uv](https://docs.astral.sh/uv/)):

   ```bash
   cd intpot
   uv sync --all-extras
   ```

2. Install pre-commit hooks:

   ```bash
   uv run pre-commit install
   ```

## Code Style

- We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.
- Run `make format` to auto-format your code.
- Run `make lint` to check for issues.
- Pre-commit hooks will run automatically on each commit.

## Type Checking

We use [Pyright](https://github.com/microsoft/pyright) for static type analysis.

- Run `make typecheck` to check types.
- Add type annotations to all new functions and methods.
- Use `from __future__ import annotations` for forward references.
- Pyright is configured in `pyproject.toml` under `[tool.pyright]`.

## Running Tests

```bash
make test
```

Or run the full check suite (lint + typecheck + test):

```bash
make check
```

## Project Structure

```
src/intpot/
├── __init__.py          # Package exports (App, IntpotApp, load)
├── cli.py               # Main CLI entry point
├── runtime.py           # Universal App class (@app.tool() decorator, serve, eject)
├── runtime_builders.py  # Build live Typer/FastAPI/FastMCP instances from registered tools
├── converter.py         # Conversion API (IntpotApp, load())
├── commands/            # CLI command handlers (serve, eject, to_cli, to_mcp, to_api, init)
├── core/
│   ├── models.py        # Shared data models (ToolInfo, ParameterInfo, SourceType)
│   ├── detector.py      # Auto-detect source type from files or live instances
│   ├── discovery.py     # Directory scanning for convertible apps
│   ├── transforms.py    # AST-based body/type transforms between frameworks
│   ├── inspectors/      # Framework-specific inspectors (extract tools)
│   └── generators/      # Framework-specific generators (render code)
└── templates/           # Jinja2 templates for code generation
```

Key concepts:
- **Runtime** — `intpot.App` registers tools via `@app.tool()` and serves them as CLI, API, or MCP at runtime
- **Detection** — identify framework type from a file path or live object
- **Inspection** — extract normalized `ToolInfo` from framework-specific apps
- **Generation** — render `ToolInfo` into target framework code via Jinja2 templates
- **Conversion API** — `intpot.load(source)` returns an `IntpotApp` for programmatic conversion
- **Eject** — export an `intpot.App` as standalone framework code using existing generators

## Pull Request Process

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/intpot.git
   ```
3. **Create a feature branch** from `main`:
   ```bash
   git checkout -b my-feature
   ```
4. Make your changes and add tests if applicable.
5. Ensure `make check` passes (lint, typecheck, and tests).
6. **Push** to your fork:
   ```bash
   git push origin my-feature
   ```
7. Open a **Pull Request** against `tugrulguner/intpot:main` with a clear description of your changes.

## Reporting Issues

- Use GitHub Issues to report bugs or request features.
- Include steps to reproduce for bug reports.
- Check existing issues before opening a new one.
