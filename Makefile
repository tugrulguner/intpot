.PHONY: install test lint format typecheck check build clean changelog-draft changelog

install:
	uv sync --all-extras

test:
	uv sync --all-extras --reinstall-package intpot
	uv run pytest tests/ -v

lint:
	uv run ruff check src/ tests/ examples/semantic_schema.py scripts/verify_generated_examples.py
	uv run ruff format --check src/ tests/ examples/semantic_schema.py scripts/verify_generated_examples.py

format:
	uv run ruff check --fix src/ tests/ examples/semantic_schema.py scripts/verify_generated_examples.py
	uv run ruff format src/ tests/ examples/semantic_schema.py scripts/verify_generated_examples.py

typecheck:
	uv run pyright src/ tests/ examples/semantic_schema.py scripts/verify_generated_examples.py

check: lint typecheck test

changelog-draft:
	uv run towncrier build --draft --version $$(uv version --short)

changelog:
	uv run towncrier build --yes --version $$(uv version --short)

build:
	uv build

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
