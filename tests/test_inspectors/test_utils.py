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
from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
)
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


# ---------------------------------------------------------------------------
# Import bindings
#
# `import os.path` binds `os`, not `os.path`. Recording the dotted path meant
# the binding never matched what the body referenced, the import was dropped,
# and the generated module raised NameError at runtime.
# ---------------------------------------------------------------------------


def _imports_for(tmp_source, body_source: str) -> list[str]:
    path = tmp_source(body_source)
    return extract_source_imports(_load(path, "tool"))


def test_a_dotted_import_is_kept_when_the_body_uses_it(tmp_source):
    imports = _imports_for(
        tmp_source,
        "import os.path\n\n\ndef tool(name: str) -> str:\n"
        '    return os.path.join("/tmp", name)\n',
    )

    assert imports == ["import os.path"]


def test_a_dotted_import_with_an_alias_binds_the_alias(tmp_source):
    imports = _imports_for(
        tmp_source,
        "import xml.etree.ElementTree as ET\n\n\ndef tool(raw: str) -> str:\n"
        "    return ET.fromstring(raw).tag\n",
    )

    assert imports == ["import xml.etree.ElementTree as ET"]


def test_from_import_binding_is_unchanged(tmp_source):
    imports = _imports_for(
        tmp_source,
        "from os import path\n\n\ndef tool(name: str) -> str:\n"
        '    return path.join("/tmp", name)\n',
    )

    assert imports == ["from os import path"]


def test_an_unused_dotted_import_is_still_dropped(tmp_source):
    """The fix must not turn the filter into "keep everything"."""
    imports = _imports_for(
        tmp_source,
        "import os.path\nimport json\n\n\ndef tool(value: str) -> str:\n"
        '    return json.dumps({"v": value})\n',
    )

    assert imports == ["import json"]


def test_only_the_first_segment_binds(tmp_source):
    """`import a.b.c` binds `a`; a body mentioning `b` or `c` must not match."""
    imports = _imports_for(
        tmp_source,
        "import xml.etree.ElementTree\n\n\ndef tool(value: str) -> str:\n"
        "    return etree(value)\n",
    )

    assert imports == []


def test_a_generated_command_using_a_dotted_import_runs(tmp_source):
    """The failure was at runtime, so the test has to reach runtime."""
    path = tmp_source(
        "import os.path\n"
        "from fastmcp import FastMCP\n"
        "\n"
        'mcp = FastMCP("probe")\n'
        "\n"
        "@mcp.tool()\n"
        "def where(name: str) -> str:\n"
        '    """Join a path."""\n'
        '    return os.path.join("/tmp", name)\n'
    )

    from intpot import load

    tools = transform_tools(load(path).tools, SourceType.MCP, SourceType.CLI)
    namespace: dict[str, Any] = {}
    exec(compile(CLIGenerator().generate(tools), "<generated>", "exec"), namespace)

    result = CliRunner().invoke(namespace["app"], ["hello"])

    assert result.exit_code == 0, result.output
    assert "/tmp/hello" in result.output


def test_a_mixed_import_statement_keeps_the_name_the_body_uses(tmp_source):
    """`import os.path, typer` binds two unrelated names in one statement.

    Downstream framework filtering works on the rendered string: it saw `typer`
    and dropped the whole statement, taking `os.path` with it.
    """
    imports = _imports_for(
        tmp_source,
        "import os.path, typer\n\n\ndef tool(name: str) -> str:\n"
        '    return os.path.join("/tmp", name)\n',
    )

    assert imports == ["import os.path"]


def test_a_mixed_from_import_keeps_only_the_name_in_use(tmp_source):
    imports = _imports_for(
        tmp_source,
        "from os.path import join, dirname\n\n\ndef tool(name: str) -> str:\n"
        '    return join("/tmp", name)\n',
    )

    assert imports == ["from os.path import join"]


def test_a_mixed_import_survives_into_a_running_command(tmp_source):
    """The reviewer's case, end to end: the failure was a runtime NameError."""
    path = tmp_source(
        "import os.path, typer\n"
        "from fastmcp import FastMCP\n"
        "\n"
        'mcp = FastMCP("probe")\n'
        "\n"
        "@mcp.tool()\n"
        "def where(name: str) -> str:\n"
        '    """Join a path."""\n'
        '    return os.path.join("/tmp", name)\n'
    )

    from intpot import load

    tools = transform_tools(load(path).tools, SourceType.MCP, SourceType.CLI)
    source = CLIGenerator().generate(tools)
    namespace: dict[str, Any] = {}
    exec(compile(source, "<generated>", "exec"), namespace)

    result = CliRunner().invoke(namespace["app"], ["hello"])

    assert result.exit_code == 0, result.output
    assert "/tmp/hello" in result.output
    assert "import os.path" in source
