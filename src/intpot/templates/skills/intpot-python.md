# intpot Python API

**intpot** exposes two APIs: `intpot.App` for defining tools once and serving them as a
CLI, API, or MCP server, and `intpot.load()` for converting existing framework code
programmatically.

## When to Use

- Define tools once and serve or export them in any framework — `App`
- Convert apps inside scripts, build tools, or CI — `load()`
- Inspect an app as stable framework-neutral data — `.schema`
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

`async def` tools work in every mode. Variadic tool signatures using `*args` or `**kwargs`
are rejected because they cannot expose one consistent CLI, API, and MCP interface; use
explicit named parameters instead.

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
print(app.schema.to_dict())               # inspect canonical source semantics
api_schema = app.project("api")           # inspect target semantics before generation
```

Calling `to_cli()` on a source that is already a CLI raises `ValueError`; same for the
other two.

Generated strings still need runtime verification. Successful generation does not prove
the result works: compile it, import it with its runtime dependencies installed, then
invoke a real CLI command, API request, or MCP tool.

Current unsupported or lossy conversions include nested Typer sub-apps, repeatable CLI
options, some FastAPI `Annotated[..., Body(...)]` parameters, factory-created apps, and
routes with multiple HTTP methods. FastAPI `Depends()`, `Security()`, nested, and
route/router/app-level dependencies remain available through `.tools` and `inspect_app`,
but `.to_cli()`, `.to_mcp()`, and `.write()` raise
`intpot.UnsupportedFastAPIDependencyError` rather than emit broken code. Full dependency
mapping remains tracked in issue #20. A body that cannot be recovered becomes a
`# TODO: implement` stub; inspect and implement it before treating the output as complete.

intpot carries direct import statements referenced by a tool body. It does not yet copy
same-module helpers, constants, classes, models, or closure values. It does not discover
or install transitive dependencies across imported modules. Direct file loading does not
add the source directory to `sys.path`, so sibling imports may require installing the
package or setting `PYTHONPATH`. intpot does not reproduce configuration or provision
external services.

## Canonical application schema

Both `intpot.App` and `IntpotApp` expose `.schema`, an immutable
`ApplicationSchema`. It contains immutable `ToolSchema` and `ParameterSchema` records;
`.project("cli" | "mcp" | "api")` returns the exact target semantics used for
generation without mutating the source snapshot. `.to_dict()` provides a sentinel-free,
JSON-compatible representation for inspection. Supported non-JSON defaults use tagged
dictionaries; opaque mutable defaults are rejected rather than exposed through the frozen
schema.

```python
schema = app.schema
print(schema.name, schema.source_type, schema.target_type)
print(schema.to_dict())

for tool in schema.tools:
    print(tool.name, tool.description, tool.return_type, tool.is_async)
    for param in tool.parameters:
        print(param.name, param.type_annotation, param.required)
```

`.tools` remains available for compatibility and returns detached mutable `ToolInfo`
objects. Mutating those objects does not change `.schema` or later generated code.

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
from intpot import SourceType, inspect_app

tools = inspect_app(SourceType.MCP, mcp_instance)
```

## Installation

```bash
pip install intpot[all]   # install both framework runtimes
```

Install `[mcp]` or `[api]` when intpot must inspect or load a source using that framework,
or when you import, serve, or invoke that target. Emitting source text alone does not
require the target extra, but verifying or running the emitted program does.
