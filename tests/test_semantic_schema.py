"""Tests for Intpot's canonical application schema."""

from __future__ import annotations

import json
import math
import sys
import threading
from collections import deque
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

import intpot
from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.generators.mcp import MCPGenerator
from intpot.core.models import ApplicationSchema, ParamSource, SourceType


def test_load_compiles_an_immutable_application_schema(tmp_source) -> None:
    source = tmp_source(
        """
        from fastmcp import FastMCP

        mcp = FastMCP("weather-tools")

        @mcp.tool()
        def forecast(city: str, days: int = 1) -> str:
            \"\"\"Return a forecast.\"\"\"
            return f"{city}: {days} day(s)"
        """
    )

    loaded = intpot.load(source)
    schema = loaded.schema

    assert isinstance(schema, ApplicationSchema)
    assert schema.name == "weather-tools"
    assert schema.source_type is SourceType.MCP
    assert schema.source_path == source.resolve()
    assert isinstance(schema.tools, tuple)
    assert schema.tools[0].name == "forecast"
    assert isinstance(schema.tools[0].parameters, tuple)
    assert schema.tools[0].parameters[0].name == "city"
    assert schema.tools[0].parameters[0].required

    with pytest.raises(FrozenInstanceError):
        schema.name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        schema.tools[0].name = "changed"  # type: ignore[misc]


def test_public_projection_uses_the_schema_without_mutating_it(tmp_source) -> None:
    source = tmp_source(
        """
        from fastmcp import FastMCP

        mcp = FastMCP("calculator")

        @mcp.tool()
        def add(a: int, b: int) -> int:
            return a + b
        """
    )
    loaded = intpot.load(source)
    original = loaded.schema

    detached_tools = loaded.tools
    detached_tools[0].name = "mutated"
    projected = loaded.project("api")

    assert intpot.ApplicationSchema is ApplicationSchema
    assert intpot.SourceType is SourceType
    assert original.target_type is None
    assert original.tools[0].name == "add"
    assert projected.source_type is SourceType.MCP
    assert projected.target_type is SourceType.API
    assert projected.tools[0].name == "add"
    assert projected.tools[0].return_type == "dict"
    assert projected.tools[0].function_body == "return {'result': a + b}"

    generated = loaded.to_api()
    assert "def add(" in generated
    assert "mutated" not in generated

    with pytest.raises(ValueError, match="expected: cli, mcp, api"):
        loaded.project("python")


def test_runtime_app_meets_conversion_at_the_same_schema() -> None:
    app = intpot.App("inventory")

    @app.tool()
    def lookup(sku: str) -> str:
        return sku.upper()

    schema = app.schema
    detached_tools = app.tools
    detached_tools[0].name = "mutated"

    assert schema.name == "inventory"
    assert schema.source_type is SourceType.PYTHON
    assert schema.tools[0].name == "lookup"
    assert app.schema is schema
    assert "def lookup(" in app.eject("mcp")
    assert "mutated" not in app.eject("mcp")


def test_schema_serializes_required_parameters_without_leaking_the_sentinel(
    tmp_source,
) -> None:
    source = tmp_source(
        """
        import typer

        app = typer.Typer(name="greeter")

        @app.command()
        def greet(name: str, loud: bool = False) -> None:
            typer.echo(name.upper() if loud else name)
        """
    )

    data = intpot.load(source).schema.to_dict()

    assert data["name"] == "greeter"
    assert data["source_type"] == "cli"
    assert data["source_path"] == str(source.resolve())
    assert data["target_type"] is None
    assert data["tools"][0]["parameters"][0] == {
        "name": "name",
        "type_annotation": "str",
        "description": "",
        "param_source": None,
        "required": True,
    }
    assert data["tools"][0]["parameters"][1]["default"] is False


@pytest.mark.parametrize(
    ("generator", "global_name", "attribute"),
    [
        (CLIGenerator(), "app", "info"),
        (APIGenerator(), "app", "title"),
        (MCPGenerator(), "mcp", "name"),
    ],
)
def test_generators_consume_application_schema_and_preserve_its_name(
    generator,
    global_name: str,
    attribute: str,
) -> None:
    app = intpot.App("inventory")

    @app.tool()
    def lookup(sku: str) -> str:
        return sku.upper()

    code = generator.generate(app.schema)
    generated = ModuleType("generated")
    exec(compile(code, "generated.py", "exec"), generated.__dict__)
    framework_app = getattr(generated, global_name)

    if attribute == "info":
        assert framework_app.info.name == "inventory"
    else:
        assert getattr(framework_app, attribute) == "inventory"


