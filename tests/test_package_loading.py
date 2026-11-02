from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

import intpot
from intpot.core.detector import SourceImportError, detect_source


@pytest.fixture(autouse=True)
def isolate_test_packages():
    def owned(name):
        return name in {"sample", "initpkg"} or name.startswith(("sample.", "initpkg."))

    previous = {name: module for name, module in sys.modules.items() if owned(name)}
    for name in previous:
        sys.modules.pop(name)
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if owned(name):
                sys.modules.pop(name)
        sys.modules.update(previous)


def make_package(
    root: Path, *, nested: bool = False, target_init: bool = False
) -> Path:
    pkg = root / "sample"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from . import helper\n")
    (pkg / "helper.py").write_text("VALUE = 'package-helper'\n")
    if nested:
        child = pkg / "nested"
        child.mkdir()
        (child / "__init__.py").write_text("from .. import helper\n")
        target = child / "__init__.py" if target_init else child / "app.py"
        relative = "from ..helper import VALUE\n"
    else:
        target = pkg / "app.py"
        relative = "from .helper import VALUE\n"
    target.write_text(
        "import typer\n" + relative + "app = typer.Typer()\n"
        "@app.command()\ndef run():\n    typer.echo(VALUE)\n"
    )
    return target


def test_detects_regular_package_and_nested_relative_imports(tmp_path: Path) -> None:
    for nested in (False, True):
        for name in tuple(sys.modules):
            if name == "sample" or name.startswith("sample."):
                del sys.modules[name]
        target = make_package(tmp_path / str(nested), nested=nested)
        source_type, app = detect_source(target)
        assert source_type.value == "cli"
        assert len(app.registered_commands) == 1
    for name in tuple(sys.modules):
        if name == "sample" or name.startswith("sample."):
            del sys.modules[name]


def test_package_initializer_target_and_eager_import_execute_once(
    tmp_path: Path,
) -> None:
    pkg = tmp_path / "initpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from . import helper\nimport typer\napp = typer.Typer()\n"
        "@app.command()\ndef run(): print(helper.VALUE)\n"
    )
    (pkg / "helper.py").write_text(
        "from pathlib import Path\np = Path(__file__).with_name('count')\np.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\nVALUE='ok'\n"
    )
    source_type, _ = detect_source(pkg / "__init__.py")
    assert source_type.value == "cli"
    assert (pkg / "count").read_text() == "1"


def test_nested_package_initializer_target(tmp_path: Path, monkeypatch) -> None:
    target = make_package(tmp_path, nested=True, target_init=True)
    for key in ("sample", "sample.helper", "sample.nested"):
        monkeypatch.delitem(sys.modules, key, raising=False)
    source_type, _ = detect_source(target)
    assert source_type.value == "cli"


