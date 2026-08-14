"""Tests for the shared inspector utilities.

The one-liner cases are written into real files rather than defined inline,
because ruff-format would rewrite `def f(): return 1` into two lines and quietly
delete the thing being tested.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from intpot.core.generators.cli import CLIGenerator
from intpot.core.inspectors._utils import extract_function_body
from intpot.core.models import SourceType
from intpot.core.transforms import transform_tools


def _load(path: Path, name: str) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


def test_body_on_the_signature_line_excludes_the_signature(tmp_source):
    """`def double(x): return x * 2` must yield `return x * 2`, not the def line.

    Slicing whole lines used to include the signature, so the generated code
    defined a nested function and never called it — valid Python that did
    nothing.
    """
    path = tmp_source("def double(x: int) -> int: return x * 2\n")

    assert extract_function_body(_load(path, "double")) == "return x * 2"


def test_multi_line_body_is_unchanged(tmp_source):
    path = tmp_source(
        """
        def triple(x: int) -> int:
            y = x * 3
            return y
        """
    )

    assert extract_function_body(_load(path, "triple")) == "y = x * 3\nreturn y"


def test_docstring_is_skipped(tmp_source):
    path = tmp_source(
        '''
        def doc(x: int) -> int:
            """Docstring."""
            return x
        '''
    )

    assert extract_function_body(_load(path, "doc")) == "return x"


def test_statement_sharing_a_line_with_the_docstring(tmp_source):
    path = tmp_source('def d(x: int) -> int:\n    """Doc."""; return x\n')

    assert extract_function_body(_load(path, "d")) == "return x"


def test_docstring_only_function_has_no_body(tmp_source):
    path = tmp_source(
        '''
        def stub(x: int) -> int:
            """Nothing here."""
        '''
    )

    assert extract_function_body(_load(path, "stub")) is None


def test_a_one_line_tool_still_runs_after_conversion(tmp_source):
    """End to end: the generated CLI must actually compute, not silently pass."""
    path = tmp_source(
        "from fastmcp import FastMCP\n"
        "\n"
        'mcp = FastMCP("probe")\n'
        "\n"
        "@mcp.tool()\n"
        "def double(x: int) -> int: return x * 2\n"
        "\n"
        "@mcp.tool()\n"
        "def triple(x: int) -> int:\n"
        "    return x * 3\n"
    )

    from intpot import load

    tools = transform_tools(load(path).tools, SourceType.MCP, SourceType.CLI)
    namespace: dict[str, Any] = {}
    exec(compile(CLIGenerator().generate(tools), "<generated>", "exec"), namespace)

    result = CliRunner().invoke(namespace["app"], ["double", "4"])

    assert result.exit_code == 0, result.output
    assert "8" in result.output


def test_the_generated_body_contains_no_nested_definition(tmp_source):
    """The specific corruption: a `def` smuggled into the body."""
    path = tmp_source("def double(x: int) -> int: return x * 2\n")

    body = extract_function_body(_load(path, "double"))

    assert body is not None
    assert "def " not in body
