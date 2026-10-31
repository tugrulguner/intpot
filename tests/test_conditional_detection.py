from __future__ import annotations

import asyncio
import textwrap

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

import intpot
from intpot.core.detector import DetectionError, detect_source

APP = """app = typer.Typer()
@app.command()
def hello(name: str = "world") -> None:
    typer.echo(f"Hello {name}")
"""


def _wrapped(prefix: str, suffix: str = "") -> str:
    return "import typer\n" + prefix + textwrap.indent(APP, "    ") + suffix


@pytest.mark.parametrize(
    "source",
    [
        _wrapped("if True:\n"),
        _wrapped("if False:\n    pass\nelse:\n"),
        _wrapped("try:\n", "except RuntimeError:\n    pass\n"),
        _wrapped("try:\n    raise RuntimeError()\nexcept RuntimeError:\n"),
        _wrapped("try:\n    pass\nexcept RuntimeError:\n    pass\nelse:\n"),
        _wrapped("try:\n    pass\nfinally:\n"),
        _wrapped(
            "try:\n    raise ExceptionGroup('probe', [ValueError()])\nexcept* ValueError:\n"
        ),
        "import typer\nif True:\n    try:\n"
        + textwrap.indent(APP, "        ")
        + "    except RuntimeError:\n        pass\n",
    ],
)
def test_conditional_app_generates_native_api_and_mcp(tmp_source, source):
    application = intpot.load(tmp_source(source))
    assert [tool.name for tool in application.tools] == ["hello"]
    api_namespace = {}
    exec(application.to_api(), api_namespace)
    with TestClient(api_namespace["app"]) as client:
        response = client.post("/hello", json="Ada")
        assert response.status_code == 200
        assert response.json() == {"result": "Hello Ada"}
    mcp_namespace = {}
    exec(application.to_mcp(), mcp_namespace)

    async def call() -> None:
        async with Client(mcp_namespace["mcp"]) as client:
            result = await client.call_tool("hello", {"name": "Ada"})
            assert result.content[0].text == "Hello Ada"

    asyncio.run(call())


@pytest.mark.parametrize(
    "scope", ["def factory():", "async def factory():", "class Factory:"]
)
def test_factory_or_class_constructor_does_not_cause_import(
    tmp_source, tmp_path, scope
):
    marker = tmp_path / "imported"
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
        "import typer\n" + scope + "\n    app = typer.Typer()\n"
    )
    with pytest.raises(DetectionError, match="No FastMCP, Typer, or FastAPI"):
        detect_source(tmp_source(source))
    assert not marker.exists()


@pytest.mark.parametrize(
    "body",
    [
        "if False:\n    app = typer.Typer()\n",
        "if True:\n    app = typer.Typer()\napp = None\n",
    ],
)
def test_candidate_constructor_still_requires_live_framework_instance(tmp_source, body):
    with pytest.raises(DetectionError, match="No FastMCP, Typer, or FastAPI"):
        detect_source(tmp_source("import typer\n" + body))


def test_conditional_import_and_condition_execute_once(tmp_source, tmp_path):
    marker = tmp_path / "events"
    source = f"""from pathlib import Path
import typer
marker = Path({str(marker)!r})
marker.write_text("imported\\n")
def available():
    with marker.open("a") as stream:
        stream.write("condition\\n")
    return True
if available():
    app: typer.Typer = typer.Typer()
    @app.command()
    def hello() -> None:
        typer.echo("Hello")
"""
    application = intpot.load(tmp_source(source))
    assert [tool.name for tool in application.tools] == ["hello"]
    assert marker.read_text() == "imported\ncondition\n"
