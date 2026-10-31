from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest
from fastmcp import Client
from typer.testing import CliRunner

import intpot


def test_mcp_bounds_protect_generated_cli_receipts(tmp_path):
    loaded = intpot.load(
        Path(__file__).parents[1] / "examples/inventory_reservation.py"
    )

    async def source():
        async with Client(loaded.app) as client:
            valid = await client.call_tool("reserve_inventory", {"quantity": 2})
            assert valid.content and "24" in valid.content[0].text
            receipt = tmp_path / "source-invalid.txt"
            invalid = await client.call_tool(
                "reserve_inventory",
                {"quantity": 0, "receipt": str(receipt)},
                raise_on_error=False,
            )
            assert invalid.is_error
            assert not receipt.exists()

    asyncio.run(source())
    namespace = {}
    exec(loaded.to_cli(), namespace)
    assert CliRunner().invoke(namespace["app"], ["2"]).exit_code == 0
    receipt = tmp_path / "generated-invalid.txt"
    rejected = CliRunner().invoke(namespace["app"], ["0", "--receipt", str(receipt)])
    assert rejected.exit_code == 2
    assert not receipt.exists()


def test_mcp_source_unsupported_constraints_refuse_before_scaffold(tmp_path):
    import pytest

    from intpot.core.numeric_ranges import UnsupportedMCPNumericRangeError

    source = tmp_path / "unsupported.py"
    source.write_text(
        """from typing import Annotated\nfrom pydantic import Field\nfrom fastmcp import FastMCP\napp = FastMCP('x')\n@app.tool()\ndef run(n: Annotated[int, Field(ge=1, le=5, multiple_of=2)]) -> int:\n    return n\n"""
    )
    loaded = intpot.load(source)
    assert loaded.tools[0].parameters[0].unsupported_mcp_numeric_range
    with pytest.raises(UnsupportedMCPNumericRangeError):
        loaded.to_cli(allow_scaffold=True)


@pytest.mark.parametrize(
    "declaration,valid,invalid",
    [
        ("n: Annotated[int, Field(ge=1, le=5)]", 3, 0),
        ("n: Annotated[int, Field(ge=1, le=5)] = 2", 3, 6),
        (
            "n: Annotated[int, Field(default=2, ge=1, le=5, validate_default=True)]",
            3,
            0,
        ),
        ("n: int = Field(2, ge=1, le=5)", 3, 0),
        ("n: float = Field(..., ge=0.5)", 0.75, 0.25),
        ("n: Annotated[float, Field(le=1.5)] = 1.0", 1.25, 1.75),
        ("n: int = Field(0)", 3, "bad"),
        ("n: Annotated[float, Field(default=0.0)]", 0.75, "bad"),
    ],
)
def test_mcp_numeric_declarations_native_consumers(
    tmp_path, declaration, valid, invalid
):
    from fastapi.testclient import TestClient

    source = tmp_path / "positive.py"
    source.write_text(
        f"from typing import Annotated\nfrom pydantic import Field\nfrom fastmcp import FastMCP\nmcp=FastMCP('positive')\n@mcp.tool()\ndef quote({declaration}) -> dict:\n    return {{'value': n}}\n"
    )
    loaded = intpot.load(source)
    param = loaded.schema.tools[0].parameters[0]
    if "default=2" in declaration:

        async def omitted_source():
            async with Client(loaded.app) as client:
                result = await client.call_tool("quote", {})
                assert json.loads(result.content[0].text) == {"value": 2}

        asyncio.run(omitted_source())
        assert not param.required and param.default == 2
    assert not param.unsupported_mcp_numeric_range
    if "ge=" in declaration or "le=" in declaration:
        assert param.minimum is not None or param.maximum is not None
    else:
        assert param.minimum is None and param.maximum is None
    ns = {}
    exec(loaded.to_api(), ns)
    api = TestClient(ns["app"])
    route = loaded.project("api").tools[0].route_path
    assert route
    assert api.post(route, json=valid).json() == {"value": valid}
    assert api.post(route, json=invalid).status_code == 422
    ns = {}
    exec(loaded.to_cli(), ns)
    prefix = [] if param.required else ["--n"]
    assert CliRunner().invoke(ns["app"], [*prefix, str(valid)]).exit_code == 0
    assert CliRunner().invoke(ns["app"], [*prefix, str(invalid)]).exit_code == 2

    async def native():
        async with Client(loaded.app) as client:
            result = await client.call_tool("quote", {"n": valid})
            assert json.loads(result.content[0].text) == {"value": valid}
            error = await client.call_tool(
                "quote", {"n": invalid}, raise_on_error=False
            )
            assert error.is_error
            if not param.required:
                result = await client.call_tool("quote", {})
                expected = json.loads(result.content[0].text)
                assert api.post(route).json() == expected
                output = CliRunner().invoke(ns["app"], [])
                assert (
                    output.exit_code == 0
                    and ast.literal_eval(output.stdout) == expected
                )

    asyncio.run(native())


