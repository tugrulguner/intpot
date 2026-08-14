"""Generated code must parse, whatever the source app contains.

Descriptions, parameter names and project names all come from someone else's
code. Each of these produced a file that would not compile, and every existing
test passed because they assert on the generated *string* rather than compiling
it.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from intpot.cli import app as cli_app
from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.generators.mcp import MCPGenerator
from intpot.core.models import (
    ParameterInfo,
    ToolInfo,
    deduplicate_identifiers,
    sanitize_identifier,
)

_GENERATORS = [
    pytest.param(CLIGenerator, id="cli"),
    pytest.param(APIGenerator, id="api"),
    pytest.param(MCPGenerator, id="mcp"),
]

# Each of these, dropped into a hand-quoted string literal, ends the literal
# early or changes its meaning.
_HOSTILE_TEXT = [
    pytest.param('He said "hi"', id="double-quote"),
    pytest.param("It's fine", id="single-quote"),
    pytest.param("line one\nline two", id="newline"),
    pytest.param("a backslash \\ here", id="backslash"),
    pytest.param('ends with a quote "', id="trailing-quote"),
    pytest.param('a """ triple quote', id="triple-quote"),
    pytest.param("tab\tseparated", id="tab"),
    pytest.param("unicode — em dash, café", id="unicode"),
]


def _tool(description: str = "", param_description: str = "") -> ToolInfo:
    return ToolInfo(
        name="demo",
        description=description,
        parameters=[
            ParameterInfo(
                name="x", type_annotation="str", description=param_description
            )
        ],
        return_type="dict",
        function_body="return {'x': x}",
    )


@pytest.mark.parametrize("generator", _GENERATORS)
@pytest.mark.parametrize("text", _HOSTILE_TEXT)
def test_a_hostile_description_still_compiles(generator, text: str) -> None:
    source = generator().generate([_tool(description=text)])

    compile(source, "<generated>", "exec")


@pytest.mark.parametrize("generator", _GENERATORS)
@pytest.mark.parametrize("text", _HOSTILE_TEXT)
def test_a_hostile_parameter_description_still_compiles(generator, text: str) -> None:
    source = generator().generate([_tool(param_description=text)])

    compile(source, "<generated>", "exec")


@pytest.mark.parametrize("generator", _GENERATORS)
def test_the_description_survives_into_the_generated_module(generator) -> None:
    """Escaping must not silently mangle the text it protects."""
    text = 'He said "hi" and left'
    source = generator().generate([_tool(description=text, param_description=text)])

    namespace: dict[str, object] = {}
    exec(compile(source, "<generated>", "exec"), namespace)

    assert 'He said "hi" and left' in source


# ---------------------------------------------------------------------------
# Identifier collisions
# ---------------------------------------------------------------------------


def test_parameters_that_sanitise_onto_one_name_are_made_unique() -> None:
    """`a-b` and `a_b` both sanitise to `a_b` — a duplicate function argument."""
    tool = ToolInfo(
        name="f",
        parameters=[
            ParameterInfo(name="a-b"),
            ParameterInfo(name="a_b"),
            ParameterInfo(name="a.b"),
        ],
        function_body="return a_b",
    )

    assert [p.name for p in tool.parameters] == ["a_b", "a_b_2", "a_b_3"]


@pytest.mark.parametrize("generator", _GENERATORS)
def test_colliding_parameter_names_still_compile(generator) -> None:
    tool = ToolInfo(
        name="f",
        parameters=[ParameterInfo(name="a-b"), ParameterInfo(name="a_b")],
        return_type="dict",
        function_body="return {}",
    )

    compile(generator().generate([tool]), "<generated>", "exec")


def test_deduplicate_skips_over_a_name_that_is_already_taken() -> None:
    assert deduplicate_identifiers(["a", "a", "a_2", "a"]) == [
        "a",
        "a_2",
        "a_2_2",
        "a_3",
    ]


def test_a_valid_unicode_identifier_is_left_alone() -> None:
    """Python 3 allows them, and mangling invented collisions."""
    assert sanitize_identifier("café") == "café"
    assert sanitize_identifier("δelta") == "δelta"


def test_sanitising_still_handles_the_cases_it_always_did() -> None:
    assert sanitize_identifier("class") == "class_"
    assert sanitize_identifier("my-tool.v2") == "my_tool_v2"
    assert sanitize_identifier("123fn") == "_123fn"
    assert sanitize_identifier("---") == "_"
    assert sanitize_identifier("") == "_"


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ['my"app', "my'app", "app\nname"])
def test_init_rejects_names_that_would_break_the_scaffold(
    name: str, tmp_path, monkeypatch
) -> None:
    """The name lands in a docstring and a string literal in the generated file."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli_app, ["init", name, "--type", "mcp"])

    assert result.exit_code == 1
    assert "quotes or control characters" in result.output
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("project_type", ["mcp", "cli", "api"])
def test_scaffolded_projects_compile(project_type: str, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli_app, ["init", "good-name", "--type", project_type])

    assert result.exit_code == 0, result.output
    written = list((tmp_path / "good-name").glob("*.py"))
    assert written, "scaffold produced no Python files"
    for path in written:
        compile(path.read_text(), str(path), "exec")
