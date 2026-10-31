from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from fastmcp import Client

import intpot


def test_conditional_import_is_retained_for_native_consumers(tmp_source):
    path = tmp_source("""
        import typer
        if True:
            from json import dumps as encode
            app = typer.Typer()
            @app.command()
            def mapping() -> None:
                typer.echo(encode({"given": "first_name"}))
    """)
    app = intpot.load(path)
    api = {}
    exec(app.to_api(), api)
    with TestClient(api["app"]) as client:
        result = client.post("/mapping")
        assert result.status_code == 200
        assert json.loads(result.json()["result"]) == {"given": "first_name"}
    mcp = {}
    exec(app.to_mcp(), mcp)

    async def call() -> None:
        async with Client(mcp["mcp"]) as client:
            result = await client.call_tool("mapping", {})
            assert json.loads(result.content[0].text) == {"given": "first_name"}

    asyncio.run(call())


def test_inactive_conditional_import_is_not_copied(tmp_source):
    path = tmp_source("""
        import typer
        if False:
            from missing_optional_dependency import encode
        else:
            from json import dumps as encode
        app = typer.Typer()
        @app.command()
        def mapping() -> None:
            typer.echo(encode({"ok": True}))
    """)
    app = intpot.load(path)
    imports = app.tools[0].source_imports
    assert "from json import dumps as encode" in imports
    assert not any("missing_optional_dependency" in item for item in imports)
    namespace = {}
    exec(app.to_api(), namespace)
    with TestClient(namespace["app"]) as client:
        assert json.loads(client.post("/mapping").json()["result"]) == {"ok": True}


def test_rebound_conditional_import_is_not_claimed(tmp_source):
    path = tmp_source("""
        import typer
        if True:
            from json import dumps as encode
        encode = print
        app = typer.Typer()
        @app.command()
        def mapping() -> None:
            typer.echo(encode({"ok": True}))
    """)
    app = intpot.load(path)
    assert not any("json" in item for item in app.tools[0].source_imports)
    import pytest

    with pytest.raises(intpot.MissingBindingError, match="encode"):
        app.to_api()


def test_nested_try_import_alias_matches_loaded_module(tmp_source):
    path = tmp_source("""
        import typer
        try:
            if True:
                import json as serializer
        except ImportError:
            serializer = None
        app = typer.Typer()
        @app.command()
        def mapping() -> None:
            typer.echo(serializer.dumps({"ok": True}))
    """)
    app = intpot.load(path)
    assert "import json as serializer" in app.tools[0].source_imports
    namespace = {}
    exec(app.to_api(), namespace)
    with TestClient(namespace["app"]) as client:
        assert json.loads(client.post("/mapping").json()["result"]) == {"ok": True}
