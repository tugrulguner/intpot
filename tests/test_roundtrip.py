"""Roundtrip conversion tests — verify tools survive conversion cycles."""

from __future__ import annotations

import textwrap
from pathlib import Path

from intpot.converter import load


def _normalise_tools(tools: list) -> list[dict]:
    """Extract comparable fields from ToolInfo list."""
    result = []
    for t in tools:
        result.append(
            {
                "name": t.name,
                "param_names": sorted(p.name for p in t.parameters),
                "param_types": {p.name: p.type_annotation for p in t.parameters},
                "required": {p.name: p.required for p in t.parameters},
            }
        )
    return sorted(result, key=lambda x: x["name"])


# --- Source app code snippets ---

MCP_SOURCE = textwrap.dedent("""\
    from fastmcp import FastMCP

    mcp = FastMCP("test-server")

    @mcp.tool()
    def greet(name: str, greeting: str = "Hello") -> str:
        \"\"\"Greet someone.\"\"\"
        return f"{greeting}, {name}!"

    @mcp.tool()
    def add(a: int, b: int) -> int:
        \"\"\"Add two numbers.\"\"\"
        return a + b
""")

CLI_SOURCE = textwrap.dedent("""\
    import typer

    app = typer.Typer()

    @app.command()
    def greet(
        name: str = typer.Argument(..., help="Name to greet"),
        greeting: str = typer.Option("Hello", help="Greeting word"),
    ) -> None:
        \"\"\"Greet someone.\"\"\"
        typer.echo(f"{greeting}, {name}!")

    @app.command()
    def add(
        a: int = typer.Argument(..., help="First number"),
        b: int = typer.Argument(..., help="Second number"),
    ) -> None:
        \"\"\"Add two numbers.\"\"\"
        typer.echo(a + b)
""")

API_SOURCE = textwrap.dedent("""\
    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/greet")
    def greet(name: str, greeting: str = "Hello") -> dict:
        \"\"\"Greet someone.\"\"\"
        return {"message": f"{greeting}, {name}!"}

    @app.post("/add")
    def add(a: int, b: int) -> dict:
        \"\"\"Add two numbers.\"\"\"
        return {"result": a + b}
""")


class TestMCPRoundtrips:
    def test_mcp_to_cli_preserves_tools(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(MCP_SOURCE)
        app = load(p)
        cli_code = app.to_cli()
        assert compile(cli_code, "<string>", "exec")

        # Verify generated code has all tools
        assert "def greet" in cli_code
        assert "def add" in cli_code

    def test_mcp_to_api_preserves_tools(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(MCP_SOURCE)
        app = load(p)
        api_code = app.to_api()
        assert compile(api_code, "<string>", "exec")
        assert "def greet" in api_code
        assert "def add" in api_code


class TestCLIRoundtrips:
    def test_cli_to_mcp_preserves_tools(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(CLI_SOURCE)
        app = load(p)

        mcp_code = app.to_mcp()
        assert compile(mcp_code, "<string>", "exec")
        assert "def greet" in mcp_code
        assert "def add" in mcp_code

    def test_cli_to_api_preserves_tools(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(CLI_SOURCE)
        app = load(p)

        api_code = app.to_api()
        assert compile(api_code, "<string>", "exec")
        assert "def greet" in api_code
        assert "def add" in api_code


class TestAPIRoundtrips:
    def test_api_to_mcp_preserves_tools(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(API_SOURCE)
        app = load(p)

        mcp_code = app.to_mcp()
        assert compile(mcp_code, "<string>", "exec")
        assert "def greet" in mcp_code
        assert "def add" in mcp_code

    def test_api_to_cli_preserves_tools(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(API_SOURCE)
        app = load(p)

        cli_code = app.to_cli()
        assert compile(cli_code, "<string>", "exec")
        assert "def greet" in cli_code
        assert "def add" in cli_code


class TestParameterPreservation:
    """Verify parameter names, types, and required flags survive conversion."""

    def test_mcp_to_cli_params(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(MCP_SOURCE)
        app = load(p)
        tools = _normalise_tools(app.tools)

        greet = next(t for t in tools if t["name"] == "greet")
        assert "name" in greet["param_names"]
        assert "greeting" in greet["param_names"]
        assert greet["required"]["name"] is True
        assert greet["required"]["greeting"] is False

    def test_cli_to_mcp_params(self, tmp_path: Path) -> None:
        p = tmp_path / "source.py"
        p.write_text(CLI_SOURCE)
        app = load(p)
        tools = _normalise_tools(app.tools)

        add_tool = next(t for t in tools if t["name"] == "add")
        assert "a" in add_tool["param_names"]
        assert "b" in add_tool["param_names"]
