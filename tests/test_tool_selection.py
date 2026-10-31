from __future__ import annotations

import pytest

from intpot.converter import IntpotApp, MissingFunctionBodyError
from intpot.core.models import ApplicationSchema, SourceType, ToolSchema


def test_select_is_missing_regression() -> None:
    app = IntpotApp(SourceType.API, object())
    app.__dict__["schema"] = ApplicationSchema(
        name="sample",
        source_type=SourceType.API,
        tools=(ToolSchema(name="first"), ToolSchema(name="second")),
    )

    selected = app.select("second")

    assert [tool.name for tool in selected.schema.tools] == ["second"]


def test_selection_preserves_schema_and_framework_app() -> None:
    original = object()
    schema = ApplicationSchema(
        name="sample",
        source_type=SourceType.API,
        tools=(
            ToolSchema(name="one", description="1"),
            ToolSchema(name="two", description="2"),
        ),
    )
    app = IntpotApp(SourceType.API, original)
    app.__dict__["schema"] = schema

    selected = app.select("two", "one").select("one")

    assert selected is not app
    assert selected.app is original
    assert selected.source_path == app.source_path
    assert selected.schema.name == schema.name
    assert selected.schema.tools == (schema.tools[0],)
    assert app.schema is schema
    assert selected.tools[0] is not app.tools[0]


@pytest.mark.parametrize("names", [(), ("one", "one"), ("missing",)])
def test_selection_rejects_empty_duplicate_and_unknown_names(
    names: tuple[str, ...],
) -> None:
    app = IntpotApp(SourceType.API, object())
    app.__dict__["schema"] = ApplicationSchema(
        name="sample", source_type=SourceType.API, tools=(ToolSchema(name="one"),)
    )
    with pytest.raises(ValueError):
        app.select(*names)


def test_selection_rejects_non_string_name() -> None:
    app = IntpotApp(SourceType.API, object())
    app.__dict__["schema"] = ApplicationSchema(
        name="sample", source_type=SourceType.API, tools=(ToolSchema(name="one"),)
    )
    with pytest.raises(TypeError):
        app.select(1)  # type: ignore[arg-type]


def test_selected_api_consumers_assess_and_refuse_only_selected_tool() -> None:
    app = IntpotApp(SourceType.API, object())
    app.__dict__["schema"] = ApplicationSchema(
        name="sample",
        source_type=SourceType.API,
        tools=(
            ToolSchema(name="bad", function_body=None),
            ToolSchema(name="good", function_body="return 1"),
        ),
    )
    selected = app.select("good")
    assert selected.assess()["body_recovery_complete"] is True
    assert [tool.name for tool in selected.project(SourceType.MCP).tools] == ["good"]


def test_selected_missing_body_still_refuses_before_write(tmp_path) -> None:
    app = IntpotApp(SourceType.API, object())
    app.__dict__["schema"] = ApplicationSchema(
        name="sample", source_type=SourceType.API, tools=(ToolSchema(name="bad"),)
    )
    output = tmp_path / "generated.py"
    with pytest.raises(MissingFunctionBodyError):
        app.select("bad").write(output, "mcp")
    assert not output.exists()


def test_api_and_mcp_generation_include_only_selected_tool() -> None:
    app = IntpotApp(SourceType.CLI, object())
    app.__dict__["schema"] = ApplicationSchema(
        name="sample",
        source_type=SourceType.CLI,
        tools=(
            ToolSchema(name="hidden", function_body="return 0"),
            ToolSchema(name="chosen", function_body="return 1"),
        ),
    )
    selected = app.select("chosen")

    api_code = selected.to_api()
    mcp_code = selected.to_mcp()

    assert "chosen" in api_code and "hidden" not in api_code
    assert "chosen" in mcp_code and "hidden" not in mcp_code


def test_unknown_selection_does_not_create_output_directory(tmp_path) -> None:
    app = IntpotApp(SourceType.API, object())
    app.__dict__["schema"] = ApplicationSchema(
        name="sample", source_type=SourceType.API, tools=(ToolSchema(name="one"),)
    )
    output = tmp_path / "not-created" / "generated.py"
    with pytest.raises(ValueError, match="Unknown tool"):
        app.select("missing").write(output, "mcp")
    assert not output.parent.exists()
