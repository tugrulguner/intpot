"""Tests for the CLI generator."""

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from intpot.core.generators.cli import CLIGenerator
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def test_generate_cli_app():
    tools = [
        ToolInfo(
            name="add",
            description="Add two numbers.",
            parameters=[
                ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
                ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
            ],
            return_type="int",
        ),
        ToolInfo(
            name="greet",
            description="Greet someone.",
            parameters=[
                ParameterInfo(name="name", type_annotation="str", default=_SENTINEL),
                ParameterInfo(name="greeting", type_annotation="str", default="Hello"),
            ],
        ),
    ]

    code = CLIGenerator().generate(tools)

    assert "import typer as _intpot_cli_typer" in code
    assert "app = _intpot_cli_typer.Typer()" in code
    assert "@app.command(name='add')" in code
    assert "@app.command(name='greet')" in code
    assert "def add(" in code
    assert "def greet(" in code
    assert "_intpot_cli_typer.Argument(..." in code
    assert "_intpot_cli_typer.Option('Hello'" in code


def test_generate_empty():
    code = CLIGenerator().generate([])
    assert "import typer as _intpot_cli_typer" in code
    assert "app = _intpot_cli_typer.Typer()" in code


def _run_generated(code: str, args: list[str]) -> Any:
    """Execute generated CLI code and invoke it, returning the Typer result."""
    namespace: dict[str, Any] = {}
    exec(compile(code, "<generated>", "exec"), namespace)
    return CliRunner().invoke(namespace["app"], args)


def test_generated_cli_prints_the_return_value():
    """Typer discards return values, so a preserved body needs an explicit echo."""
    tools = [
        ToolInfo(
            name="add",
            description="Add two numbers.",
            parameters=[
                ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
                ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
            ],
            return_type="int",
            function_body="return a + b",
        ),
    ]

    result = _run_generated(CLIGenerator().generate(tools), ["2", "3"])

    assert result.exit_code == 0
    assert result.output.strip() == "5"


def test_generated_cli_runs_an_async_body():
    """`async def` under @app.command() is never awaited, so the body is driven
    through asyncio.run from a synchronous command instead."""
    tools = [
        ToolInfo(
            name="fetch",
            description="Fetch a URL.",
            parameters=[
                ParameterInfo(name="url", type_annotation="str", default=_SENTINEL),
            ],
            return_type="str",
            is_async=True,
            function_body='return f"fetched {url}"',
        ),
    ]

    result = _run_generated(CLIGenerator().generate(tools), ["example.com"])

    assert result.exit_code == 0
    assert "fetched example.com" in result.output


def test_generated_cli_stays_quiet_when_the_body_returns_nothing():
    """A body that echoes itself must not also print a bare `None`."""
    tools = [
        ToolInfo(
            name="log",
            description="Log a message.",
            parameters=[
                ParameterInfo(name="msg", type_annotation="str", default=_SENTINEL),
            ],
            return_type="None",
            function_body="typer.echo(msg)",
            source_imports=["import typer"],
        ),
    ]

    result = _run_generated(CLIGenerator().generate(tools), ["hello"])

    assert result.exit_code == 0
    assert result.output.strip() == "hello"


def test_generated_cli_splits_mixed_imports_and_keeps_a_used_framework_utility():
    tool = ToolInfo(
        name="status_code",
        description="Return a status code.",
        return_type="int",
        function_body="return http_status.HTTP_200_OK",
        source_imports=[
            "from fastapi import Body, status as http_status",
        ],
    )

    code = CLIGenerator().generate([tool])
    result = _run_generated(code, [])

    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "200"
    assert "from fastapi import status as http_status" in code
    assert "import Body" not in code


def test_generated_cli_drops_an_unused_source_framework_import():
    tool = ToolInfo(
        name="greet",
        description="Greet someone.",
        parameters=[
            ParameterInfo(name="name", type_annotation="str", default=_SENTINEL),
        ],
        return_type="str",
        function_body="return name",
        source_imports=["import typer"],
    )

    code = CLIGenerator().generate([tool])

    assert code.count("import typer") == 1


def test_generated_cli_framework_import_does_not_overwrite_a_source_alias():
    tool = ToolInfo(
        name="root",
        description="Return a square root.",
        return_type="float",
        function_body="return typer.sqrt(9)",
        source_imports=["import math as typer"],
    )

    code = CLIGenerator().generate([tool])
    result = _run_generated(code, [])

    assert "import math as typer" in code
    assert "import typer as _intpot_cli_typer" in code
    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "3.0"


def test_generated_cli_rejects_a_retained_app_binding():
    tool = ToolInfo(
        name="uses_app",
        description="Use a source app binding.",
        return_type="str",
        function_body="return app.__name__",
        source_imports=["import math as app"],
    )

    try:
        CLIGenerator().generate([tool])
    except ValueError as error:
        assert "collide with generated names: app" in str(error)
    else:
        raise AssertionError("expected a generated-binding collision")


def test_generated_cli_does_not_treat_a_literal_string_as_a_forward_reference():
    tool = ToolInfo(
        name="literal_status",
        description="Return a literal status.",
        return_type='Annotated[Literal["status"], "status"]',
        function_body='return "status"',
        source_imports=[
            "from typing import Annotated, Literal",
            "from fastapi import status",
        ],
    )

    code = CLIGenerator().generate([tool])
    result = _run_generated(code, [])

    assert "from fastapi import status" not in code
    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "status"


def test_generated_cli_filters_imports_against_their_own_tool():
    tools = [
        ToolInfo(
            name="constant",
            description="Return one.",
            return_type="int",
            function_body="return 1",
            source_imports=["import zlib as math"],
        ),
        ToolInfo(
            name="floor",
            description="Round down.",
            return_type="int",
            function_body="return math.floor(1.5)",
            source_imports=["import math"],
        ),
    ]

    code = CLIGenerator().generate(tools)
    result = _run_generated(code, ["floor"])

    assert "import zlib as math" not in code
    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "1"


def test_generated_cli_keeps_a_typing_name_used_by_the_body():
    tool = ToolInfo(
        name="has_any",
        description="Check the typing object.",
        return_type="bool",
        function_body="return Any is not None",
        source_imports=["from typing import Any"],
    )

    code = CLIGenerator().generate([tool])
    result = _run_generated(code, [])

    assert "from typing import Any" in code
    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "True"


def test_generated_cli_keeps_a_global_read_by_augmented_assignment():
    tool = ToolInfo(
        name="increment_pi",
        description="Increment pi.",
        return_type="float",
        function_body="global pi\npi += 1\nreturn pi",
        source_imports=["from math import pi"],
    )

    code = CLIGenerator().generate([tool])
    result = _run_generated(code, [])

    assert "from math import pi" in code
    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "4.141592653589793"


def test_generated_cli_keeps_a_global_deleted_by_the_body():
    tool = ToolInfo(
        name="delete_pi",
        description="Delete pi.",
        return_type="str",
        function_body='global pi\ndel pi\nreturn "deleted"',
        source_imports=["from math import pi"],
    )

    code = CLIGenerator().generate([tool])
    result = _run_generated(code, [])

    assert "from math import pi" in code
    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "deleted"
