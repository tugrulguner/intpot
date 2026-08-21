"""A source that fails to import must be reported, not dumped as a traceback.

Detection executes the user's module, so anything it raises reaches intpot.
Only DetectionError was caught, so a missing dependency, a module-level error
or an unresolvable sibling import produced a full rich traceback and Typer's
crash exit code. Directory scanning already handled this; single-file commands,
which is what most people run, did not.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from intpot.cli import app
from intpot.core.detector import DetectionError, SourceImportError, detect_source

runner = CliRunner()

_RAISES_ON_IMPORT = """\
import nonexistent_module_xyz
from fastmcp import FastMCP

mcp = FastMCP("probe")

@mcp.tool()
def echo(value: str) -> str:
    "Echo."
    return value
"""


@pytest.fixture()
def broken_source(tmp_source) -> Path:
    return tmp_source(_RAISES_ON_IMPORT)


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["inspect"], id="inspect"),
        pytest.param(["to", "cli"], id="to-cli"),
        pytest.param(["to", "mcp"], id="to-mcp"),
        pytest.param(["to", "api"], id="to-api"),
    ],
)
def test_commands_report_an_import_failure_without_a_traceback(argv, broken_source):
    result = runner.invoke(app, [*argv, str(broken_source)])

    assert result.exit_code == 1, result.output
    assert "Cannot import" in result.output
    assert "nonexistent_module_xyz" in result.output
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_eject_reports_an_import_failure_without_a_traceback(broken_source):
    result = runner.invoke(app, ["eject", str(broken_source), "--to", "cli"])

    assert result.exit_code == 1, result.output
    assert "Cannot import" in result.output


def test_serve_reports_an_import_failure_without_a_traceback(broken_source):
    result = runner.invoke(app, ["serve", str(broken_source), "--cli"])

    assert result.exit_code == 1, result.output
    assert "Cannot import" in result.output


def test_the_error_names_the_file_and_the_original_exception(broken_source):
    with pytest.raises(SourceImportError) as caught:
        detect_source(broken_source)

    message = str(caught.value)
    assert str(broken_source) in message
    assert "ModuleNotFoundError" in message
    assert "nonexistent_module_xyz" in message
    assert caught.value.__cause__ is not None, "original exception discarded"


def test_a_source_import_error_is_a_detection_error() -> None:
    """Subclassing is what makes every existing handler report it cleanly."""
    assert issubclass(SourceImportError, DetectionError)


# ---------------------------------------------------------------------------
# Install hints must name the right package
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        ("fastmcp", "intpot[mcp]"),
        ("fastapi", "intpot[api]"),
        ("uvicorn", "intpot[api]"),
    ],
)
def test_a_missing_framework_points_at_the_right_extra(missing, expected):
    from intpot.core.detector import _import_failure_message

    message = _import_failure_message(Path("app.py"), ModuleNotFoundError(name=missing))

    assert expected in message


def test_a_users_own_module_is_not_mistaken_for_a_framework():
    """`"fastapi" in "myfastapi_helper"` sent people to install intpot[api].

    It would not have helped, and it hid the real cause.
    """
    from intpot.core.detector import _import_failure_message

    message = _import_failure_message(
        Path("app.py"), ModuleNotFoundError(name="myfastapi_helper")
    )

    assert "intpot[api]" not in message
    assert "myfastapi_helper" not in message or "sys.path" in message


def test_a_missing_sibling_module_explains_why(tmp_source):
    source = tmp_source(
        "from helpers import double\n"
        "from fastmcp import FastMCP\n"
        'mcp = FastMCP("probe")\n'
    )

    result = runner.invoke(app, ["inspect", str(source)])

    assert result.exit_code == 1
    assert "sys.path" in result.output


# ---------------------------------------------------------------------------
# Directory scanning must keep telling the two cases apart (#59)
# ---------------------------------------------------------------------------


def test_directory_scan_still_reports_import_failures(tmp_path: Path):
    """SourceImportError subclasses DetectionError, so ordering matters here."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "broken.py").write_text(_RAISES_ON_IMPORT)

    result = runner.invoke(app, ["to", "cli", str(project)])

    assert "SKIP (import failed)" in result.output
    assert "nonexistent_module_xyz" in result.output