def test_schema_detaches_and_freezes_mutable_parameter_defaults() -> None:
    original_default = [{"region": "us"}]
    app = intpot.App("defaults")

    @app.tool()
    def configure(regions: list[dict[str, str]] = original_default) -> int:
        return len(regions)

    schema_default = app.schema.tools[0].parameters[0].default
    original_default[0]["region"] = "eu"

    assert isinstance(schema_default, tuple)
    assert [dict(item) for item in schema_default] == [{"region": "us"}]
    with pytest.raises(TypeError):
        schema_default[0]["region"] = "eu"

    first_compatibility_default = app.tools[0].parameters[0].default
    first_compatibility_default[0]["region"] = "apac"
    second_compatibility_default = app.tools[0].parameters[0].default

    assert second_compatibility_default == [{"region": "eu"}]
    assert app.schema.to_dict()["tools"][0]["parameters"][0]["default"] == {
        "$intpot": {
            "type": "list",
            "items": [
                {
                    "$intpot": {
                        "type": "dict",
                        "items": [{"key": "region", "value": "us"}],
                    }
                }
            ],
        }
    }


def test_public_schema_constructors_freeze_nested_collections() -> None:
    from intpot import ApplicationSchema, ParameterSchema, SourceType, ToolSchema

    default = [{"region": "us"}]
    parameters = [ParameterSchema(name="filters", default=default)]
    dependencies = ["auth"]
    tools = [
        ToolSchema(
            name="search",
            parameters=parameters,  # type: ignore[arg-type]
            dependencies=dependencies,  # type: ignore[arg-type]
        )
    ]

    schema = ApplicationSchema(
        name="catalog",
        source_type=SourceType.PYTHON,
        tools=tools,  # type: ignore[arg-type]
    )
    default[0]["region"] = "eu"
    parameters.clear()
    dependencies.clear()
    tools.clear()

    assert len(schema.tools) == 1
    assert len(schema.tools[0].parameters) == 1
    assert schema.tools[0].dependencies == ("auth",)
    frozen_default = schema.tools[0].parameters[0].default
    assert [dict(item) for item in frozen_default] == [{"region": "us"}]
    with pytest.raises(TypeError):
        frozen_default[0]["region"] = "apac"


def test_parameter_schema_freezes_mutable_defaults_and_rejects_opaque() -> None:
    from intpot import ParameterSchema

    binary = ParameterSchema(name="binary", default=bytearray(b"a"))
    queue = ParameterSchema(name="queue", default=deque(["a"], maxlen=2))

    with pytest.raises(TypeError):
        binary.default[0] = ord("z")
    with pytest.raises(AttributeError):
        queue.default.append("b")

    assert binary.to_info().default == bytearray(b"a")
    assert queue.to_info().default == deque(["a"], maxlen=2)

    class MutableHashable:
        __hash__ = object.__hash__

        def __init__(self) -> None:
            self.value = "a"

    with pytest.raises(TypeError, match="Unsupported parameter default"):
        ParameterSchema(name="opaque", default=MutableHashable())


def test_parameter_schema_normalizes_scalar_subclasses_and_rejects_enums() -> None:
    from intpot import ParameterSchema

    class MutableText(str):
        pass

    text = MutableText("stable")
    text.state = []
    parameter = ParameterSchema(name="text", default=text)
    before = hash(parameter)
    text.state.append("changed")

    assert type(parameter.default) is str
    assert parameter.default == "stable"
    assert hash(parameter) == before

    class MutableValue(Enum):
        item = []  # noqa: RUF012 - adversarial mutable enum payload

    with pytest.raises(TypeError, match="Enum defaults are not supported"):
        ParameterSchema(name="enum", default=MutableValue.item)


def test_parameter_schema_freezes_slice_bounds_and_remains_hashable() -> None:
    from intpot import ParameterSchema

    start: list[str] = []
    parameter = ParameterSchema(name="window", default=slice(start, 2, 1))
    before = hash(parameter)
    start.append("changed")

    assert parameter.to_info().default == slice([], 2, 1)
    assert hash(parameter) == before


