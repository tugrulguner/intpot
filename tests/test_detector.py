"""Tests for source type detection."""

from __future__ import annotations

import pytest

from intpot.core.detector import DetectionError, detect_source
from intpot.core.models import SourceType


def test_detect_mcp(tmp_source):
    path = tmp_source("""
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def hello(name: str) -> str:
            return f"Hello, {name}!"
    """)
    source_type, app = detect_source(path)
    assert source_type == SourceType.MCP


def test_detect_typer(tmp_source):
    path = tmp_source("""
        import typer
        app = typer.Typer()

        @app.command()
        def hello(name: str = "world") -> None:
            typer.echo(f"Hello, {name}!")
    """)
    source_type, app = detect_source(path)
    assert source_type == SourceType.CLI


def test_detect_fastapi(tmp_source):
    path = tmp_source("""
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/hello")
        def hello(name: str = "world") -> dict:
            return {"message": f"Hello, {name}!"}
    """)
    source_type, app = detect_source(path)
    assert source_type == SourceType.API


def test_detect_unknown(tmp_source):
    path = tmp_source("""
        x = 42
    """)
    with pytest.raises(DetectionError):
        detect_source(path)


def test_detect_file_not_found(tmp_path):
    with pytest.raises(DetectionError, match="File not found"):
        detect_source(tmp_path / "nonexistent.py")
