"""Roundtrip conversion tests — verify tools survive conversion cycles."""

from __future__ import annotations

import asyncio
import builtins
import importlib.util
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any, get_type_hints

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from typer.testing import CliRunner

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

    def test_mcp_to_api_preserves_schema_description_and_runs(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from typing import Annotated

            from fastmcp import FastMCP
            from pydantic import Field

            mcp = FastMCP("test-server")

            @mcp.tool()
            def greet(
                name: Annotated[str, Field(description="Person to greet.")],
            ) -> str:
                return f"Hello, {name}!"
        """)
        path = tmp_path / "described_mcp.py"
        path.write_text(source)

        api_code = load(path).to_api()

        assert "name: str" in api_code
        generated = ModuleType("generated_described_api")
        exec(
            compile(api_code, "generated_described_api.py", "exec"), generated.__dict__
        )
        client = TestClient(generated.app)
        operation = client.get("/openapi.json").json()["paths"]["/greet"]["post"]
        body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        assert body_schema["description"] == "Person to greet."
        response = client.post("/greet", json="Ada")
        assert response.status_code == 200
        assert response.json() == {"result": "Hello, Ada!"}

    def test_mcp_to_cli_keeps_a_required_import_containing_a_framework_name(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            import copy as BodyBuilder

            from fastmcp import FastMCP

            mcp = FastMCP("copy-server")

            @mcp.tool()
            def copy_value(value: str) -> str:
                return BodyBuilder.copy(value)
        """)
        path = tmp_path / "copy_mcp.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_copy_cli")
        exec(
            compile(cli_code, "generated_copy_cli.py", "exec", dont_inherit=True),
            generated.__dict__,
        )

        result = CliRunner().invoke(generated.app, ["hello"])

        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "hello"

    def test_runtime_app_to_cli_keeps_a_quoted_annotation_import(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from pathlib import Path

            from intpot import App

            app = App("path-app")

            @app.tool()
            def empty_paths() -> list["Path"]:
                return []
        """)
        path = tmp_path / "runtime_app.py"
        path.write_text(source)

        spec = importlib.util.spec_from_file_location("path_app", path)
        assert spec is not None and spec.loader is not None
        source_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source_module)
        cli_code = source_module.app.eject("cli")
        generated = ModuleType("generated_path_cli")
        exec(
            compile(cli_code, "generated_path_cli.py", "exec", dont_inherit=True),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app)

        assert "from pathlib import Path" in cli_code
        assert get_type_hints(generated._empty_paths_impl)["return"] == list[Path]
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "[]"


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

    def test_cli_to_mcp_drops_typer_after_echo_is_translated(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "cli_app.py"
        path.write_text(CLI_SOURCE)

        mcp_code = load(path).to_mcp()
        generated = ModuleType("generated_mcp_without_typer")
        exec(
            compile(
                mcp_code,
                "generated_mcp_without_typer.py",
                "exec",
                dont_inherit=True,
            ),
            generated.__dict__,
        )
        result = asyncio.run(
            generated.mcp.call_tool(
                "greet",
                {"name": "Ada", "greeting": "Welcome"},
            )
        )

        assert "import typer" not in mcp_code
        assert result.is_error is False
        assert result.structured_content == {"result": "Welcome, Ada!"}


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

    def test_api_to_cli_drops_an_import_shadowed_by_a_parameter(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        source = textwrap.dedent("""\
            from fastapi import FastAPI, status

            app = FastAPI()

            @app.get("/echo")
            def echo(status: str) -> str:
                return status
        """)
        path = tmp_path / "shadowed_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_shadowed_cli")
        real_import = builtins.__import__

        def target_only_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "fastapi" or name.startswith("fastapi."):
                raise ImportError("generated CLI must not depend on FastAPI")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", target_only_import)
        exec(
            compile(cli_code, "generated_shadowed_cli.py", "exec", dont_inherit=True),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app, ["ok"])

        assert "from fastapi import status" not in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "ok"

    def test_api_to_cli_imports_with_a_framework_return_annotation(
        self, tmp_path: Path
    ) -> None:
        """The private implementation must not eagerly resolve source-only types.

        ``dont_inherit`` matters here: this test module enables future annotations,
        but a generated file executed by a user does not inherit its compiler flags.
        """
        source = textwrap.dedent("""\
            from fastapi import FastAPI
            from fastapi.responses import HTMLResponse

            app = FastAPI()

            @app.get("/hello", response_class=HTMLResponse)
            def hello() -> HTMLResponse:
                return "<h1>Hello</h1>"
        """)
        path = tmp_path / "html_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_html_cli")
        exec(
            compile(
                cli_code,
                "generated_html_cli.py",
                "exec",
                dont_inherit=True,
            ),
            generated.__dict__,
        )

        result = CliRunner().invoke(generated.app)

        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "<h1>Hello</h1>"

    def test_api_to_cli_helper_aliases_do_not_collide_with_parameters(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/sync")
            def sync_echo(_intpot_cli_typer: str) -> str:
                return _intpot_cli_typer

            @app.get("/async")
            async def async_echo(_intpot_cli_asyncio: str) -> str:
                return _intpot_cli_asyncio
        """)
        path = tmp_path / "helper_alias_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_helper_alias_cli")
        exec(
            compile(cli_code, "generated_helper_alias_cli.py", "exec"),
            generated.__dict__,
        )
        sync_result = CliRunner().invoke(generated.app, ["sync-echo", "hello"])
        async_result = CliRunner().invoke(generated.app, ["async-echo", "world"])

        assert sync_result.exit_code == 0, sync_result.exception
        assert sync_result.output.strip() == "hello"
        assert async_result.exit_code == 0, async_result.exception
        assert async_result.output.strip() == "world"

    def test_api_to_cli_keeps_an_augmented_assignment_global_read(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from math import pi
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/increment")
            def increment() -> str:
                global pi
                pi += 1
                return "done"
        """)
        path = tmp_path / "augmented_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_augmented_cli")
        exec(
            compile(cli_code, "generated_augmented_cli.py", "exec"), generated.__dict__
        )
        result = CliRunner().invoke(generated.app)

        assert "from math import pi" in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "done"

    def test_api_to_cli_keeps_a_class_scope_fallback_read(self, tmp_path: Path) -> None:
        source = textwrap.dedent("""\
            from math import pi
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/pi")
            def class_pi() -> float:
                class Constants:
                    pi = pi
                return Constants.pi
        """)
        path = tmp_path / "class_scope_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_class_scope_cli")
        exec(
            compile(cli_code, "generated_class_scope_cli.py", "exec"),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app)

        assert "from math import pi" in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "3.141592653589793"

    def test_api_to_cli_keeps_a_nested_quoted_annotation_import(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from decimal import Decimal
            import typing
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/annotation")
            def nested_annotation() -> str:
                def inner(value: "Decimal") -> "Decimal":
                    return value
                return typing.get_type_hints(inner)["value"].__name__
        """)
        path = tmp_path / "nested_annotation_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_nested_annotation_cli")
        exec(
            compile(cli_code, "generated_nested_annotation_cli.py", "exec"),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app)

        assert "from decimal import Decimal" in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "Decimal"

    def test_api_to_cli_drops_an_import_shadowed_earlier_in_a_class(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from math import pi as endpoint
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/")
            def endpoint() -> int:
                class Counter:
                    endpoint = 1
                    endpoint += 1
                return Counter.endpoint
        """)
        path = tmp_path / "class_shadow_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_class_shadow_cli")
        exec(
            compile(cli_code, "generated_class_shadow_cli.py", "exec"),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app)

        assert "from math import pi as endpoint" not in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "2"

    def test_api_to_cli_keeps_a_class_loop_fallback_read(self, tmp_path: Path) -> None:
        source = textwrap.dedent("""\
            from math import pi
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/")
            def endpoint() -> float:
                class Values:
                    for pi in (pi,):
                        pass
                return Values.pi
        """)
        path = tmp_path / "class_loop_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_class_loop_cli")
        exec(
            compile(cli_code, "generated_class_loop_cli.py", "exec"),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app)

        assert "from math import pi" in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "3.141592653589793"

    def test_api_to_cli_keeps_a_destructured_global_delete(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from math import pi as doomed
            from fastapi import FastAPI

            app = FastAPI()

            @app.delete("/")
            def delete_global() -> str:
                global doomed
                del (doomed,)
                return "deleted"
        """)
        path = tmp_path / "destructured_delete_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_destructured_delete_cli")
        exec(
            compile(cli_code, "generated_destructured_delete_cli.py", "exec"),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app)

        assert "from math import pi as doomed" in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "deleted"

    def test_api_to_cli_keeps_a_class_method_default_fallback(
        self, tmp_path: Path
    ) -> None:
        source = textwrap.dedent("""\
            from math import pi as value
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/")
            def endpoint() -> float:
                class Values:
                    def value(self, default=value):
                        return default
                return Values().value()
        """)
        path = tmp_path / "class_method_default_api.py"
        path.write_text(source)

        cli_code = load(path).to_cli()
        generated = ModuleType("generated_class_method_default_cli")
        exec(
            compile(cli_code, "generated_class_method_default_cli.py", "exec"),
            generated.__dict__,
        )
        result = CliRunner().invoke(generated.app)

        assert "from math import pi as value" in cli_code
        assert result.exit_code == 0, result.exception
        assert result.output.strip() == "3.141592653589793"

    def test_api_to_cli_keeps_class_fallbacks_across_binding_forms(
        self, tmp_path: Path
    ) -> None:
        cases = {
            "with": (
                "from contextlib import nullcontext as cm",
                'with cm("ok") as cm:\n    value = cm',
                "from contextlib import nullcontext as cm",
                "ok",
            ),
            "named_expression": (
                "from math import pi as m",
                "value = (m := m)",
                "from math import pi as m",
                "3.141592653589793",
            ),
            "conditional": (
                "from math import pi",
                "if False:\n    pi = 0\nvalue = pi",
                "from math import pi",
                "3.141592653589793",
            ),
            "while": (
                "from math import pi",
                "while False:\n    pi = 0\nvalue = pi",
                "from math import pi",
                "3.141592653589793",
            ),
            "try": (
                "from math import pi",
                "try:\n    if False:\n        pi = 0\nexcept Exception:\n    pass\nvalue = pi",
                "from math import pi",
                "3.141592653589793",
            ),
            "match": (
                "from math import pi",
                "match pi:\n    case pi:\n        value = pi",
                "from math import pi",
                "3.141592653589793",
            ),
            "annotation_only": (
                "from math import pi",
                "pi: float\nvalue = pi",
                "from math import pi",
                "3.141592653589793",
            ),
            "exception_target_cleanup": (
                "from math import pi",
                "pi = 1\ntry:\n    raise ValueError\nexcept ValueError as pi:\n    pass\nvalue = pi",
                "from math import pi",
                "3.141592653589793",
            ),
        }
        for case_name, (
            import_line,
            class_body,
            expected_import,
            expected,
        ) in cases.items():
            source = (
                f"{import_line}\n"
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                '@app.get("/")\n'
                "def endpoint():\n"
                "    class Values:\n"
                f"{textwrap.indent(class_body, '        ')}\n"
                "    return Values.value\n"
            )
            path = tmp_path / f"class_{case_name}_api.py"
            path.write_text(source)

            cli_code = load(path).to_cli()
            generated = ModuleType(f"generated_class_{case_name}_cli")
            exec(
                compile(cli_code, f"generated_{case_name}.py", "exec"),
                generated.__dict__,
            )
            result = CliRunner().invoke(generated.app)

            assert expected_import in cli_code, case_name
            assert result.exit_code == 0, (case_name, result.exception)
            assert result.output.strip() == expected, case_name


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