def test_schema_equality_distinguishes_source_container_types() -> None:
    from intpot import ParameterSchema

    unequal_pairs = [
        ([], ()),
        (set(), frozenset()),
        (bytearray(b"a"), b"a"),
    ]

    for left, right in unequal_pairs:
        assert ParameterSchema("value", default=left) != ParameterSchema(
            "value", default=right
        )


def test_schema_json_preserves_mixed_mapping_keys() -> None:
    from intpot import ParameterSchema

    data = ParameterSchema("mapping", default={1: "integer", "1": "string"}).to_dict()[
        "default"
    ]
    encoded = json.loads(json.dumps(data))

    assert encoded == {
        "$intpot": {
            "type": "dict",
            "items": [
                {"key": 1, "value": "integer"},
                {"key": "1", "value": "string"},
            ],
        }
    }


def test_runtime_tools_preserve_detached_opaque_compatibility_defaults() -> None:
    class Marker:
        def __init__(self) -> None:
            self.value = "original"

    marker = Marker()
    app = intpot.App("compatibility")

    @app.tool()
    def use_marker(value=marker):
        return value.value

    first = app.tools
    first[0].parameters[0].default.value = "changed"

    assert app.tools[0].parameters[0].default.value == "original"
    with pytest.raises(TypeError, match="Unsupported parameter default"):
        _ = app.schema


def test_runtime_tools_are_stable_before_and_after_schema_access() -> None:
    class MutableText(str):
        pass

    default = MutableText("stable")
    default.state = ["compatibility"]
    app = intpot.App("compatibility")

    @app.tool()
    def show(value=default):
        return value

    before = app.tools[0].parameters[0].default
    _ = app.schema
    after = app.tools[0].parameters[0].default

    assert type(before) is MutableText
    assert type(after) is MutableText
    assert before.state == after.state == ["compatibility"]


def test_runtime_tools_keep_uncloneable_opaque_defaults_available() -> None:
    class SelfCopying:
        def __deepcopy__(self, memo):
            return self

    lock = threading.Lock()
    self_copying = SelfCopying()
    app = intpot.App("opaque-compatibility")

    @app.tool()
    def use(lock_value=lock, self_copying_value=self_copying):
        return lock_value, self_copying_value

    defaults = [parameter.default for parameter in app.tools[0].parameters]

    assert defaults == [lock, self_copying]
    assert defaults[0] is lock
    assert defaults[1] is self_copying


def test_schema_json_strictly_normalizes_non_finite_numbers() -> None:
    from intpot import ParameterSchema

    defaults = {
        "positive": float("inf"),
        "negative": float("-inf"),
        "nan": float("nan"),
        "complex": complex(float("inf"), float("nan")),
    }
    normalized = {
        name: ParameterSchema(name, default=value).to_dict()["default"]
        for name, value in defaults.items()
    }

    json.dumps(normalized, allow_nan=False)
    assert normalized["positive"] == {"$intpot": {"type": "float", "value": "infinity"}}
    assert normalized["negative"] == {
        "$intpot": {"type": "float", "value": "-infinity"}
    }
    assert normalized["nan"] == {"$intpot": {"type": "float", "value": "nan"}}
    assert normalized["complex"] == {
        "$intpot": {
            "type": "complex",
            "real": {"$intpot": {"type": "float", "value": "infinity"}},
            "imag": {"$intpot": {"type": "float", "value": "nan"}},
        }
    }


def test_schema_json_envelopes_preserve_source_types_without_tag_collisions() -> None:
    from intpot import ParameterSchema

    values = {
        "list": [],
        "tuple": (),
        "bytes": b"abc",
        "lookalike": {"type": "bytes", "base64": "YWJj"},
    }
    normalized = {
        name: ParameterSchema(name, default=value).to_dict()["default"]
        for name, value in values.items()
    }

    assert (
        len({json.dumps(value, sort_keys=True) for value in normalized.values()}) == 4
    )
    assert normalized["list"]["$intpot"]["type"] == "list"
    assert normalized["tuple"]["$intpot"]["type"] == "tuple"
    assert normalized["bytes"]["$intpot"]["type"] == "bytes"
    assert normalized["lookalike"]["$intpot"]["type"] == "dict"


def test_frozen_mapping_retrieves_the_identical_nan_key() -> None:
    from intpot import ParameterSchema

    mapping = ParameterSchema("mapping", default={float("nan"): "value"}).default
    key = next(iter(mapping))

    assert mapping[key] == "value"
    assert dict(mapping)[key] == "value"


