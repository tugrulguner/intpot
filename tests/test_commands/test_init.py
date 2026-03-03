"""Tests for the init command."""

from __future__ import annotations

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_init_mcp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "my-server", "--type", "mcp"])
    assert result.exit_code == 0
    assert (tmp_path / "my-server" / "server.py").exists()
    content = (tmp_path / "my-server" / "server.py").read_text()
    assert "my-server" in content
    assert "FastMCP" in content


def test_init_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "my-cli", "--type", "cli"])
    assert result.exit_code == 0
    assert (tmp_path / "my-cli" / "main.py").exists()
    content = (tmp_path / "my-cli" / "main.py").read_text()
    assert "my-cli" in content
    assert "typer" in content


def test_init_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "my-api", "--type", "api"])
    assert result.exit_code == 0
    assert (tmp_path / "my-api" / "main.py").exists()
    content = (tmp_path / "my-api" / "main.py").read_text()
    assert "my-api" in content
    assert "FastAPI" in content


def test_init_existing_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "existing").mkdir()
    result = runner.invoke(app, ["init", "existing", "--type", "mcp"])
    assert result.exit_code == 1
