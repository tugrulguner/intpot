from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("variable", ["native_output", "api_output", "output"])
@pytest.mark.parametrize("changed_newlines", [False, True])
def test_informational_example_checks_actual_bytes(
    tmp_path, variable, changed_newlines
):
    """Exercise each real driver's output assertion, not a duplicate comparator."""
    driver = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_application_conformance.py"
    )
    tree = ast.parse(driver.read_text())
    checks: list[ast.stmt] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assert)
        and {variable, "expected"}
        <= {part.id for part in ast.walk(node) if isinstance(part, ast.Name)}
    ]
    assert len(checks) == 1
    expected = "<pre>text\n</pre>\n"
    data = expected.encode()
    output = tmp_path / "output.html"
    output.write_bytes(data.replace(b"\n", b"\r\n") if changed_newlines else data)
    namespace = {
        variable: output,
        "expected": expected,
        "native": SimpleNamespace(returncode=0, stderr=""),
        "normal": SimpleNamespace(is_error=False),
        "status": 200,
        "ordinary": {},
    }
    code = compile(ast.Module(body=checks, type_ignores=[]), str(driver), "exec")
    if changed_newlines:
        with pytest.raises(AssertionError):
            exec(code, namespace)
    else:
        exec(code, namespace)