def test_schema_equality_preserves_multiple_distinct_nan_set_members() -> None:
    from intpot import ParameterSchema

    first_nan = float("nan")
    second_nan = float("nan")
    single = ParameterSchema("values", default={first_nan})
    multiple = ParameterSchema("values", default={first_nan, second_nan})

    assert len(single.default) == 1
    assert len(multiple.default) == 2
    assert single.to_dict() != multiple.to_dict()
    assert single != multiple


def test_schema_rejects_defaults_that_cannot_preserve_value_semantics() -> None:
    from intpot import ParameterSchema

    unsupported = (
        datetime(2026, 11, 1, 1, 30, fold=1),
        time(1, 30, fold=1),
        datetime(2026, 1, 1, tzinfo=UTC),
        time(1, 30, tzinfo=UTC),
        Decimal("sNaN"),
    )

    for value in unsupported:
        with pytest.raises(TypeError, match="cannot be preserved"):
            ParameterSchema("value", default=value)


def test_schema_equality_distinguishes_cross_type_equal_scalars() -> None:
    from intpot import ParameterSchema

    boolean = ParameterSchema("value", default=True)
    integer = ParameterSchema("value", default=1)

    assert boolean != integer
    assert integer != boolean
    assert hash(boolean) != hash(integer)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (Decimal("1.0"), Decimal("1.00")),
        (Decimal("-0"), Decimal("0")),
        (-0.0, 0.0),
        (complex(-0.0, 0.0), complex(0.0, 0.0)),
    ],
)
def test_schema_equality_distinguishes_preserved_value_representations(
    left, right
) -> None:
    from intpot import ParameterSchema

    left_schema = ParameterSchema("value", default=left)
    right_schema = ParameterSchema("value", default=right)

    assert repr(left_schema.to_info().default) != repr(right_schema.to_info().default)
    assert left_schema != right_schema


def test_api_generation_avoids_path_default_import_collisions() -> None:
    from intpot import ApplicationSchema, ParameterSchema, SourceType, ToolSchema

    schema = ApplicationSchema(
        name="paths",
        source_type=SourceType.PYTHON,
        tools=(
            ToolSchema(
                name="read",
                parameters=(
                    ParameterSchema(
                        "item_id", type_annotation="str", param_source=ParamSource.path
                    ),
                    ParameterSchema(
                        "output", type_annotation="object", default=Path("result.txt")
                    ),
                ),
                route_path="/items/{item_id}",
            ),
        ),
    )

    code = APIGenerator().generate(schema)
    module = ModuleType("generated_path_defaults")
    exec(compile(code, "generated_path_defaults.py", "exec"), module.__dict__)

    assert (
        "from fastapi import FastAPI as _intpot_fastapi_FastAPI, "
        "Body as _intpot_fastapi_Body, Path as _intpot_fastapi_Path"
    ) in code
    assert "import pathlib as _intpot_defaults_pathlib" in code
    assert "_intpot_defaults_pathlib.Path('result.txt')" in code


def test_api_generation_isolated_fastapi_path_from_preserved_source_imports() -> None:
    from intpot import ApplicationSchema, ParameterSchema, SourceType, ToolSchema

    schema = ApplicationSchema(
        name="paths",
        source_type=SourceType.PYTHON,
        tools=(
            ToolSchema(
                name="read",
                parameters=(
                    ParameterSchema(
                        "item_id", type_annotation="str", param_source=ParamSource.path
                    ),
                    ParameterSchema(
                        "output", type_annotation="Path", default=Path("result.txt")
                    ),
                ),
                route_path="/items/{item_id}",
                source_imports=("from pathlib import Path",),
            ),
        ),
    )

    code = APIGenerator().generate(schema)
    module = ModuleType("generated_preserved_path")
    exec(compile(code, "generated_preserved_path.py", "exec"), module.__dict__)

    assert "Path as _intpot_fastapi_Path" in code


@pytest.mark.parametrize("generator", [CLIGenerator(), APIGenerator(), MCPGenerator()])
def test_compatibility_tool_inputs_render_structured_defaults(generator) -> None:
    from intpot.core.models import ParameterInfo, ToolInfo

    tool = ToolInfo(
        name="show",
        parameters=[
            ParameterInfo(
                "values", type_annotation="object", default=deque([Path("value.txt")])
            )
        ],
    )

    code = generator.generate([tool])
    module = ModuleType("generated_compatibility_defaults")
    exec(compile(code, "generated_compatibility_defaults.py", "exec"), module.__dict__)


