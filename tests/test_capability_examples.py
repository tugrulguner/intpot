from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_capability_teaching_scripts_are_present_and_runnable() -> None:
    scripts = [
        "examples/enum_export/app.py",
        "examples/convert_enum_export.py",
        "examples/selected_tools.py",
        "examples/convert_selected_tools.py",
        "examples/convert_informational.py",
    ]
    missing = [name for name in scripts if not (ROOT / name).is_file()]
    assert not missing, f"missing user-facing capability examples: {missing}"

    for name in scripts[1:]:
        result = subprocess.run(
            [sys.executable, str(ROOT / name), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_enum_recipe_generates_runnable_servers(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/convert_enum_export.py"),
            "--output-dir",
            str(tmp_path / "servers"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("enum_api.py", "enum_mcp.py"):
        source = (tmp_path / "servers" / name).read_text()
        compile(source, name, "exec")


def test_capability_recipes_preserve_actual_cli_http_mcp_effects() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "capability_verifier", ROOT / "scripts/verify_generated_examples.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.verify_capability_examples()
    assert (
        result["enum"] == "native/http/stdio-mcp byte parity; invalid inputs no files"
    )
    assert result["selected"] == "only slug; native/http/stdio-mcp; full source refused"
    assert result["informational"] in {
        "native/http/stdio-mcp byte parity; early exit; conflicts rejected",
        "provider-backed callbacks refused before output directory",
    }


def test_capability_index_describes_new_examples() -> None:
    readme = (ROOT / "examples/README.md").read_text()
    for term in ("enum_export", "selected_tools.py", "informational"):
        assert term in readme
