"""Build and execute wheel/sdist consumers in clean external environments."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"{command!r} failed ({result.returncode})\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def main() -> None:
    artifacts = sorted((ROOT / "dist").glob("*"))
    wheels = [path for path in artifacts if path.suffix == ".whl"]
    sdists = [path for path in artifacts if path.name.endswith(".tar.gz")]
    assert len(wheels) == len(sdists) == 1, artifacts
    with tempfile.TemporaryDirectory(prefix="intpot-installed-") as temp:
        base = Path(temp)
        source = base / "consumer.py"
        source.write_text(
            "from fastapi import FastAPI\napp = FastAPI()\nFACTOR = 7\n"
            "def scale(x):\n    return x * FACTOR\n"
            "@app.get('/calc')\ndef calc(x: int) -> int:\n    return scale(x)\n"
        )
        for artifact in (wheels[0], sdists[0]):
            kind = "sdist" if artifact.name.endswith(".tar.gz") else "wheel"
            home = base / kind
            venv.EnvBuilder(with_pip=False, symlinks=True).create(home)
            python = home / "bin" / "python"
            cli = home / "bin" / "intpot"
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["PYTHONNOUSERSITE"] = "1"
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--disable-pip-version-check",
                    str(artifact),
                    "fastapi",
                    "httpx",
                    "fastmcp",
                ],
                cwd=base,
                env=env,
            )
            version = run(
                [
                    str(python),
                    "-c",
                    "import intpot,pathlib,sys; p=pathlib.Path(intpot.__file__).resolve(); assert p.is_relative_to(pathlib.Path(sys.prefix).resolve()), p; print(intpot.__version__)",
                ],
                cwd=base,
                env=env,
            ).strip()
            assert (
                run([str(cli), "--version"], cwd=base, env=env).strip()
                == f"intpot {version}"
            )
            skills = base / f"skills-{kind}"
            skills.mkdir()
            run(
                [str(cli), "add", "skills", "--agent", "codex", "--path", str(skills)],
                cwd=base,
                env=env,
            )
            assert (skills / "AGENTS.md").is_file()
            assert "intpot CLI" in (skills / "AGENTS.md").read_text()
            for target in ("cli", "api", "mcp"):
                generated = base / f"{target}-{kind}.py"
                consumer_source = source
                if target == "api":
                    consumer_source = base / "cli_source.py"
                    consumer_source.write_text(
                        "import typer\napp=typer.Typer(add_completion=False)\n"
                        "FACTOR=7\ndef scale(x):\n    return x*FACTOR\n"
                        "@app.command()\ndef calc(x:int):\n    typer.echo(scale(x))\n"
                    )
                run(
                    [
                        str(cli),
                        "to",
                        target,
                        str(consumer_source),
                        "--output",
                        str(generated),
                    ],
                    cwd=base,
                    env=env,
                )
                if target == "cli":
                    script = (
                        "import importlib.util,sys; s=importlib.util.spec_from_file_location('g',sys.argv[1]);"
                        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m);"
                        "from typer.testing import CliRunner; r=CliRunner().invoke(m.app,['3']);"
                        "assert r.exit_code==0,r.exception; assert r.stdout=='21\\n',r.stdout"
                    )
                elif target == "api":
                    script = (
                        "import importlib.util,sys; s=importlib.util.spec_from_file_location('g',sys.argv[1]);"
                        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m);"
                        "from fastapi.testclient import TestClient; r=TestClient(m.app).post('/calc',json=3);"
                        "assert r.status_code==200,r.text; assert r.json()=={'result':21},r.json()"
                    )
                else:
                    script = (
                        "import importlib.util,sys,asyncio; s=importlib.util.spec_from_file_location('g',sys.argv[1]);"
                        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m);"
                        "\nfrom fastmcp import Client\n"
                        "async def run():\n async with Client(m.mcp) as c: return await c.call_tool('calc',{'x':3})\n"
                        "r=asyncio.run(run());"
                        "v=(r[0].text if isinstance(r,list) else getattr(r,'structured_content',None));"
                        "v=(v['result'] if isinstance(v,dict) and 'result' in v else v if isinstance(v,str) else r.content[0].text);"
                        "assert str(v)=='21',r"
                    )
                run([str(python), "-c", script, str(generated)], cwd=base, env=env)
            diagnostics = json.loads(
                run(
                    [str(python), str(ROOT / "examples" / "diagnostic_context.py")],
                    cwd=base,
                    env=env,
                )
            )
            assert len(diagnostics) == 2
            assert all(
                item["source_location"] is not None
                and Path(item["source_location"]["path"]).name == "original.py"
                and item["source_location"]["line"] == 10
                and item["source_location"]["end_line"] == 11
                and item["references"]
                and "Model" in item["suggested_action"]
                for item in diagnostics
            )
            provenance = json.loads(
                run(
                    [str(python), str(ROOT / "examples" / "source_provenance.py")],
                    cwd=base,
                    env=env,
                )
            )
            assert provenance["original_result"] == 21
            assert provenance["cli_json_parity"] and provenance["refused_before_write"]
            assert provenance["unavailable_location"] is None
            chains = json.loads(
                run(
                    [str(python), str(ROOT / "examples" / "binding_chains.py")],
                    cwd=base,
                    env=env,
                )
            )
            assert (
                chains["original_http_result"] == chains["generated_cli_result"] == 21
            )
            assert chains["fixture_kind"] == "caller-authored incomplete schema"
            assert chains["cli_json_parity"] and chains["refused_before_write"]
            assert all(
                ref["dependency_chain"] == ["calc", "_calc_impl", "scale", "leaf"]
                for item in chains["fixture_diagnostics"]
                for ref in item["references"]
            )
            occurrences = json.loads(
                run(
                    [str(python), str(ROOT / "examples" / "reference_locations.py")],
                    cwd=base,
                    env=env,
                )
            )
            assert occurrences["original_result"] == 21
            assert (
                occurrences["cli_json_parity"]
                and occurrences["refused_before_write"]
                and occurrences["unavailable_after_change"]
            )
            assert occurrences["diagnostics"][0]["references"][0]["reference_locations"]
            print(
                f"verified {kind} {artifact.name}: version, shipped skills, generated CLI/API/MCP, diagnostic context, source provenance, binding chains, reference occurrences"
            )


if __name__ == "__main__":
    main()
