# intpot Python API

**intpot** provides a Python API for converting between Typer (CLI), FastMCP (MCP), and FastAPI (API) apps programmatically.

## When to Use

Use the Python API when you need to:
- Convert apps programmatically within scripts or pipelines
- Inspect app functions/tools/endpoints as normalized data
- Generate code from live app instances (not just files)
- Integrate intpot into build tools or CI/CD

## Core API

### `intpot.load(source)`

Load a file path or live app instance. Returns an `IntpotApp`.

```python
import intpot

# From a file path
app = intpot.load("mcp_server.py")

# From a live FastMCP instance
from fastmcp import FastMCP
mcp = FastMCP("my-server")

@mcp.tool()
def greet(name: str) -> str:
    return f"Hello, {name}!"

app = intpot.load(mcp)
```

### `IntpotApp` methods

```python
app = intpot.load("server.py")

# Generate code as strings
cli_code = app.to_cli()
mcp_code = app.to_mcp()
api_code = app.to_api()

# Write directly to files
app.write("output/cli_app.py", "cli")
app.write("output/api_app.py", "api")
app.write("output/mcp_server.py", "mcp")

# Inspect normalized tools
for tool in app.tools:
    print(tool.name, tool.description)
    for param in tool.parameters:
        print(f"  {param.name}: {param.annotation} = {param.default}")

# Check detected source type
print(app.source_type)  # SourceType.MCP, SourceType.CLI, or SourceType.API
```

### `intpot.inspect_app(source_type, app_instance)`

Low-level inspection — extract `ToolInfo` list from a live app instance.

```python
from intpot import inspect_app
from intpot.core.models import SourceType

tools = inspect_app(SourceType.MCP, mcp_instance)
for tool in tools:
    print(tool.name, [p.name for p in tool.parameters])
```

## Installation

```python
pip install intpot[all]  # includes fastmcp + fastapi extras
```
