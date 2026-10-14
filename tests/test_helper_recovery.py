from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot


@pytest.mark.parametrize("target", ["cli", "mcp", "api"])
def test_helper_and_constant_execute_through_generated_consumers(tmp_source, target):
    registration = (
        'from fastmcp import FastMCP\napp = FastMCP("helpers")\n@app.tool()\n'
        if target == "api"
        else 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/calc")\n'
    )
    header, decorator = registration.rsplit("@", 1)
    source = (
        header
        + "FACTOR = 7\ndef scale(x: int) -> int:\n    return x * FACTOR\n@"
        + decorator
        + "def calc(x: int) -> int:\n    return scale(x)\n"
    )
    loaded = intpot.load(tmp_source(source))
    assert loaded.assess()["diagnostics"] == []
    schema = loaded.schema
    namespace: dict[str, Any] = {"__name__": "helper_consumer"}
    code = getattr(loaded, "to_" + target)()
    exec(compile(code, "<generated>", "exec", dont_inherit=True), namespace)
    if target == "api":
        response = TestClient(namespace["app"]).post("/calc", json=3)
        assert response.status_code == 200, response.text
        assert response.json() == {"result": 21}
    elif target == "cli":
        result = CliRunner().invoke(namespace["app"], ["3"])
        assert result.exit_code == 0, result.exception
        assert result.stdout == "21\n"
    else:
        result = asyncio.run(namespace["mcp"].call_tool("calc", {"x": 3}))
        assert result.content[0].text == "21"
    assert loaded.schema is schema


@pytest.mark.parametrize(
    "helper",
    [
        "FACTOR = 7\nglobals()['FACTOR'] = 9\ndef scale(x):\n    return x * FACTOR\n",
        "FACTOR = 7\ndef scale(x):\n    global FACTOR\n    FACTOR += 1\n    return x * FACTOR\n",
        "def make_default():\n    return 7\ndef scale(x, factor=make_default()):\n    return x * factor\n",
    ],
)
def test_unsafe_support_is_not_recovered(tmp_source, helper):
    path = tmp_source(
        "from fastapi import FastAPI\napp = FastAPI()\n"
        + helper
        + "@app.get('/calc')\ndef calc(x: int) -> int:\n    return scale(x)\n"
    )
    loaded = intpot.load(path)
    with pytest.raises(intpot.MissingBindingError, match="scale"):
        loaded.to_cli()


def test_local_names_do_not_copy_unrelated_module_bindings(tmp_source):
    path = tmp_source("""from fastapi import FastAPI
app = FastAPI()
FACTOR = 999
def scale(x):
    FACTOR = 7
    return x * FACTOR
@app.get('/calc')
def calc(x: int) -> int:
    return scale(x)
""")
    loaded = intpot.load(path)
    code = loaded.to_cli()
    assert "999" not in code
    namespace: dict[str, Any] = {"__name__": "local_helper"}
    exec(compile(code, "<cli>", "exec", dont_inherit=True), namespace)
    result = CliRunner().invoke(namespace["app"], ["3"])
    assert result.stdout == "21\n", result.exception


@pytest.mark.parametrize(
    "mutation",
    [
        "scale.__defaults__ = (9,)\n",
        "globals()['scale'].__code__ = (lambda x, factor=7: x * 99).__code__\n",
    ],
)
def test_rebound_helper_runtime_contract_is_not_copied(tmp_source, mutation):
    source = (
        "from fastapi import FastAPI\napp = FastAPI()\ndef scale(x, factor=7):\n    return x * factor\n"
        + mutation
        + "@app.get('/calc')\ndef calc(x: int) -> int:\n    return scale(x)\n"
    )
    loaded = intpot.load(tmp_source(source))
    with pytest.raises(intpot.MissingBindingError, match="scale"):
        loaded.to_cli()


def test_dynamic_global_lookup_in_helper_is_not_recovered(tmp_source):
    loaded = intpot.load(
        tmp_source("""from fastapi import FastAPI
app = FastAPI()
FACTOR = 7
def scale(x):
    return x * globals()['FACTOR']
@app.get('/calc')
def calc(x: int) -> int:
    return scale(x)
""")
    )
    with pytest.raises(intpot.MissingBindingError, match="scale"):
        loaded.to_cli()