def test_directory_scan_stays_quiet_about_files_that_are_not_apps(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "plain.py").write_text("value = 42\n")
    (project / "server.py").write_text(
        textwrap.dedent("""\
            from fastmcp import FastMCP
            mcp = FastMCP("probe")

            @mcp.tool()
            def echo(value: str) -> str:
                "Echo."
                return value
            """)
    )

    result = runner.invoke(
        app, ["to", "cli", str(project), "-o", str(tmp_path / "out")]
    )

    assert result.exit_code == 0, result.output
    assert "SKIP (import failed)" not in result.output


# ---------------------------------------------------------------------------
# sys.exit() during import
#
# SystemExit derives from BaseException, not Exception, so `except Exception`
# never saw it. intpot exited with the *source's* code and printed nothing —
# and a directory scan terminated instead of skipping the file and continuing.
# argparse calls sys.exit() on a bad parse, so this is reachable by accident.
# ---------------------------------------------------------------------------

_EXITS_ON_IMPORT = """\
import sys
from fastmcp import FastMCP

mcp = FastMCP("probe")
sys.exit(3)
"""


def test_a_source_that_exits_during_import_is_reported(tmp_source):
    source = tmp_source(_EXITS_ON_IMPORT)

    result = runner.invoke(app, ["inspect", str(source)])

    assert result.exit_code == 1, (
        f"inherited the source's exit code: {result.exit_code}"
    )
    assert "sys.exit(3)" in result.output
    assert "__main__" in result.output, "no guidance on how to avoid it"


def test_a_directory_scan_survives_a_source_that_exits(tmp_path: Path):
    """The scan must skip the file and keep going, not abort at exit code 3."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "exiter.py").write_text(_EXITS_ON_IMPORT)
    (project / "server.py").write_text(
        textwrap.dedent("""\
            from fastmcp import FastMCP
            mcp = FastMCP("probe")

            @mcp.tool()
            def echo(value: str) -> str:
                "Echo."
                return value
            """)
    )
    out = tmp_path / "out"

    result = runner.invoke(app, ["to", "cli", str(project), "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert "SKIP (import failed)" in result.output
    assert (out / "server_cli.py").exists(), "the good file was not converted"


def test_keyboard_interrupt_is_not_swallowed(tmp_source, monkeypatch):
    """Catching BaseException would trap Ctrl-C too; only SystemExit is caught."""
    from intpot.core import detector

    source = tmp_source('from fastmcp import FastMCP\nmcp = FastMCP("probe")\n')

    def _interrupt(self, module):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "importlib.machinery.SourceFileLoader.exec_module", _interrupt, raising=False
    )

    with pytest.raises(KeyboardInterrupt):
        detector.detect_source(source)


# ---------------------------------------------------------------------------
# The documented Python-API contract
# ---------------------------------------------------------------------------


def test_load_still_raises_module_not_found_for_a_path(tmp_source):
    """`load()` documents ModuleNotFoundError; wrapping made it unreachable."""
    from intpot import load

    source = tmp_source(
        "import totally_absent_module\n"
        "from fastmcp import FastMCP\n"
        'mcp = FastMCP("probe")\n'
    )

    with pytest.raises(ModuleNotFoundError) as caught:
        load(source)

    assert "totally_absent_module" in str(caught.value)
    assert caught.value.name == "totally_absent_module"


def test_load_keeps_the_install_hint_for_a_missing_extra():
    from intpot.converter import _missing_module_error

    hinted = _missing_module_error(ModuleNotFoundError(name="fastmcp"))

    assert "intpot[mcp]" in str(hinted)
    assert hinted.name == "fastmcp"


def test_load_hands_back_an_unrelated_missing_module_unchanged():
    from intpot.converter import _missing_module_error

    original = ModuleNotFoundError(
        "No module named 'myfastapi_helper'", name="myfastapi_helper"
    )

    assert _missing_module_error(original) is original


def test_load_still_raises_a_detection_error_for_a_non_app(tmp_source):
    from intpot import load

    with pytest.raises(DetectionError):
        load(tmp_source("value = 42\n"))
