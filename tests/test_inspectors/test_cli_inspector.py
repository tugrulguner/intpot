"""Tests for the CLI inspector."""

from __future__ import annotations

import typer

from intpot.core.inspectors.cli import CLIInspector


def test_inspect_typer_commands():
    app = typer.Typer()

    @app.command()
    def add(
        a: int = typer.Argument(..., help="First number"),
        b: int = typer.Argument(..., help="Second number"),
    ) -> None:
        """Add two numbers."""
        pass

    @app.command()
    def greet(
        name: str = typer.Argument(..., help="Name"),
        greeting: str = typer.Option("Hello", help="Greeting"),
    ) -> None:
        """Greet someone."""
        pass

    inspector = CLIInspector()
    tools = inspector.inspect(app)

    assert len(tools) == 2

    add_tool = next(t for t in tools if t.name == "add")
    assert add_tool.description == "Add two numbers."
    assert len(add_tool.parameters) == 2
    assert add_tool.parameters[0].name == "a"
    assert add_tool.parameters[0].type_annotation == "int"
    assert add_tool.parameters[0].required
    assert add_tool.parameters[0].description == "First number"

    greet_tool = next(t for t in tools if t.name == "greet")
    assert greet_tool.parameters[1].name == "greeting"
    assert greet_tool.parameters[1].default == "Hello"
    assert not greet_tool.parameters[1].required


def test_inspect_empty_typer():
    app = typer.Typer()
    inspector = CLIInspector()
    tools = inspector.inspect(app)
    assert tools == []


# ---------------------------------------------------------------------------
# Vendored-click compatibility
#
# Typer 0.27 ships its own copy of click as `typer._click`, so a Typer app's
# objects are not instances of anything in the standalone `click` package.
# Every isinstance/identity check against click silently stopped matching:
# `intpot inspect` reported "No tools found" for every Typer app, and had the
# groups been found, every parameter would have been typed `str`.
#
# These stubs inherit from nothing, so they reproduce that on any installed
# typer version rather than only on the one CI happens to pin.
# ---------------------------------------------------------------------------


class _StubType:
    """Stands in for a vendored click ParamType."""

    def __init__(self, name: str) -> None:
        self.name = name


class _StubParam:
    def __init__(self, name, type_name, required=True, default=None, help_=""):
        self.name = name
        self.type = _StubType(type_name)
        self.required = required
        self.default = default
        self.help = help_


class _StubCommand:
    def __init__(self, name, params=None, help_=""):
        self.name = name
        self.params = params or []
        self.help = help_
        self.callback = None


class _StubGroup:
    def __init__(self, commands):
        self.name = "root"
        self.commands = commands


def test_a_group_that_is_not_a_click_subclass_is_still_walked():
    group = _StubGroup({"greet": _StubCommand("greet", help_="Greet someone.")})

    tools = CLIInspector().inspect(group)

    assert [t.name for t in tools] == ["greet"]
    assert tools[0].description == "Greet someone."


def test_nested_groups_that_are_not_click_subclasses_are_walked():
    inner = _StubGroup({"child": _StubCommand("child")})
    outer = _StubGroup({"parent": inner})

    tools = CLIInspector().inspect(outer)

    assert [t.name for t in tools] == ["parent_child"]


def test_parameter_types_are_matched_structurally_not_by_identity():
    """Both vocabularies must map: click says 'integer', typer says 'int'."""
    command = _StubCommand(
        "calc",
        params=[
            _StubParam("a", "int"),  # typer's vendored click
            _StubParam("b", "integer"),  # click's own
            _StubParam("c", "float"),
            _StubParam("d", "boolean"),
            _StubParam("e", "text"),  # click's name for str
            _StubParam("f", "str"),
        ],
    )

    tools = CLIInspector().inspect(_StubGroup({"calc": command}))
    types = {p.name: p.type_annotation for p in tools[0].parameters}

    assert types == {
        "a": "int",
        "b": "int",
        "c": "float",
        "d": "bool",
        "e": "str",
        "f": "str",
    }


def test_an_unrecognised_parameter_type_falls_back_to_str():
    command = _StubCommand("pick", params=[_StubParam("choice", "choice")])

    tools = CLIInspector().inspect(_StubGroup({"pick": command}))

    assert tools[0].parameters[0].type_annotation == "str"