def test_transitive_helpers_imports_and_recursive_calls(tmp_source):
    loaded = intpot.load(
        tmp_source("""from fastapi import FastAPI
from math import ceil as round_up
app = FastAPI()
FACTOR = 7
def add_factor(x):
    if x <= 0:
        return 0
    return FACTOR + add_factor(x - 1)
def scale(x):
    return round_up(add_factor(x))
@app.get('/calc')
def calc(x: int) -> int:
    return scale(x)
""")
    )
    namespace: dict[str, Any] = {"__name__": "transitive"}
    code = loaded.to_cli()
    exec(compile(code, "<cli>", "exec", dont_inherit=True), namespace)
    result = CliRunner().invoke(namespace["app"], ["3"])
    assert result.exit_code == 0, result.exception
    assert result.stdout == "21\n"
    schema = loaded.schema
    info = loaded.tools[0]
    assert info.support_definitions
    assert intpot.ToolSchema.from_info(info) == schema.tools[0]
    info.support_definitions.clear()
    assert schema.tools[0].support_definitions
    assert schema.tools[0].to_dict()["support_definitions"]
    assert hash(schema.tools[0]) == hash(
        intpot.ToolSchema.from_info(schema.tools[0].to_info())
    )


def test_unresolved_reference_in_explicit_support_is_refused():
    from intpot.converter import project_schema
    from intpot.core.models import (
        ApplicationSchema,
        ParameterInfo,
        SourceType,
        ToolInfo,
    )

    schema = ApplicationSchema.from_tools(
        name="explicit",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                name="calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=["def scale(x):\n    return missing + x"],
            )
        ],
    )
    with pytest.raises(intpot.MissingBindingError, match="missing"):
        project_schema(schema, SourceType.CLI)


def test_cross_tool_support_conflict_refuses_cli_before_writes(tmp_source, tmp_path):
    from intpot.cli import app as cli

    path = tmp_source("""from fastapi import FastAPI
app = FastAPI()
def scale_tool(x):
    return x * 7
@app.get('/scale')
def scale__tool(x: int) -> int:
    return scale_tool(x)
""")
    loaded = intpot.load(path)
    with pytest.raises(intpot.MissingBindingError, match="collide"):
        loaded.to_cli()
    output = tmp_path / "generated.py"
    result = CliRunner().invoke(cli, ["to", "cli", str(path), "--output", str(output)])
    assert result.exit_code == 1, result.output
    assert "collide" in result.stderr
    assert not output.exists()


