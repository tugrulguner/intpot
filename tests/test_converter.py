"""Tests for the Python API (intpot.load / IntpotApp)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import intpot
from intpot.converter import IntpotApp, UnsupportedFastAPIDependencyError
from intpot.core.detector import DetectionError
from intpot.core.models import SourceType


def test_unsupported_fastapi_dependency_error_is_public():
    assert intpot.UnsupportedFastAPIDependencyError is UnsupportedFastAPIDependencyError


def test_load_from_file(tmp_source):
    source = tmp_source("""
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """)
    app = intpot.load(str(source))
    assert isinstance(app, IntpotApp)
    assert app.source_type == SourceType.MCP
    assert app.source_path is not None


def test_load_from_mcp_instance():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    assert app.source_type == SourceType.MCP
    assert app.app is mcp
    assert app.source_path is None


def test_load_from_typer_instance():
    import typer

    cli = typer.Typer()

    @cli.command()
    def hello(name: str = typer.Argument(..., help="Name")) -> None:
        typer.echo(f"Hello {name}")

    app = intpot.load(cli)
    assert app.source_type == SourceType.CLI
    assert app.app is cli


def test_load_from_fastapi_instance():
    from fastapi import FastAPI

    api = FastAPI()

    @api.post("/greet")
    def greet(name: str) -> dict:
        return {"message": f"Hello, {name}!"}

    app = intpot.load(api)
    assert app.source_type == SourceType.API
    assert app.app is api


def test_to_cli_from_mcp():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    code = intpot.load(mcp).to_cli()
    assert "import typer" in code
    assert "def greet(" in code


def test_to_mcp_from_cli():
    import typer

    cli = typer.Typer()

    @cli.command()
    def hello(name: str = typer.Argument(..., help="Name")) -> None:
        typer.echo(f"Hello {name}")

    code = intpot.load(cli).to_mcp()
    assert "from fastmcp import FastMCP" in code
    assert "def hello(" in code


def test_to_api_from_cli():
    import typer

    cli = typer.Typer()

    @cli.command()
    def hello(name: str = typer.Argument(..., help="Name")) -> None:
        typer.echo(f"Hello {name}")

    code = intpot.load(cli).to_api()
    assert "from fastapi import FastAPI" in code
    assert "hello" in code


def test_to_api_accepts_a_source_returning_only_on_one_branch(tmp_source):
    source = tmp_source("""
        from fastmcp import FastMCP

        mcp = FastMCP("test")

        @mcp.tool()
        def maybe_result(enabled: bool) -> int:
            if enabled:
                return 1
    """)

    code = intpot.load(source).to_api()
    namespace: dict[str, object] = {}
    exec(compile(code, "<generated>", "exec"), namespace)
    client = TestClient(namespace["app"])  # type: ignore[arg-type]

    returned = client.post("/maybe_result", json=True)
    fell_through = client.post("/maybe_result", json=False)

    assert returned.status_code == 200
    assert returned.json() == {"result": 1}
    assert fell_through.status_code == 200
    assert fell_through.json() is None


def test_api_dependency_refuses_python_api_conversion_but_remains_inspectable():
    from fastapi import Depends, FastAPI

    api = FastAPI()

    def current_user() -> str:
        return "Ada"

    @api.get("/greet")
    def greet(user: str = Depends(current_user)) -> dict:
        return {"message": f"Hello, {user}!"}

    loaded = intpot.load(api)

    assert loaded.tools[0].name == "greet"
    assert loaded.tools[0].dependencies == ["current_user"]
    with pytest.raises(
        UnsupportedFastAPIDependencyError,
        match=r"/greet.*greet.*current_user.*Depends/Security.*issue #20",
    ):
        loaded.to_cli()


def test_conversion_uses_the_cached_inspection_snapshot():
    from fastapi import Depends, FastAPI

    api = FastAPI()

    @api.get("/first")
    def first() -> dict:
        return {"first": True}

    loaded = intpot.load(api)
    assert [tool.name for tool in loaded.tools] == ["first"]

    def later_dependency() -> str:
        return "later"

    @api.get("/second")
    def second(value: str = Depends(later_dependency)) -> dict:
        return {"value": value}

    code = loaded.to_cli()

    assert "def first(" in code
    assert "def second(" not in code


def test_same_type_raises():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    with pytest.raises(ValueError, match=r"already.*MCP"):
        app.to_mcp()


def test_write_to_file(tmp_path):
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    out = tmp_path / "output" / "cli_app.py"
    result = app.write(out, "cli")
    assert out.exists()
    content = out.read_text()
    assert "import typer" in content
    assert "def greet(" in content
    assert result == out.resolve()


def test_write_to_file_honors_encoding(tmp_path):
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    out = tmp_path / "encoded" / "cli_app.py"
    intpot.load(mcp).write(out, "cli", encoding="utf-16")

    assert "import typer" in out.read_text(encoding="utf-16")


def test_write_to_file_can_refuse_overwrite(tmp_path):
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    out = tmp_path / "cli_app.py"
    out.write_text("keep this file", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        intpot.load(mcp).write(out, "cli", overwrite=False)

    assert out.read_text(encoding="utf-8") == "keep this file"


def test_write_invalid_target():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    with pytest.raises(ValueError, match="Unknown target"):
        app.write("/tmp/out.py", "invalid")


def test_unknown_instance():
    with pytest.raises(DetectionError, match="Unrecognized"):
        intpot.load(42)
