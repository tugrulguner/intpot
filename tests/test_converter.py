"""Tests for the Python API (intpot.load / IntpotApp)."""

from __future__ import annotations

import ast
import importlib.util
import py_compile
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

import intpot
from intpot.converter import IntpotApp, UnsupportedFastAPIDependencyError
from intpot.core.detector import DetectionError
from intpot.core.models import SourceType


def _import_written(path: Path) -> ModuleType:
    """Import a written artifact from disk, the way Python loads a module.

    The loader decodes the file with the encoding its own PEP 263 declaration
    names — which is the part a `compile()` of a string never exercises.
    """
    spec = importlib.util.spec_from_file_location("written_cli_app", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _written_typer_help(path: Path, encoding: str) -> str:
    """Read the help text back out of a written file, as Python will read it.

    The source holds an escape; the value it stands for has to be the one
    intpot meant. An assertion on the generated string would not see the
    escape at all, so the file is parsed the way the loader parses it.
    """
    tree = ast.parse(path.read_text(encoding=encoding))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "Typer":
            continue
        for keyword in node.keywords:
            if keyword.arg == "help":
                return ast.literal_eval(keyword.value)
    raise AssertionError("the written file has no Typer(help=...) call")


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
        """Greet someone with a café, naïve façade."""
        return f"Hello, {name}!"

    out = tmp_path / "encoded" / "cli_app.py"
    intpot.load(mcp).write(out, "cli", encoding="latin-1")

    # The encoding only matters if Python can still load what was written: a
    # declaration the loader accepts, then the real compile the file would
    # have to survive on disk.
    written = out.read_text(encoding="latin-1")
    assert written.splitlines()[0] == "# -*- coding: iso8859-1 -*-"
    assert "café" in written
    py_compile.compile(str(out), cfile=str(tmp_path / "cli_app.pyc"), doraise=True)

    # intpot's own text is written as an escape. U+2014 is not in Latin-1, so
    # an em dash left in the source was enough to refuse the whole write.
    assert "\\u2014" in written
    assert "—" not in written


def test_the_written_cli_artifact_imports_and_runs(tmp_path):
    """A file that compiles is not a file that runs.

    The written source has to survive the loader's own decoding — the PEP 263
    declaration, the declared encoding — and then behave like the CLI it
    claims to be.
    """
    from fastmcp import FastMCP
    from typer.testing import CliRunner

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        """Greet someone with a café, naïve façade."""
        return f"Hello, {name}!"

    out = tmp_path / "encoded" / "cli_app.py"
    intpot.load(mcp).write(out, "cli", encoding="latin-1")

    module = _import_written(out)

    # The escape must not change the value: the CLI still says what intpot
    # meant, it is only the bytes on disk that changed.
    assert _written_typer_help(out, "latin-1") == "test — powered by intpot"

    result = CliRunner().invoke(module.app, ["greet", "World"])

    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "Hello, World!"


def test_intpot_own_text_does_not_block_a_narrow_encoding(tmp_path):
    """The refusal belongs to the user's text, not to intpot's own.

    The CLI template adds an em dash to the app help. Latin-1 does not cover
    U+2014 and ASCII does not either, so that one character of intpot's own
    boilerplate was enough to refuse every narrow-encoding write.
    """
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        """Greet someone with a wave."""
        return f"Hello, {name}!"

    out = tmp_path / "encoded" / "cli_app.py"
    intpot.load(mcp).write(out, "cli", encoding="ascii")

    written = out.read_text(encoding="ascii")

    assert written.isascii()
    assert "\\u2014" in written
    py_compile.compile(str(out), cfile=str(tmp_path / "cli_app.pyc"), doraise=True)


def test_write_rejects_an_encoding_python_cannot_load(tmp_path):
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    out = tmp_path / "encoded" / "cli_app.py"
    with pytest.raises(ValueError, match="Unsupported source encoding"):
        intpot.load(mcp).write(out, "cli", encoding="utf-16")

    # Rejected before anything touches the filesystem: UTF-16 source loads as
    # null bytes, not as the file the caller asked for.
    assert not out.parent.exists()


def test_write_rejects_a_source_its_encoding_cannot_represent(tmp_path):
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        """Greet someone — with a wave."""
        return f"Hello, {name}!"

    out = tmp_path / "encoded" / "cli_app.py"
    with pytest.raises(ValueError, match="not representable"):
        intpot.load(mcp).write(out, "cli", encoding="ascii")

    # The refusal is the user's own text: intpot's em dash is written as an
    # escape, but a description copied out of the source is not.
    #
    # Not an empty file either: cp1252 is the supported encoding that holds
    # the em dash, and the same source has to survive the round trip.
    assert not out.exists()
    intpot.load(mcp).write(out, "cli", encoding="cp1252")
    py_compile.compile(str(out), cfile=str(tmp_path / "cli_app.pyc"), doraise=True)


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


def test_write_refuses_a_destination_created_while_it_generates(tmp_path, monkeypatch):
    """The exclusive create is the guarantee; an exists() check cannot be.

    A second writer that lands the file after generation but before the write
    is the whole window a check-then-write leaves open, and it is reproduced
    here by generating through a hook instead of racing a thread.
    """
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    out = tmp_path / "cli_app.py"
    app = intpot.load(mcp)
    generate = app.to_cli

    def generate_into_a_race():
        code = generate()
        out.write_text("another writer got here first", encoding="utf-8")
        return code

    monkeypatch.setattr(app, "to_cli", generate_into_a_race)

    with pytest.raises(FileExistsError, match="already exists"):
        app.write(out, "cli", overwrite=False)

    assert out.read_text(encoding="utf-8") == "another writer got here first"


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