def test_imported_endpoint_uses_own_module_not_application_names(tmp_path, monkeypatch):
    origin = tmp_path / "helper_origin.py"
    origin.write_text(
        "FACTOR = 7\ndef scale(x):\n    return x * FACTOR\ndef calc(x: int) -> int:\n    return scale(x)\n"
    )
    source = tmp_path / "application.py"
    source.write_text(
        "from fastapi import FastAPI\nfrom helper_origin import calc\napp = FastAPI()\nFACTOR = 999\ndef scale(x):\n    return 999\napp.get('/calc')(calc)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    loaded = intpot.load(source)
    code = loaded.to_cli()
    assert "999" not in code
    namespace: dict[str, Any] = {"__name__": "owning_module"}
    exec(compile(code, "<cli>", "exec", dont_inherit=True), namespace)
    result = CliRunner().invoke(namespace["app"], ["3"])
    assert result.exit_code == 0, result.exception
    assert result.stdout == "21\n"


def test_changed_helper_file_is_not_used_as_live_implementation(tmp_source):
    source = tmp_source(
        "from fastapi import FastAPI\napp = FastAPI()\ndef scale(x):\n    return x * 7\n@app.get('/calc')\ndef calc(x: int) -> int:\n    return scale(x)\n"
    )
    loaded = intpot.load(source)
    source.write_text(source.read_text().replace("x * 7", "x * 99"))
    assert TestClient(loaded.app).get("/calc", params={"x": 3}).json() == 21
    with pytest.raises(intpot.MissingBindingError, match="scale"):
        loaded.to_cli()


@pytest.mark.parametrize(
    "helper",
    [
        "def decorator(fn):\n    return fn\n@decorator\ndef scale(x):\n    return x * 7\n",
        "def factory():\n    factor = 7\n    def inner(x):\n        return x * factor\n    return inner\nscale = factory()\n",
        "FACTOR = [7]\ndef scale(x):\n    return x * FACTOR[0]\n",
    ],
)
def test_unbounded_helpers_remain_refused(tmp_source, helper):
    loaded = intpot.load(
        tmp_source(
            "from fastapi import FastAPI\napp = FastAPI()\n"
            + helper
            + "@app.get('/calc')\ndef calc(x: int) -> int:\n    return scale(x)\n"
        )
    )
    assert TestClient(loaded.app).get("/calc", params={"x": 3}).json() == 21
    with pytest.raises(intpot.MissingBindingError, match="scale"):
        loaded.to_cli(allow_scaffold=True)


def test_framework_output_helpers_remain_outside_plain_helper_subset(tmp_source):
    loaded = intpot.load(
        tmp_source("""import typer
app = typer.Typer(add_completion=False)
def emit(x):
    typer.echo(x * 7)
@app.command()
def calc(x: int):
    emit(x)
""")
    )
    source = CliRunner().invoke(loaded.app, ["3"])
    assert source.stdout == "21\n"
    with pytest.raises(intpot.MissingBindingError, match="emit"):
        loaded.to_api()


@pytest.mark.parametrize("target", ["api", "mcp"])
def test_cli_helper_recovery_preserves_output_adaptation(tmp_source, target):
    loaded = intpot.load(
        tmp_source("""import typer
app = typer.Typer(add_completion=False)
FACTOR = 7
def scale(x):
    return x * FACTOR
@app.command()
def calc(x: int):
    typer.echo(str(scale(x)))
""")
    )
    assert CliRunner().invoke(loaded.app, ["3"]).stdout == "21\n"
    namespace: dict[str, Any] = {"__name__": "cli_source_helpers"}
    exec(
        compile(
            getattr(loaded, "to_" + target)(), "<target>", "exec", dont_inherit=True
        ),
        namespace,
    )
    if target == "api":
        response = TestClient(namespace["app"]).post("/calc", json=3)
        assert response.status_code == 200, response.text
        assert response.json() == {"result": "21"}
    else:
        assert (
            asyncio.run(namespace["mcp"].call_tool("calc", {"x": 3})).content[0].text
            == "21"
        )


def test_recovered_constant_cannot_overwrite_generated_typing_binding(
    tmp_source, tmp_path
):
    loaded = intpot.load(
        tmp_source("""from fastapi import FastAPI
app = FastAPI()
Optional = 7
def scale(x):
    return x * Optional
@app.get('/calc')
def calc(x: int | None = None) -> int:
    return scale(x or 3)
""")
    )
    assert TestClient(loaded.app).get("/calc").json() == 21
    output = tmp_path / "generated.py"
    with pytest.raises(intpot.MissingBindingError, match="Optional"):
        loaded.write(output, "mcp")
    assert not output.exists()


def test_async_helpers_execute_in_generated_consumers(tmp_source):
    loaded = intpot.load(
        tmp_source("""from fastapi import FastAPI
app = FastAPI()
FACTOR = 7
async def scale(x: int) -> int:
    return x * FACTOR
@app.get('/calc')
async def calc(x: int) -> int:
    return await scale(x)
""")
    )
    assert TestClient(loaded.app).get("/calc", params={"x": 3}).json() == 21
    for target in ("cli", "mcp"):
        namespace: dict[str, Any] = {"__name__": "async_helpers"}
        exec(
            compile(
                getattr(loaded, "to_" + target)(), "<target>", "exec", dont_inherit=True
            ),
            namespace,
        )
        if target == "cli":
            result = CliRunner().invoke(namespace["app"], ["3"])
            assert result.exit_code == 0, result.exception
            assert result.stdout == "21\n"
        else:
            assert (
                asyncio.run(namespace["mcp"].call_tool("calc", {"x": 3}))
                .content[0]
                .text
                == "21"
            )


@pytest.mark.parametrize(
    "binding",
    [
        "FACTOR = (1,)\nglobals()['FACTOR'] = (True,)\ndef scale(x):\n    return type(FACTOR[0]).__name__\n",
        "def scale(x, factor=1):\n    return type(factor).__name__\nscale.__defaults__ = (True,)\n",
    ],
)
def test_equal_but_different_literal_types_are_not_recovered(tmp_source, binding):
    loaded = intpot.load(
        tmp_source(
            "from fastapi import FastAPI\napp=FastAPI()\n"
            + binding
            + "@app.get('/calc')\ndef calc(x: int = 3) -> str:\n    return scale(x)\n"
        )
    )
    assert TestClient(loaded.app).get("/calc").json() == "bool"
    with pytest.raises(intpot.MissingBindingError, match="scale"):
        loaded.to_cli()


def test_recovered_import_cannot_replace_generated_initialization_builtin(tmp_source):
    loaded = intpot.load(
        tmp_source("""from fastapi import FastAPI
from math import ceil as object
app = FastAPI()
def scale(x):
    return object(x) * 7
@app.get('/calc')
def calc(x: int) -> int:
    return scale(x)
""")
    )
    assert TestClient(loaded.app).get("/calc", params={"x": 3}).json() == 21
    with pytest.raises(intpot.MissingBindingError, match="object"):
        loaded.to_mcp()
