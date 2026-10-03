---
title: Build and run an Intpot app
description: Create one typed App, serve it through a real CLI or HTTP interface, and test the generated contract.
---

This guide takes a small declaration from source to a locally exercised CLI and HTTP endpoint. It uses a deterministic function, not a model or external service.

## Requirements and install

Use Python 3.11 or newer. Install the interface extras you intend to run; the base package includes Typer but not FastAPI/Uvicorn or FastMCP.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install 'intpot[api]'
```

For CLI-only work install `intpot`; for MCP install `intpot[mcp]`; for all three install `intpot[all]`. On Windows activate the virtual environment with `.venv\Scripts\activate`.

## Declare a tool

Save as `app.py`:

```python
from intpot import App

app = App("greetings")

@app.tool()
def greet(name: str, excited: bool = False) -> str:
    """Greet one person."""
    suffix = "!" if excited else "."
    return f"Hello, {name}{suffix}"
```

The decorator registers the original callable and captures its name, docstring, signature, annotations, defaults, async status, body, and source imports for interface construction and code generation. Parameters must be explicit: `*args` and `**kwargs` are rejected because they do not map consistently to all three interfaces.

## Run the real CLI

```sh
intpot serve app.py --cli -- greet Ada --excited
```

The separator passes arguments to the generated Typer command when they could otherwise be interpreted by Intpot. This invokes the registered function; do not run untrusted application modules merely to inspect them.

## Serve and call HTTP

Start the server in one terminal:

```sh
intpot serve app.py --api --host 127.0.0.1 --port 8000
```

In another terminal, call the generated route:

```sh
curl -i -X POST http://127.0.0.1:8000/greet \
  -H 'content-type: application/json' \
  -d '{"name":"Ada","excited":true}'
```

The default API host is loopback (`127.0.0.1`) and the default port is `8000`; use `0.0.0.0` only when you intentionally want network exposure. FastAPI request validation applies to the generated operation. Exercise your actual responses and error cases; this example's deterministic return value is `Hello, Ada!`.

## Inspect the interface schema

Before starting a server, build the FastAPI app and inspect its OpenAPI schema:

```python
from intpot.runtime_builders import build_fastapi_app

api = build_fastapi_app(app.name, app._tools)
operation = api.openapi()["paths"]["/greet"]["post"]
assert operation["operationId"] == "greet_greet_post"
assert operation["requestBody"]["required"] is True
```

The JSON body fields derive from the Python parameters. A default makes a parameter optional; an omitted default marks it required. Route details for converted FastAPI apps can carry method, path, operation ID, summary, description, tags, and deprecation metadata when the inspector can recover them. See [schema and parameter reference](/schema-reference/).

## Async tools and generated code

`async def` is recognized and marked async in the schema. Inspect generated source and execute it under the target framework rather than assuming every framework feature has identical scheduling semantics. `app.eject("api")`, `app.eject("cli")`, and `app.eject("mcp")` return generated Python source; `intpot eject app.py --to api --output generated_api.py` writes it. Ejected source imports the chosen framework directly and does not require Intpot at runtime, but does require that target framework's dependencies.

## Verify generated applications

A successful conversion only establishes that Intpot generated source. For each generated target: inspect the file, compile it with `python -m py_compile generated_api.py`, install the target extra, start it using the framework's documented entry point, and call a representative success and invalid-input case. Compare behavior against the source app, especially defaults, request placement, async functions, exceptions, imports, and side effects. Keep these checks in your project's tests; conversion cannot preserve arbitrary framework middleware, lifecycle hooks, or application configuration.

## Common failures

- **Missing optional framework:** install `intpot[api]` or `intpot[mcp]` as appropriate.
- **No App found:** `intpot serve` expects a Python file defining a public `intpot.App` instance.
- **Import-time exception:** detection imports the file. Put command-line startup under `if __name__ == "__main__":` and avoid import-time side effects.
- **Port unavailable:** choose an unused local port and pass `--port`.
- **Conversion rejects FastAPI dependencies:** see [conversion boundaries](/conversion-boundaries/); dependencies cannot be safely mapped to CLI/MCP.

## Next steps

Read [conversion boundaries](/conversion-boundaries/), then [schema and parameter reference](/schema-reference/) and [architecture internals](/architecture-internals/). The [cookbook](https://github.com/tugrulguner/intpot/blob/main/docs/cookbook.md) has additional recipes. [Download this guide as Markdown](/downloads/build-an-app.md).
