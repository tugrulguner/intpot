"""Adversarial input tests — verify generated code handles edge cases."""

from __future__ import annotations

from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.generators.mcp import MCPGenerator
from intpot.core.models import (
    _SENTINEL,
    ParameterInfo,
    ToolInfo,
    sanitize_identifier,
)


class TestSanitizeIdentifier:
    def test_python_keyword(self) -> None:
        assert sanitize_identifier("class") == "class_"
        assert sanitize_identifier("for") == "for_"
        assert sanitize_identifier("return") == "return_"

    def test_special_chars(self) -> None:
        result = sanitize_identifier("my-tool.v2")
        assert result.isidentifier()
        assert result == "my_tool_v2"

    def test_digit_start(self) -> None:
        result = sanitize_identifier("123fn")
        assert result.isidentifier()
        assert result == "_123fn"

    def test_empty_name(self) -> None:
        assert sanitize_identifier("") == "_"
        assert sanitize_identifier("   ") == "_"

    def test_all_special_chars(self) -> None:
        result = sanitize_identifier("---")
        assert result == "_"

    def test_unicode_chars(self) -> None:
        result = sanitize_identifier("café")
        assert result.isidentifier() or result == "caf_"

    def test_normal_names_unchanged(self) -> None:
        assert sanitize_identifier("hello_world") == "hello_world"
        assert sanitize_identifier("myFunc") == "myFunc"
        assert sanitize_identifier("x") == "x"


class TestAutoSanitizeOnDataclass:
    def test_tool_info_sanitizes_name(self) -> None:
        tool = ToolInfo(name="my-tool.v2")
        assert tool.name.isidentifier()

    def test_parameter_info_sanitizes_name(self) -> None:
        param = ParameterInfo(name="my-param")
        assert param.name.isidentifier()

    def test_keyword_parameter(self) -> None:
        param = ParameterInfo(name="class")
        assert param.name == "class_"


def _all_generators():
    return [CLIGenerator(), MCPGenerator(), APIGenerator()]


class TestTripleQuotesInDocstrings:
    def test_triple_quotes_compile(self) -> None:
        tool = ToolInfo(
            name="test_tool",
            description='A tool with """ triple quotes',
            parameters=[],
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")


class TestSpecialCharNames:
    def test_special_char_tool_names_compile(self) -> None:
        tool = ToolInfo(
            name="my-tool.v2",  # will be sanitized by __post_init__
            description="A tool with special chars",
            parameters=[
                ParameterInfo(name="my-param", type_annotation="str", default=_SENTINEL)
            ],
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")


class TestVeryLongNames:
    def test_long_name_compiles(self) -> None:
        long_name = "a" * 500
        tool = ToolInfo(name=long_name, description="Long-named tool")
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")


class TestEmptyDocstrings:
    def test_empty_description_compiles(self) -> None:
        tool = ToolInfo(name="empty_desc", description="")
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")


class TestComplexTypes:
    def test_complex_type_imports(self) -> None:
        tool = ToolInfo(
            name="complex_tool",
            description="Uses complex types",
            parameters=[
                ParameterInfo(
                    name="data",
                    type_annotation="Dict[str, List[Union[int, str]]]",
                    default=_SENTINEL,
                ),
            ],
            return_type="Optional[Dict[str, Any]]",
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")
            # Verify typing imports are generated
            assert "from typing import" in code
            assert "Dict" in code
            assert "List" in code
            assert "Union" in code

    def test_basic_types_no_typing_import(self) -> None:
        tool = ToolInfo(
            name="basic_tool",
            parameters=[
                ParameterInfo(name="x", type_annotation="int"),
                ParameterInfo(name="y", type_annotation="str"),
            ],
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")
            assert "from typing import" not in code


class TestMultilineDescriptions:
    def test_multiline_description_compiles(self) -> None:
        tool = ToolInfo(
            name="multi_desc",
            description="Line 1\nLine 2\nLine 3",
            parameters=[],
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")


class TestAsyncTools:
    def test_async_tool_compiles(self) -> None:
        tool = ToolInfo(
            name="async_tool",
            description="An async tool",
            is_async=True,
            parameters=[
                ParameterInfo(name="x", type_annotation="int"),
            ],
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")

    def test_async_tool_stays_async_for_mcp_and_api(self) -> None:
        """MCP and FastAPI both await handlers, so the async marker is preserved."""
        from intpot.core.generators.api import APIGenerator
        from intpot.core.generators.mcp import MCPGenerator

        tool = ToolInfo(name="async_tool", description="An async tool", is_async=True)

        for gen in (MCPGenerator(), APIGenerator()):
            assert "async def async_tool" in gen.generate([tool])

    def test_async_command_is_not_emitted_for_cli(self) -> None:
        """Typer cannot run an `async def` command — it would never be awaited.

        The generated command stays synchronous; when a body is preserved it is
        driven through asyncio.run instead.
        """
        from intpot.core.generators.cli import CLIGenerator

        tool = ToolInfo(
            name="async_tool",
            description="An async tool",
            is_async=True,
            function_body="return 42",
        )

        code = CLIGenerator().generate([tool])

        assert "async def _async_tool_impl(" in code
        assert "asyncio.run(_async_tool_impl())" in code
        assert "async def async_tool(" not in code


class TestFunctionBody:
    def test_function_body_in_output(self) -> None:
        tool = ToolInfo(
            name="body_tool",
            description="Tool with body",
            function_body="return x + 1",
            parameters=[
                ParameterInfo(name="x", type_annotation="int"),
            ],
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            compile(code, "<string>", "exec")
            assert "return x + 1" in code
            assert "# TODO: implement" not in code

    def test_no_body_shows_todo(self) -> None:
        tool = ToolInfo(
            name="stub_tool",
            description="Tool without body",
            parameters=[],
        )
        for gen in _all_generators():
            code = gen.generate([tool])
            assert "# TODO: implement" in code


class TestRoutePath:
    def test_route_path_in_api_output(self) -> None:
        tool = ToolInfo(
            name="get_users",
            description="Get users",
            route_path="/api/v1/users",
            http_method="GET",
        )
        gen = APIGenerator()
        code = gen.generate([tool])
        compile(code, "<string>", "exec")
        assert "/api/v1/users" in code

    def test_default_route_path(self) -> None:
        tool = ToolInfo(
            name="get_users",
            description="Get users",
            http_method="GET",
        )
        gen = APIGenerator()
        code = gen.generate([tool])
        compile(code, "<string>", "exec")
        assert "/get_users" in code


class TestLeadingUnderscores:
    def test_leading_underscore_is_preserved(self) -> None:
        """Stripping it collapsed `_name` onto `name`, so two distinct
        parameters could share one identifier in the generated code."""
        assert sanitize_identifier("_name") == "_name"
        assert sanitize_identifier("_name") != sanitize_identifier("name")

    def test_dunder_survives_as_a_distinct_name(self) -> None:
        assert sanitize_identifier("__init__") == "_init_"
        assert sanitize_identifier("__init__").isidentifier()

    def test_underscore_runs_still_collapse(self) -> None:
        assert sanitize_identifier("user__id") == "user_id"
        assert sanitize_identifier("---") == "_"
