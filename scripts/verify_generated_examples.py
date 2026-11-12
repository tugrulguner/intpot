"""Execute checked-in generated examples through their real frameworks."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient
from typer.testing import CliRunner

ROOT = Path(__file__).parents[1]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load example module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_generated_cli() -> None:
    module = _load_module(
        "intpot_generated_advanced_cli",
        ROOT / "examples" / "conversions" / "advanced_api_to_cli.py",
    )
    result = CliRunner().invoke(module.app, ["get_user", "7"])
    assert result.exit_code == 0, result.exception
    assert result.stdout == (
        "{'user_id': '7', 'username': 'example', 'role': 'member'}\n"
    )
    created = CliRunner().invoke(
        module.app,
        ["create_user", "ada", "ada@example.com"],
    )
    assert created.exit_code == 0, created.exception
    assert created.stdout == (
        "{'username': 'ada', 'email': 'ada@example.com', 'role': 'member', "
        "'created': True, 'status': 201}\n"
    )
    print("verified generated CLI command")


def verify_generated_mcp() -> None:
    module = _load_module(
        "intpot_generated_advanced_mcp",
        ROOT / "examples" / "conversions" / "advanced_api_to_mcp.py",
    )
    result = asyncio.run(module.mcp.call_tool("get_user", {"user_id": "7"}))
    assert result.is_error is False
    assert result.structured_content == {
        "user_id": "7",
        "username": "example",
        "role": "member",
    }
    created = asyncio.run(
        module.mcp.call_tool(
            "create_user",
            {"username": "ada", "email": "ada@example.com"},
        )
    )
    assert created.is_error is False
    assert created.structured_content == {
        "username": "ada",
        "email": "ada@example.com",
        "role": "member",
        "created": True,
        "status": 201,
    }
    print("verified generated MCP tool")


def verify_dependency_api() -> None:
    module = _load_module(
        "intpot_dependency_api",
        ROOT / "examples" / "dependency_api.py",
    )
    response = TestClient(module.app).get("/profile")
    assert response.status_code == 200
    assert response.json() == {"username": "example", "role": "member"}
    print("verified dependency FastAPI route")


def verify_generated_cli_to_api() -> None:
    basic = _load_module(
        "intpot_generated_cli_to_api",
        ROOT / "examples" / "conversions" / "cli_to_api.py",
    )
    greeted = TestClient(basic.app).post(
        "/greet", json={"name": "Ada", "greeting": "Hi"}
    )
    assert greeted.status_code == 200, greeted.text
    assert greeted.json() == {"result": "Hi, Ada!"}

    advanced = _load_module(
        "intpot_generated_advanced_cli_to_api",
        ROOT / "examples" / "conversions" / "advanced_cli_to_api.py",
    )
    searched = TestClient(advanced.app).post(
        "/search", json={"query": "alias", "include-done": True}
    )
    assert searched.status_code == 200, searched.text
    assert len(json.loads(searched.json()["result"])) == 2
    print("verified generated CLI-to-API parameter aliases")


def verify_semantic_schema() -> None:
    module = _load_module(
        "intpot_semantic_schema",
        ROOT / "examples" / "semantic_schema.py",
    )
    schema = module.app.schema
    payload = schema.to_dict()
    assert payload["name"] == "schema-example"
    assert payload["source_type"] == "python"
    assert [tool["name"] for tool in payload["tools"]] == ["greet"]
    assert [parameter["name"] for parameter in payload["tools"][0]["parameters"]] == [
        "name",
        "excited",
    ]
    print("verified semantic schema example")


def verify_missing_binding() -> None:
    module = _load_module(
        "intpot_missing_binding", ROOT / "examples" / "missing_binding.py"
    )
    response = TestClient(module.app).get("/calc", params={"x": 3})
    assert response.status_code == 200
    assert response.json() == 21
    output = StringIO()
    with redirect_stdout(output):
        module.main()
    assert "calc(3) = 21" in output.getvalue()
    assert "Cannot convert tools with missing bindings" in output.getvalue()
    print("verified missing-binding diagnostics and refusal example")


def verify_helper_recovery() -> None:
    module = _load_module(
        "intpot_helper_recovery", ROOT / "examples" / "helper_recovery.py"
    )
    output = StringIO()
    with redirect_stdout(output):
        module.main()
    assert "Generated cli: calc(3) = 21" in output.getvalue()
    assert "Generated mcp: calc(3) = 21" in output.getvalue()
    assert "Generated api: calc(3) = 21" in output.getvalue()
    print("verified bounded helper recovery through CLI API and MCP")


def verify_definition_bindings() -> None:
    module = _load_module(
        "intpot_definition_bindings", ROOT / "examples" / "definition_bindings.py"
    )
    output = StringIO()
    with redirect_stdout(output):
        module.main()
    assert output.getvalue().splitlines() == [
        "Original HTTP API: /value = 1",
        "cli: missing_annotation_binding names=['Model']",
        "mcp: missing_definition_binding names=['Model']",
        "CLI and MCP conversion refused before writing, including scaffold opt-in",
    ]
    print("verified definition-binding diagnostics and before-write refusal")
    context = _load_module(
        "intpot_diagnostic_context", ROOT / "examples" / "diagnostic_context.py"
    )
    output = StringIO()
    with redirect_stdout(output):
        context.main()
    diagnostics = json.loads(output.getvalue())
    assert {item["code"] for item in diagnostics} == {
        "missing_annotation_binding",
        "missing_definition_binding",
    }
    assert all(
        item["source_location"] is not None
        and Path(item["source_location"]["path"]).name == "original.py"
        and item["source_location"]["line"] == 10
        and item["source_location"]["end_line"] == 11
        and item["references"]
        and "Model" in item["suggested_action"]
        for item in diagnostics
    )
    print("verified actionable diagnostic context and before-write refusal")


def verify_application_conformance() -> None:
    cases = (
        (
            "application_conformance.py",
            "batch-order",
            {"source_cli", "generated_cli", "api", "mcp"},
        ),
        (
            "api_application_conformance.py",
            "storage-cost",
            {"source_api", "cli", "mcp"},
        ),
        (
            "mcp_application_conformance.py",
            "inventory-reservation",
            {"source_mcp", "cli", "api"},
        ),
    )
    for filename, label, interfaces in cases:
        module = _load_module(
            f"intpot_example_{label.replace('-', '_')}", ROOT / "examples" / filename
        )
        report = asyncio.run(module.verify())
        assert set(report["interfaces"]) == interfaces
        assert all(item["receipts_verified"] for item in report["interfaces"].values())
        print(f"verified {label} source and generated interfaces")


def verify_capability_examples(python: str | None = None) -> dict[str, str]:
    """Run the teaching scripts through native CLI, live HTTP, and stdio MCP."""
    import os
    import socket
    import subprocess
    import sys
    import tempfile
    import time
    from importlib import import_module

    try:
        http = import_module("httpx")
    except ModuleNotFoundError:
        http = import_module("httpx2")
    interpreter = python or sys.executable
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    # This is an application dependency, never a path to Intpot's source package.
    env["PYTHONPATH"] = str(ROOT / "examples")

    def run(
        arguments: list[str], *, succeeds: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [interpreter, *arguments],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (result.returncode == 0) == succeeds, (
            arguments,
            result.stdout,
            result.stderr,
        )
        return result

    summary: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="intpot-capabilities-") as directory:
        base = Path(directory)
        source = base / "input.txt"
        source.write_text("Curiosity & <science>\n", encoding="utf-8")
        provider = (
            run(
                [
                    "-c",
                    "import runpy,sys; ns=runpy.run_path(sys.argv[1]); print(callable(getattr(ns['version_callback'],'__annotate__',None)))",
                    str(ROOT / "examples/informational_text/app.py"),
                ]
            ).stdout.strip()
            == "True"
        )
        manifest_sources: list[str] = []
        for kind, tool in (
            ("enum", "export"),
            ("selected", "slug"),
            ("informational", "convert"),
            ("manifest", "manifest"),
        ):
            out = base / kind
            helper = (
                "convert_enum_export.py"
                if kind == "enum"
                else "convert_selected_tools.py"
                if kind == "selected"
                else "convert_file_manifest.py"
                if kind == "manifest"
                else "convert_informational.py"
            )
            command = [str(ROOT / "examples" / helper), "--output-dir", str(out)]
            if kind == "informational" and provider:
                refused = run(command, succeeds=False)
                assert "UnsupportedCLIParameterCallbackError" in refused.stderr
                assert not out.exists()
                summary[kind] = (
                    "provider-backed callbacks refused before output directory"
                )
                continue
            run(command)
            native = base / ("native-" + kind)
            if kind == "enum":
                native_args = [
                    str(ROOT / "examples/enum_export/app.py"),
                    str(source),
                    str(native),
                ]
                run(native_args)
                assert native.with_suffix(".txt").read_bytes() == source.read_bytes()
                repeat = run(
                    [*native_args, "--to", "html", "--to", "text", "--to", "html"]
                )
                assert repeat.stdout.count(str(native.with_suffix(".html"))) == 2
                bad_native = base / "native-invalid"
                run(
                    [*native_args[:2], str(bad_native), "--to", "invalid"],
                    succeeds=False,
                )
                assert (
                    not bad_native.with_suffix(".txt").exists()
                    and not bad_native.with_suffix(".html").exists()
                )
            elif kind == "selected":
                assert (
                    run(
                        [
                            str(ROOT / "examples/selected_tools.py"),
                            "slug",
                            "Hello World",
                        ]
                    ).stdout.strip()
                    == "hello-world"
                )
                refused = run(
                    [
                        "-c",
                        "import intpot,sys; intpot.load(sys.argv[1]).write(sys.argv[2], 'api')",
                        str(ROOT / "examples/selected_tools.py"),
                        str(base / "refused/whole.py"),
                    ],
                    succeeds=False,
                )
                assert "UnsupportedCLIParameterCallbackError" in refused.stderr
                assert not (base / "refused").exists()
            elif kind == "manifest":
                second = base / "second input.txt"
                second.write_text("A second input\n", encoding="utf-8")
                manifest_sources = [str(source), str(second), str(source)]
                run(
                    [
                        str(ROOT / "examples/file_manifest.py"),
                        *manifest_sources,
                        "--output",
                        str(native),
                        "--label",
                        "release",
                        "--label",
                        "A B",
                        "--label",
                        "release",
                    ]
                )
                assert json.loads(native.read_text())["count"] == 3
            else:
                run(
                    [
                        str(ROOT / "examples/informational_text/app.py"),
                        str(source),
                        str(native),
                        "--format",
                        "html",
                    ]
                )
                early = run(
                    [
                        str(ROOT / "examples/informational_text/app.py"),
                        "--version",
                        "--format",
                        "invalid",
                    ]
                )
                assert early.stdout.strip() == "informational-text 1.0"
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            with (base / (kind + ".log")).open("w") as log:
                server = subprocess.Popen(
                    [
                        interpreter,
                        "-m",
                        "uvicorn",
                        kind + "_api:app",
                        "--app-dir",
                        str(out),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                url = f"http://127.0.0.1:{port}"
                try:
                    for _ in range(200):
                        assert server.poll() is None, (
                            base / (kind + ".log")
                        ).read_text()
                        try:
                            schema = http.get(url + "/openapi.json")
                            if schema.status_code == 200:
                                break
                        except http.TransportError:
                            pass
                        time.sleep(0.05)
                    else:
                        raise AssertionError("example HTTP server did not become ready")
                    for transport in ("http", "mcp"):
                        target = base / (transport + "-" + kind)
                        payload = (
                            {
                                "source": str(source),
                                "output": str(target),
                                "to": ["html", "text", "html"],
                            }
                            if kind == "enum"
                            else {"text": "Hello World"}
                            if kind == "selected"
                            else {
                                "source": manifest_sources,
                                "output": str(target),
                                "label": ["release", "A B", "release"],
                            }
                            if kind == "manifest"
                            else {
                                "source": str(source),
                                "output": str(target),
                                "format": "html",
                            }
                        )
                        if transport == "http":
                            wire = "Hello World" if kind == "selected" else payload
                            response = http.post(
                                url + "/" + tool, json=wire, timeout=20
                            )
                            assert response.status_code == 200, response.text
                            result = response.json()["result"]
                        else:
                            result = run(
                                [
                                    str(ROOT / "examples/call_converted_mcp.py"),
                                    kind,
                                    json.dumps(payload),
                                    "--server-dir",
                                    str(out),
                                ]
                            ).stdout.strip()
                        if kind == "enum":
                            for suffix in (".txt", ".html"):
                                assert (
                                    target.with_suffix(suffix).read_bytes()
                                    == native.with_suffix(suffix).read_bytes()
                                )
                            bad = {
                                **payload,
                                "output": str(base / "invalid-enum"),
                                "to": ["invalid"],
                            }
                        elif kind == "selected":
                            assert result == "hello-world"
                            assert set(schema.json()["paths"]) == {"/slug"}
                            bad = {}
                        elif kind == "manifest":
                            assert target.read_bytes() == native.read_bytes()
                            bad = {
                                "source": [],
                                "output": str(base / "invalid-manifest"),
                            }
                        else:
                            assert target.read_bytes() == native.read_bytes()
                            early_payload = {"version": True, "format": "invalid"}
                            if transport == "http":
                                early_response = http.post(
                                    url + "/convert", json=early_payload, timeout=20
                                )
                                assert (
                                    early_response.status_code == 200
                                    and early_response.json()
                                    == {"result": "informational-text 1.0\n"}
                                )
                            else:
                                early_result = run(
                                    [
                                        str(ROOT / "examples/call_converted_mcp.py"),
                                        kind,
                                        json.dumps(early_payload),
                                        "--server-dir",
                                        str(out),
                                    ]
                                )
                                assert (
                                    early_result.stdout.strip()
                                    == "informational-text 1.0"
                                )
                            bad = {
                                "version": True,
                                "formats": True,
                                "output": str(base / "conflict"),
                            }
                        if transport == "http":
                            assert (
                                http.post(
                                    url + "/" + tool, json=bad, timeout=20
                                ).status_code
                                == 422
                            )
                        else:
                            run(
                                [
                                    str(ROOT / "examples/call_converted_mcp.py"),
                                    kind,
                                    json.dumps(bad),
                                    "--server-dir",
                                    str(out),
                                ],
                                succeeds=False,
                            )
                        assert not (base / "conflict").exists()
                        assert not (base / "invalid-manifest").exists()
                        assert (
                            not (base / "invalid-enum.txt").exists()
                            and not (base / "invalid-enum.html").exists()
                        )
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=8)
            summary[kind] = {
                "enum": "native/http/stdio-mcp byte parity; invalid inputs no files",
                "manifest": "native/http/stdio-mcp manifest parity; order/duplicates; empty required list no files",
                "selected": "only slug; native/http/stdio-mcp; full source refused",
                "informational": "native/http/stdio-mcp byte parity; early exit; conflicts rejected",
            }[kind]
    print(json.dumps(summary, sort_keys=True))
    return summary


def main() -> None:
    import sys

    verify_capability_examples()
    if "--capability-only" in sys.argv:
        return
    verify_generated_cli()
    verify_generated_mcp()
    verify_dependency_api()
    verify_generated_cli_to_api()
    verify_semantic_schema()
    verify_missing_binding()
    verify_helper_recovery()
    verify_definition_bindings()
    verify_application_conformance()


if __name__ == "__main__":
    main()