@pytest.mark.parametrize("fresh_parent", [False, True])
def test_package_search_path_cannot_select_foreign_target(tmp_path, fresh_parent):
    target = make_package(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    marker = tmp_path / "foreign-executed"
    (foreign / "app.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('wrong tree')\n"
        "import typer\napp = typer.Typer()\n"
    )
    if fresh_parent:
        target.with_name("__init__.py").write_text(f"__path__ = [{str(foreign)!r}]\n")
    else:
        from types import ModuleType

        parent = ModuleType("sample")
        parent.__file__ = str(target.with_name("__init__.py"))
        parent.__path__ = [str(foreign)]
        sys.modules["sample"] = parent
    with pytest.raises(SourceImportError):
        detect_source(target)
    assert not marker.exists(), "Loader executed a different tree's target"


def test_import_preserves_unrelated_application_path_changes(tmp_path):
    target = make_package(tmp_path)
    added = str(tmp_path / "application-added")
    target.with_name("__init__.py").write_text(
        f"import sys\nsys.path.append({added!r})\n"
    )
    before = sys.path.copy()
    try:
        detect_source(target)
        assert sys.path == [*before, added]
    finally:
        sys.path[:] = before


def test_foreign_cached_helper_is_refused_without_executing_target(tmp_path):
    from types import ModuleType

    target = make_package(tmp_path)
    marker = tmp_path / "target-executed"
    target.write_text(
        target.read_text()
        + f"\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    )
    helper = ModuleType("sample.helper")
    helper.__file__ = str(tmp_path / "other-tree" / "helper.py")
    vars(helper)["VALUE"] = "wrong-tree"
    sys.modules["sample.helper"] = helper
    with pytest.raises(SourceImportError):
        detect_source(target)
    assert not marker.exists()
    assert sys.modules["sample.helper"] is helper


def test_file_loading_through_cli_reaches_native_http_and_mcp(tmp_path):
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from typer.testing import CliRunner

    from intpot.cli import app as cli

    target = make_package(tmp_path)
    for destination in ("api", "mcp"):
        output = tmp_path / (destination + ".py")
        result = CliRunner().invoke(
            cli,
            ["to", destination, str(target), "--tool", "run", "--output", str(output)],
        )
        assert result.exit_code == 0, (result.exception, result.stdout)
        namespace: dict[str, Any] = {"__name__": "generated_package"}
        exec(output.read_text(), namespace)
        if destination == "api":
            with TestClient(namespace["app"]) as client:
                response = client.post("/run", json={})
                assert response.status_code == 200
                assert response.json() == {"result": "package-helper"}
        else:

            async def call(server=namespace["mcp"]):
                async with Client(server) as client:
                    result = await client.call_tool("run", {})
                    assert result.content[0].text == "package-helper"

            asyncio.run(call())


def test_foreign_cache_cli_refuses_before_write(tmp_path):
    from types import ModuleType

    from typer.testing import CliRunner

    from intpot.cli import app as cli

    target = make_package(tmp_path)
    cached = ModuleType("sample")
    cached.__file__ = str(tmp_path / "foreign" / "__init__.py")
    sys.modules["sample"] = cached
    for destination in ("api", "mcp"):
        output = tmp_path / (destination + ".py")
        result = CliRunner().invoke(
            cli,
            ["to", destination, str(target), "--tool", "run", "--output", str(output)],
        )
        assert result.exit_code == 1
        assert not output.exists()
        assert sys.modules["sample"] is cached


def test_parent_eager_target_import_and_repeated_load_execute_once(tmp_path):
    target = make_package(tmp_path)
    counter = tmp_path / "count"
    target.write_text(
        target.read_text()
        + f"\nfrom pathlib import Path\np=Path({str(counter)!r})\np.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n"
    )
    target.with_name("__init__.py").write_text("from . import app\n")
    first = intpot.load(target)
    second = intpot.load(target)
    assert first.schema == second.schema
    assert counter.read_text() == "1"


def test_cached_matching_package_is_reused(tmp_path: Path) -> None:
    target = make_package(tmp_path)
    sys.path.insert(0, str(tmp_path))
    try:
        before = importlib.import_module("sample")
        detect_source(target)
        assert sys.modules["sample"] is before
    finally:
        sys.path.remove(str(tmp_path))
        for name in tuple(sys.modules):
            if name == "sample" or name.startswith("sample."):
                del sys.modules[name]


@pytest.mark.parametrize("kind", ["parent", "target"])
def test_foreign_cached_package_is_refused_without_overwrite(
    tmp_path: Path, kind: str
) -> None:
    target = make_package(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "__init__.py").write_text("raise RuntimeError('foreign executed')\n")
    (foreign / "app.py").write_text("raise RuntimeError('foreign target executed')\n")
    name = "sample" if kind == "parent" else "sample.app"
    module = __import__("types").ModuleType(name)
    module.__file__ = str(foreign / ("__init__.py" if kind == "parent" else "app.py"))
    sys.modules[name] = module
    try:
        with pytest.raises(SourceImportError):
            detect_source(target)
        assert sys.modules[name] is module
    finally:
        del sys.modules[name]


def test_standalone_does_not_retain_sys_path(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("import typer\napp=typer.Typer()\n")
    before = sys.path.copy()
    detect_source(target)
    assert sys.path == before


@pytest.mark.parametrize(
    "source, exception",
    [
        ("raise RuntimeError('boom')", Exception),
        ("raise SystemExit(7)", SystemExit),
        ("raise KeyboardInterrupt()", KeyboardInterrupt),
    ],
)
@pytest.mark.parametrize("packaged", [False, True])
def test_import_errors_restore_path(
    tmp_path: Path, source: str, exception: type[BaseException], packaged: bool
) -> None:
    target = make_package(tmp_path) if packaged else tmp_path / "app.py"
    target.write_text("import typer\napp=typer.Typer()\n" + source)
    before = sys.path.copy()
    expected = (
        (SourceImportError,)
        if exception is not KeyboardInterrupt
        else (KeyboardInterrupt,)
    )
    with pytest.raises(expected):
        detect_source(target)
    assert sys.path == before
