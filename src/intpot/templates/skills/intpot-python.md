# intpot Python API

**intpot** exposes two APIs: `intpot.App` for defining tools once and serving them as a
CLI, API, or MCP server, and `intpot.load()` for converting existing framework code
programmatically.

## When to Use

- Define tools once and serve or export them in any framework — `App`
- Convert apps inside scripts, build tools, or CI — `load()`
- Read an app's functions as normalized data — `.tools`
- Generate from a live app instance rather than a file — `load(instance)`

## `intpot.App` — write once, serve everywhere

```python
from intpot import App

app = App("my-app")

@app.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
```

The tool's name and description default to the function name and its docstring. Override
either — useful when the docstring explains the code to a maintainer but an agent needs
different wording:

```python
@app.tool(name="lookup", description="Look up a customer by account number.")
def fetch_customer_record(account_id: str) -> dict:
    """Hit the accounts table. Caller must have validated account_id."""
    ...
```

`async def` tools work in every mode.

### Serving and exporting

```python
app.serve(mode="cli")                     # run as a Typer CLI
app.serve(mode="api", port=8000)          # FastAPI on 127.0.0.1 by default
app.serve(mode="api", host="0.0.0.0")     # opt in to network exposure
app.serve(mode="mcp")                     # FastMCP server

cli_code = app.eject("cli")               # standalone source, as a string
api_code = app.eject("api")
mcp_code = app.eject("mcp")
```

`serve(mode="api")` and `eject("api")` expose the same HTTP interface: arguments come
from a JSON request body.

## `intpot.load(source)` — convert existing code

Accepts a file path or a live app instance; returns an `IntpotApp`.

```python
import intpot

app = intpot.load("mcp_server.py")

from fastmcp import FastMCP
mcp = FastMCP("my-server")

@mcp.tool()
def greet(name: str) -> str:
    return f"Hello, {name}!"

app = intpot.load(mcp)
```

`load()` executes the file to find the app instance — treat unfamiliar sources with the
same caution as `exec`.

### `IntpotApp`

```python
app = intpot.load("server.py")

cli_code = app.to_cli()                   # generated source, as a string
mcp_code = app.to_mcp()
api_code = app.to_api()

app.write("output/cli_app.py", "cli")     # generate and write, returns the Path

print(app.source_type)                    # SourceType.MCP / CLI / API
```

Calling `to_cli()` on a source that is already a CLI raises `ValueError`; same for the
other two.

## Normalized tool data

`.tools` returns `ToolInfo` objects — the schema both halves of intpot meet at.

```python
for tool in app.tools:
    print(tool.name, tool.description, tool.return_type, tool.is_async)
    for param in tool.parameters:
        print(f"  {param.name}: {param.type_annotation}")
        print(f"    required={param.required} default={param.default}")
```

`ToolInfo` fields: `name`, `description`, `parameters`, `return_type`, `http_method`,
`function_body`, `is_async`, `route_path`, `dependencies`, `source_imports`.

`ParameterInfo` fields: `name`, `type_annotation`, `default`, `description`,
`param_source`, plus a `required` property. **The type field is `type_annotation`, not
`annotation`.** `default` is a private sentinel when the parameter is required — check
`param.required` rather than comparing against `None`.

`param_source` is `ParamSource.query` / `header` / `path` / `body` for FastAPI sources
that declared one, otherwise `None`.

### `intpot.inspect_app(source_type, app_instance)`

Low-level: extract `ToolInfo` from a live instance without wrapping it.

```python
from intpot import inspect_app
from intpot.core.models import SourceType

tools = inspect_app(SourceType.MCP, mcp_instance)
```

## Installation

```bash
pip install intpot[all]   # includes the fastmcp and fastapi extras
```