@pytest.mark.parametrize("generator", [CLIGenerator(), APIGenerator(), MCPGenerator()])
def test_default_helpers_cannot_be_shadowed_by_generated_tool_names(generator) -> None:
    from intpot import ApplicationSchema, ParameterSchema, SourceType, ToolSchema

    helper_names = (
        "datetime",
        "date",
        "time",
        "timedelta",
        "Decimal",
        "Fraction",
        "UUID",
        "deque",
        "pathlib",
        "_intpot_defaults_collections",
        "_intpot_defaults_datetime",
        "_intpot_defaults_decimal",
        "_intpot_defaults_fractions",
        "_intpot_defaults_pathlib",
        "_intpot_defaults_uuid",
        "_intpot_fastapi_Body",
        "_intpot_fastapi_Path",
    )
    defaults = (
        datetime(2026, 1, 1),
        date(2026, 1, 1),
        time(1, 2),
        timedelta(seconds=1),
        Decimal("1.5"),
        Fraction(1, 2),
        UUID("12345678-1234-5678-1234-567812345678"),
        deque([1]),
        Path("value.txt"),
    )
    schema = ApplicationSchema(
        name="helper-collisions",
        source_type=SourceType.PYTHON,
        tools=(
            *(ToolSchema(name=name) for name in helper_names),
            ToolSchema(
                name="preserved_alias",
                source_imports=("import math as _intpot_defaults_datetime",),
            ),
            ToolSchema(
                name="show",
                parameters=tuple(
                    ParameterSchema(
                        f"value_{index}", type_annotation="object", default=value
                    )
                    for index, value in enumerate(defaults)
                ),
            ),
        ),
    )

    code = generator.generate(schema)
    module = ModuleType("generated_helper_collisions")
    exec(compile(code, "generated_helper_collisions.py", "exec"), module.__dict__)


@pytest.mark.parametrize("generator", [CLIGenerator(), APIGenerator(), MCPGenerator()])
def test_wildcard_source_imports_cannot_shadow_generated_helpers(
    generator, monkeypatch
) -> None:
    from intpot import ApplicationSchema, ParameterSchema, ToolSchema

    collision = ModuleType("intpot_collision_source")
    exported = (
        "typer",
        "FastMCP",
        "bytearray",
        "complex",
        "float",
        "frozenset",
        "range",
        "set",
        "slice",
        "Ellipsis",
        "NotImplemented",
        "_intpot_fastapi_FastAPI",
        "_intpot_fastapi_Body",
        "_intpot_defaults_builtins",
        "_intpot_defaults_datetime",
    )
    collision.__all__ = exported
    for name in exported:
        setattr(collision, name, object())
    monkeypatch.setitem(sys.modules, collision.__name__, collision)

    schema = ApplicationSchema(
        name="wildcard-safe",
        source_type=SourceType.PYTHON,
        tools=(
            ToolSchema(
                name="show",
                parameters=(
                    ParameterSchema("when", default=datetime(2026, 1, 1)),
                    ParameterSchema("blob", default=bytearray(b"x")),
                    ParameterSchema("number", default=complex(1, 2)),
                    ParameterSchema("infinite", default=float("inf")),
                    ParameterSchema("frozen", default=frozenset()),
                    ParameterSchema("span", default=range(1, 2)),
                    ParameterSchema("items", default=set()),
                    ParameterSchema("window", default=slice(1, 2)),
                ),
                source_imports=(f"from {collision.__name__} import *",),
            ),
        ),
    )

    code = generator.generate(schema)
    module = ModuleType("generated_wildcard_safe")
    exec(compile(code, "generated_wildcard_safe.py", "exec"), module.__dict__)


