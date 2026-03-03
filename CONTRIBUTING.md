# Contributing to intpot

Thanks for your interest in contributing!

## Development Setup

1. Fork and clone the repository:

   ```bash
   git clone https://github.com/YOUR_USERNAME/intpot.git
   cd intpot
   ```

2. Install dependencies (requires [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync --all-extras
   ```

3. Install pre-commit hooks:

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

## Pull Request Process

1. Create a feature branch from `main`.
2. Make your changes and add tests if applicable.
3. Ensure `make check` passes (lint, typecheck, and tests).
4. Open a pull request with a clear description of your changes.

## Reporting Issues

- Use GitHub Issues to report bugs or request features.
- Include steps to reproduce for bug reports.
- Check existing issues before opening a new one.