@pytest.mark.parametrize(
    "declaration",
    [
        "n: Annotated[int, Field(gt=1)]",
        "n: Annotated[int, Field(ge=1, multiple_of=2)]",
        "n: Annotated[int, Field(ge=1, strict=True)]",
        "n: Annotated[int, Field(ge=1), AfterValidator(abs)]",
        'n: Annotated[float, Field(ge=float("inf"))]',
        "n: Annotated[int, Field(ge=1, le=5)] = 0",
        "n: Annotated[int, Field(default=0, ge=1, validate_default=True)]",
        "n: Annotated[int, Field(default=None, ge=1, validate_default=True)]",
        'n: int = Field("2", ge=1, le=5)',
        'n: int = Field("bad", validate_default=False)',
        'n: Annotated[int, Field(default="bad", validate_default=False)]',
        "n: int = Field(True)",
        "n: int = Field(1.5)",
        'n: float = Field(float("inf"))',
        "n: int = Field(default_factory=lambda: 2, ge=1)",
    ],
)
def test_mcp_unsupported_validation_is_inspectable_and_refused_before_write(
    tmp_path, declaration
):
    source = tmp_path / "negative.py"
    source.write_text(
        f"from typing import Annotated\nfrom pydantic import Field, AfterValidator\nfrom fastmcp import FastMCP\nmcp=FastMCP('negative')\n@mcp.tool()\ndef quote({declaration}) -> int:\n    return n\n"
    )
    loaded = intpot.load(source)
    assert loaded.schema.tools[0].parameters[0].unsupported_mcp_numeric_range
    assert [d["code"] for d in loaded.assess()["diagnostics"]] == [
        "unsupported_mcp_numeric_range"
    ] * 2
    for target in ("cli", "api"):
        for scaffold in (False, True):
            dest = tmp_path / f"{target}-{scaffold}" / "app.py"
            with pytest.raises(intpot.UnsupportedMCPNumericRangeError):
                loaded.write(dest, target, allow_scaffold=scaffold)
            assert not dest.parent.exists()


@pytest.mark.parametrize(
    "declaration",
    [
        'n: int = Field("bad", validate_default=False)',
        'n: Annotated[int, Field(default="bad", validate_default=False)]',
    ],
)
def test_mcp_unbounded_default_source_omission_is_not_silently_changed(
    tmp_path, declaration
):
    source = tmp_path / "omission.py"
    source.write_text(
        f"from typing import Annotated\nfrom pydantic import Field\nfrom fastmcp import FastMCP\nmcp=FastMCP('omission')\n@mcp.tool()\ndef quote({declaration}) -> dict:\n    return {{'value': n}}\n"
    )
    loaded = intpot.load(source)

    async def native():
        async with Client(loaded.app) as client:
            result = await client.call_tool("quote", {})
            assert json.loads(result.content[0].text) == {"value": "bad"}

    asyncio.run(native())
    assert loaded.schema.tools[0].parameters[0].default == "bad"
    assert loaded.schema.tools[0].parameters[0].unsupported_mcp_numeric_range
    for target in ("cli", "api"):
        for scaffold in (False, True):
            output = tmp_path / f"{target}-{scaffold}" / "output.py"
            with pytest.raises(intpot.UnsupportedMCPNumericRangeError):
                loaded.write(output, target, allow_scaffold=scaffold)
            assert not output.parent.exists()


def test_mcp_factory_is_not_evaluated_during_inspection():
    from fastmcp import FastMCP
    from pydantic import Field

    calls = []

    def factory():
        calls.append(True)
        return 2

    server = FastMCP("factory")

    @server.tool()
    def quote(n: int = Field(default_factory=factory, ge=1)) -> int:
        return n

    assert calls == []
    loaded = intpot.load(server)
    assert calls == []
    assert loaded.schema.tools[0].parameters[0].unsupported_mcp_numeric_range
    with pytest.raises(intpot.UnsupportedMCPNumericRangeError):
        loaded.to_api(allow_scaffold=True)
    assert calls == []


def test_mcp_metadata_copy_hash_and_json():
    from dataclasses import replace

    from intpot.core.models import ParameterInfo, ParameterSchema, ToolInfo
    from intpot.runtime import _copy_tool_info

    info = ParameterInfo("n", "int", unsupported_mcp_numeric_range=True)
    schema = ParameterSchema.from_info(info)
    assert schema == ParameterSchema.from_info(schema.to_info())
    assert len({schema, ParameterSchema.from_info(schema.to_info())}) == 1
    assert schema != replace(schema, unsupported_mcp_numeric_range=False)
    assert schema.to_dict()["unsupported_mcp_numeric_range"]
    assert (
        "unsupported_mcp_numeric_range"
        not in replace(schema, unsupported_mcp_numeric_range=False).to_dict()
    )
    copied = _copy_tool_info(ToolInfo("quote", parameters=[info])).parameters[0]
    assert copied.unsupported_mcp_numeric_range
    copied.unsupported_mcp_numeric_range = False
    assert schema.unsupported_mcp_numeric_range and info.unsupported_mcp_numeric_range