@pytest.mark.parametrize("generator", [CLIGenerator(), APIGenerator(), MCPGenerator()])
def test_generators_render_every_supported_structured_default(generator) -> None:
    from intpot import ApplicationSchema, ParameterSchema, SourceType, ToolSchema

    defaults = (
        [1, "two"],
        (1, "two"),
        {1, 2},
        frozenset({1, 2}),
        {1: "one", "two": 2},
        bytearray(b"abc"),
        deque([1, 2], maxlen=3),
        Path("value.txt"),
        date(2026, 8, 31),
        datetime(2026, 8, 31, 3, 4, 5),
        time(3, 4, 5),
        timedelta(days=2, seconds=3, microseconds=4),
        Decimal("1.25"),
        Fraction(2, 3),
        UUID("12345678-1234-5678-1234-567812345678"),
        range(1, 5, 2),
        slice(1, 5, 2),
        complex(1, 2),
        float("inf"),
    )
    parameters = tuple(
        ParameterSchema(f"value_{index}", type_annotation="object", default=value)
        for index, value in enumerate(defaults)
    )
    schema = ApplicationSchema(
        name="defaults",
        source_type=SourceType.PYTHON,
        tools=(ToolSchema(name="show", parameters=parameters),),
    )

    code = generator.generate(schema)
    module = ModuleType("generated_defaults")
    exec(compile(code, "generated_defaults.py", "exec"), module.__dict__)

    generated = module.show
    actual = tuple(
        parameter.default
        for parameter in __import__("inspect").signature(generated).parameters.values()
    )
    if isinstance(generator, CLIGenerator):
        actual = tuple(value.default for value in actual)
    if isinstance(generator, APIGenerator):
        actual = tuple(value.default for value in actual)
    assert actual[:-1] == defaults[:-1]
    assert math.isinf(actual[-1]) and actual[-1] > 0


def test_schema_to_dict_normalizes_supported_non_json_defaults() -> None:
    from intpot import ApplicationSchema, ParameterSchema, SourceType, ToolSchema

    schema = ApplicationSchema(
        name="json-values",
        source_type=SourceType.PYTHON,
        tools=(
            ToolSchema(
                name="show",
                parameters=(
                    ParameterSchema(name="tags", default={"b", "a"}),
                    ParameterSchema(name="path", default=Path("/tmp/value")),
                    ParameterSchema(name="blob", default=b"abc"),
                    ParameterSchema(name="queue", default=deque([1, 2], maxlen=3)),
                ),
            ),
        ),
    )

    data = schema.to_dict()
    defaults = {
        parameter["name"]: parameter["default"]
        for parameter in data["tools"][0]["parameters"]
    }

    json.dumps(data)
    assert defaults["tags"] == {"$intpot": {"type": "set", "items": ["a", "b"]}}
    assert defaults["path"] == {"$intpot": {"type": "path", "value": "/tmp/value"}}
    assert defaults["blob"] == {"$intpot": {"type": "bytes", "base64": "YWJj"}}
    assert defaults["queue"] == {
        "$intpot": {
            "type": "deque",
            "items": [1, 2],
            "maxlen": 3,
        }
    }


def test_runtime_schema_and_ejection_follow_public_app_renames() -> None:
    from intpot.runtime_builders import build_fastapi_app

    app = intpot.App("first")

    @app.tool()
    def status() -> str:
        return "ok"

    _ = app.schema
    app.name = "second"

    live = build_fastapi_app(app.name, app._tools)
    generated = ModuleType("generated_after_rename")
    exec(compile(app.eject("api"), "generated.py", "exec"), generated.__dict__)

    assert app.schema.name == "second"
    assert live.title == "second"
    assert generated.app.title == "second"


def test_compile_app_supports_the_public_python_source_type() -> None:
    app = intpot.App("python-source")

    @app.tool()
    def echo(value: str) -> str:
        return value

    schema = intpot.compile_app(intpot.SourceType.PYTHON, app)

    assert schema == app.schema
    assert schema.name == "python-source"
    assert [tool.name for tool in schema.tools] == ["echo"]

    with pytest.raises(ValueError, match=r"requires an intpot\.App"):
        intpot.compile_app(intpot.SourceType.PYTHON, object())


def test_application_names_follow_framework_semantics_and_path_fallback(
    tmp_source,
) -> None:
    default_api = tmp_source(
        """
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/health")
        def health() -> dict:
            return {"ok": True}
        """,
        name="service.py",
    )
    titled_api = tmp_source(
        """
        from fastapi import FastAPI

        app = FastAPI(title="Orders")

        @app.get("/health")
        def health() -> dict:
            return {"ok": True}
        """,
        name="orders.py",
    )

    assert intpot.load(default_api).schema.name == "service"
    assert intpot.load(titled_api).schema.name == "Orders"
