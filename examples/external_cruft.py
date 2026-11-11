#!/usr/bin/env python3
"""Reproduce a bounded Cruft create workflow through native and generated clients.

This case study uses only a synthetic local Cookiecutter template; it never
modifies the pinned Cruft checkout. See external-applications/cruft.md.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PIN = "33f6b722fc6fe4b5d26a351e487372e5e4375ab2"
EXPECTED_PACKAGES = (
    "cruft",
    "intpot",
    "typer",
    "click",
    "cookiecutter",
    "fastapi",
    "fastmcp",
)


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def record_process(
    report: dict, evidence: Path, label: str, argv: list[str], env: dict
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        argv, cwd=evidence, env=env, capture_output=True, text=True, timeout=60
    )
    (evidence / f"{label}.stdout").write_text(result.stdout)
    (evidence / f"{label}.stderr").write_text(result.stderr)
    report["commands"].append(
        {
            "name": label,
            "argv": argv,
            "exit_code": result.returncode,
            "stdout_file": f"{label}.stdout",
            "stderr_file": f"{label}.stderr",
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="must not exist")
    args = parser.parse_args()
    source = args.source_checkout.resolve(strict=True)
    output = args.output_dir.absolute()
    if output.exists():
        parser.error(f"output directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output
    evidence.mkdir()
    report: dict = {
        "source_checkout": str(source),
        "source_pin": PIN,
        "commands": [],
        "cases": [],
        "template_is_explicitly_synthetic": True,
        "full_application_conversion_verified": False,
        "limitations": [
            "no_input=True",
            "default_config=True",
            "local trusted synthetic template",
            "absolute existing output parents",
            "full Cruft application not converted",
        ],
    }
    report_path = evidence / "report.json"

    def save() -> None:
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n"
        )

    def check(
        command: list[str], label: str, env: dict | None = None
    ) -> subprocess.CompletedProcess:
        result = record_process(
            report,
            evidence,
            label,
            command,
            env
            or {
                **os.environ,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
            },
        )
        save()
        if result.returncode:
            raise RuntimeError(
                f"{label} failed with exit {result.returncode}; see {report_path}"
            )
        return result

    try:
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(source), "status", "--porcelain"], text=True
        )
        cruft_file = source / "cruft" / "__init__.py"
        if not cruft_file.is_file() or not cruft_file.read_bytes():
            raise RuntimeError("pinned source lacks cruft/__init__.py")
        license_file = next(
            (
                p
                for p in (
                    source / "LICENSE",
                    source / "LICENSE.md",
                    source / "LICENSE.txt",
                )
                if p.is_file()
            ),
            None,
        )
        if license_file is None or "MIT License" not in license_file.read_text(
            errors="replace"
        ):
            raise RuntimeError("pinned source checkout lacks its MIT license")
        if commit != PIN or dirty.strip():
            raise RuntimeError(
                "source checkout must be the exact clean MIT-pinned checkout"
            )
        cruft_mod = importlib.import_module("cruft")
        if cruft_mod.__file__ is None:
            raise RuntimeError("installed Cruft module has no source file")
        installed_root = Path(cruft_mod.__file__).resolve().parent
        verified: list[str] = []
        for path in sorted((source / "cruft").rglob("*.py")):
            relative = path.relative_to(source / "cruft")
            installed = installed_root / relative
            if not installed.is_file() or installed.read_bytes() != path.read_bytes():
                raise RuntimeError(f"installed Cruft source mismatch: cruft/{relative}")
            verified.append(f"cruft/{relative}")
        if len(verified) != 18:
            raise RuntimeError(
                f"expected 18 installed Cruft package Python files, verified {len(verified)}"
            )
        report.update(
            {
                "source_commit": commit,
                "source_clean": True,
                "license": "MIT",
                "installed_source_root": str(installed_root),
                "installed_python_files_byte_verified": verified,
                "installed_python_file_count": len(verified),
                "versions": {
                    name: importlib.metadata.version(name) for name in EXPECTED_PACKAGES
                },
                "python_executable": sys.executable,
            }
        )
        save()

        template = evidence / "synthetic-template"
        (template / "{{cookiecutter.project_slug}}").mkdir(parents=True)
        (template / "cookiecutter.json").write_text(
            json.dumps(
                {
                    "project_slug": "synthetic_project",
                    "package_name": "synthetic_package",
                },
                indent=2,
            )
            + "\n"
        )
        (template / "README.md").write_text(
            "# Synthetic local Cruft fixture\n\nThis fixture contains no upstream application data.\n"
        )
        (template / "{{cookiecutter.project_slug}}" / "README.md").write_text(
            "# {{ cookiecutter.project_slug }}\n\nPackage: {{ cookiecutter.package_name }}\n"
        )
        check(["git", "init", str(template)], "fixture-git-init")
        check(
            [
                "git",
                "-C",
                str(template),
                "-c",
                "user.name=Synthetic Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "add",
                ".",
            ],
            "fixture-git-add",
        )
        check(
            [
                "git",
                "-C",
                str(template),
                "-c",
                "user.name=Synthetic Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "Synthetic local template fixture",
            ],
            "fixture-git-commit",
        )
        report["fixture_commit"] = subprocess.check_output(
            ["git", "-C", str(template), "rev-parse", "HEAD"], text=True
        ).strip()
        save()

        cli = importlib.import_module("cruft._cli")
        intpot_module = importlib.import_module("intpot")
        report["intpot_source"] = intpot_module.__file__
        transforms_module = importlib.import_module("intpot.core.transforms")
        if transforms_module.__file__ is None:
            raise RuntimeError("installed Intpot transforms module has no source file")
        transforms_path = Path(transforms_module.__file__)
        report["intpot_transforms"] = {
            "file": str(transforms_path),
            "sha256": hashlib.sha256(transforms_path.read_bytes()).hexdigest(),
        }
        app = intpot_module.load(cli.app).select("create")
        assessment = app.assess()
        report["assessment"] = assessment
        report["selected_names"] = [tool.name for tool in app.schema.tools]
        if report["selected_names"] != ["create"]:
            raise RuntimeError(f"unexpected selected tools: {report['selected_names']}")
        api_path, mcp_path = (
            evidence / "generated_cruft_api.py",
            evidence / "generated_cruft_mcp.py",
        )
        api_path.write_text(app.to_api())
        mcp_path.write_text(app.to_mcp())
        report["generated_files"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (api_path, mcp_path)
        }
        save()

        home = evidence / "isolated-home"
        home.mkdir()
        env = os.environ.copy()
        env.update(
            HOME=str(home),
            TMPDIR=str(output.parent),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
        )
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        context = {
            "project_slug": "consumer_result",
            "package_name": "toolkit_İstanbul",
        }
        parents = {key: evidence / key for key in ("native", "http", "mcp")}
        for parent in parents.values():
            parent.mkdir()
        native_cli = str(Path(sys.executable).with_name("cruft"))
        native_argv = [
            native_cli,
            "create",
            str(template),
            "--output-dir",
            str(parents["native"]),
            "--no-input",
            "--default-config",
            "--extra-context",
            json.dumps(context),
            "--skip",
            "cache",
            "--skip",
            "tmp",
        ]

        def native_case(
            label: str, overwrite: bool = False, expected_success: bool = True
        ) -> dict:
            before = snapshot(parents["native"])
            argv = native_argv + (["--overwrite-if-exists"] if overwrite else [])
            result = record_process(report, evidence, label, argv, env)
            after = snapshot(parents["native"])
            item = {
                "name": label,
                "exit_code": result.returncode,
                "before": before,
                "after": after,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            report["cases"].append(item)
            save()
            if (result.returncode == 0) != expected_success:
                raise RuntimeError(
                    f"{label} unexpected native exit {result.returncode}; details in {report_path}"
                )
            return item

        native_case("native-create")
        expected = snapshot(parents["native"])
        if set(expected) != {
            "consumer_result/README.md",
            "consumer_result/.cruft.json",
        }:
            raise RuntimeError(f"unexpected fixture output files: {sorted(expected)}")
        native_case("native-existing-refusal", expected_success=False)
        if snapshot(parents["native"]) != expected:
            raise RuntimeError("native existing-destination refusal changed tree")
        (parents["native"] / "consumer_result" / "README.md").write_text("SENTINEL")
        native_case("native-explicit-overwrite", overwrite=True)
        if snapshot(parents["native"]) != expected:
            raise RuntimeError("native explicit overwrite did not restore bytes")

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        def http_request(data=None):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/create",
                data=None if data is None else json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=35) as response:
                    return response.status, response.read().decode()
            except urllib.error.HTTPError as error:
                return error.code, error.read().decode()

        log = (evidence / "http-server.log").open("w")
        http_argv = [
            sys.executable,
            "-m",
            "uvicorn",
            "generated_cruft_api:app",
            "--app-dir",
            str(evidence),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        report["commands"].append(
            {
                "name": "generated-http-server",
                "argv": http_argv,
                "log_file": "http-server.log",
            }
        )
        save()
        server = subprocess.Popen(
            http_argv,
            cwd=evidence,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(150):
                if server.poll() is not None:
                    raise RuntimeError(
                        "generated HTTP server exited; inspect http-server.log"
                    )
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/openapi.json", timeout=2
                    ) as response:
                        schema = json.load(response)
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("generated HTTP server readiness timeout")
            if set(schema["paths"]) != {"/create"}:
                raise RuntimeError(
                    "generated HTTP surface does not match selected create operation"
                )
            for name, overwrite, expected_status in (
                ("http-create", False, 200),
                ("http-existing-refusal", False, 500),
                ("http-explicit-overwrite", True, 200),
            ):
                if overwrite:
                    (parents["http"] / "consumer_result" / "README.md").write_text(
                        "SENTINEL"
                    )
                before = snapshot(parents["http"])
                body = {
                    "template_git_url": str(template),
                    "output-dir": str(parents["http"]),
                    "no-input": True,
                    "default-config": True,
                    "extra-context": json.dumps(context),
                    "overwrite-if-exists": overwrite,
                    "skip": ["cache", "tmp"],
                }
                status, response = http_request(body)
                after = snapshot(parents["http"])
                report["cases"].append(
                    {
                        "name": name,
                        "status": status,
                        "request": body,
                        "response": response,
                        "before": before,
                        "after": after,
                    }
                )
                save()
                if status != expected_status or after != expected:
                    raise RuntimeError(
                        f"{name} failed status/tree assertion; report: {report_path}"
                    )
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            log.close()
            report["http_process_reaped"] = server.poll() is not None
            save()

        Client = importlib.import_module("fastmcp").Client
        StdioTransport = importlib.import_module(
            "fastmcp.client.transports"
        ).StdioTransport

        async def mcp_cases():
            transport_args = [str(mcp_path)]
            report["commands"].append(
                {
                    "name": "generated-stdio-mcp-server",
                    "argv": [sys.executable, *transport_args],
                    "log_file": "mcp-server.log",
                }
            )
            save()
            transport = StdioTransport(
                sys.executable,
                transport_args,
                env=env,
                cwd=str(evidence),
                log_file=evidence / "mcp-server.log",
            )
            async with Client(transport) as client:
                tools = await client.list_tools()
                names = [tool.name for tool in tools]
                if names != ["create"]:
                    raise RuntimeError(f"stdio MCP exposed tools {names}")
                for name, overwrite, is_error in (
                    ("mcp-create", False, False),
                    ("mcp-existing-refusal", False, True),
                    ("mcp-explicit-overwrite", True, False),
                ):
                    if overwrite:
                        (parents["mcp"] / "consumer_result" / "README.md").write_text(
                            "SENTINEL"
                        )
                    before = snapshot(parents["mcp"])
                    call_args = {
                        "template_git_url": str(template),
                        "output_dir": str(parents["mcp"]),
                        "no_input": True,
                        "default_config": True,
                        "extra_context": json.dumps(context),
                        "overwrite_if_exists": overwrite,
                        "skip": ["cache", "tmp"],
                    }
                    try:
                        result = await client.call_tool(
                            "create", call_args, raise_on_error=False
                        )
                        actual_error = bool(result.is_error)
                        content = [
                            getattr(item, "text", None) for item in result.content
                        ]
                        error_state = None
                    except Exception as error:
                        after = snapshot(parents["mcp"])
                        report["cases"].append(
                            {
                                "name": name,
                                "arguments": call_args,
                                "client_exception": {
                                    "type": type(error).__name__,
                                    "message": str(error),
                                },
                                "before": before,
                                "after": after,
                                "client_call_failed": True,
                            }
                        )
                        save()
                        raise RuntimeError(
                            f"{name} raised in the MCP client; see {report_path}"
                        ) from error
                    after = snapshot(parents["mcp"])
                    report["cases"].append(
                        {
                            "name": name,
                            "arguments": call_args,
                            "is_error": actual_error,
                            "content": content,
                            "error": error_state,
                            "before": before,
                            "after": after,
                        }
                    )
                    save()
                    if actual_error != is_error or after != expected:
                        raise RuntimeError(
                            f"{name} failed native client/tree assertion; report: {report_path}"
                        )

        asyncio.run(mcp_cases())
        report.update(
            selected_project_creation_verified=True,
            native_http_mcp_byte_parity=True,
            existing_destination_refusal_verified=True,
            overwrite_restores_original_bytes=True,
            completed=True,
        )
        save()
        print(report_path)
        return 0
    except Exception as error:
        report["completed"] = False
        report["failure"] = {"type": type(error).__name__, "message": str(error)}
        save()
        print(report_path, file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
