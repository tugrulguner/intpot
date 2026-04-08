# Cookbook

Practical patterns, tips, and gotchas for converting between frameworks with intpot.

## Basic conversions

### CLI to API

```bash
intpot to api cli_app.py
```

Typer arguments become `Body(...)` fields, options become `Body(default=...)`. All commands turn into POST endpoints named after the function.

**Before (Typer):**
```python
@app.command()
def create_task(
    title: str = typer.Argument(..., help="Task title"),
    priority: int = typer.Option(3, help="Priority 1-5"),
) -> None:
    typer.echo(json.dumps({"title": title, "priority": priority}))
```

**After (FastAPI):**
```python
@app.post("/create_task")
def create_task(
    title: str = Body(..., description="Task title"),
    priority: int = Body(default=3, description="Priority 1-5"),
) -> str:
    return json.dumps({"title": title, "priority": priority})
```

Note: `typer.echo(X)` becomes `return X`. The return type here is `str` because `json.dumps()` returns a string — intpot sets it based on what the function body actually returns.

### CLI to MCP

```bash
intpot to mcp cli_app.py
```

Same idea — arguments and options flatten into regular function parameters. `typer.echo(X)` becomes `return X`, return type becomes `str`.

```python
# before
def greet(name: str = typer.Argument(...), greeting: str = typer.Option("Hello")) -> None:
    typer.echo(f"{greeting}, {name}!")

# after
@mcp.tool()
def greet(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"
```

### MCP to CLI

```bash
intpot to cli mcp_server.py
```

Required params become `typer.Argument(...)`, optional ones become `typer.Option(default)`. Return values get wrapped in `typer.echo()`.

### MCP to API

```bash
intpot to api mcp_server.py
```

MCP tools map to POST endpoints. Parameters become `Body(...)` fields. Pretty straightforward since both MCP and API are request/response style.

### API to CLI

```bash
intpot to cli api_app.py
```

Path parameters (like `/users/{user_id}`) become `typer.Argument()` with an auto-generated help string. Body parameters become arguments or options depending on whether they have defaults.

### API to MCP

```bash
intpot to mcp api_app.py
```

Endpoints become MCP tools. Path params and body params all flatten into regular function parameters.

## What happens to async functions

Async functions are preserved through conversion. If your MCP tool is `async def`, the generated FastAPI endpoint will also be `async def`, and vice versa.

```python
# MCP source
@mcp.tool()
async def summarize(note_ids: str) -> str:
    ids = [nid.strip() for nid in note_ids.split(",")]
    return json.dumps({"summarized": len(ids), "ids": ids})

# Generated FastAPI output
@app.post("/summarize")
async def summarize(
    note_ids: str = Body(...),
) -> dict:
    ids = [nid.strip() for nid in note_ids.split(',')]
    return json.dumps({'summarized': len(ids), 'ids': ids})
```

## What happens to `Depends()`

FastAPI's dependency injection (`Depends()`) doesn't have a direct equivalent in Typer or MCP. intpot handles this by:

1. **Stripping** the `Depends()` parameter from the converted function signature
2. **Adding a comment** noting which dependencies were used

```python
# FastAPI source
@app.post("/users")
def create_user(
    username: str = Body(...),
    db=Depends(get_db),
) -> dict:
    return {"username": username}

# Generated CLI output
# NOTE: Original used dependency injection: get_db
@app.command()
def create_user(
    username: str = typer.Argument(..., help="Unique username"),
) -> None:
    typer.echo({'username': username})
```

You'll need to manually wire up your database/service layer after conversion. This is a known limitation (see the [roadmap](https://github.com/tugrulguner/intpot/blob/main/ROADMAP.md) for v2 plans around dependency injection mapping).

## Body transforms: `typer.echo()` vs `return`

This is the main I/O boundary that intpot handles automatically:

| Direction | What happens |
|-----------|-------------|
| CLI -> API/MCP | `typer.echo(X)` becomes `return X` |
| API/MCP -> CLI | `return X` becomes `typer.echo(X)` |
| MCP <-> API | Body stays the same (both use `return`) |

`raise typer.Exit(code)` gets special treatment too:
- Exit code 0 becomes `return None`
- Non-zero exit codes become `raise RuntimeError("Exit code N")`

## Return types

intpot adjusts return types based on the target framework:

| Target | Return type |
|--------|------------|
| CLI (Typer) | Always `None` (output goes through `typer.echo`) |
| API (FastAPI) | Always `dict` |
| MCP (FastMCP) | `str` if coming from CLI, otherwise preserves original |

## Parameter descriptions

Descriptions carry over between frameworks where possible:

- `typer.Argument(..., help="...")` -> `Body(..., description="...")`
- `Body(..., description="...")` -> `typer.Option(..., help="...")`
- MCP tools don't have per-parameter descriptions in the decorator, so descriptions are empty when converting *from* MCP

## HTTP method preservation

When converting from FastAPI, intpot preserves the HTTP method. Converting back from CLI/MCP always defaults to POST since those frameworks don't have a concept of HTTP methods.

```python
# FastAPI source with GET
@app.get("/users")
def list_users(limit: int = 20) -> dict: ...

# Convert to CLI and back to API
# The roundtrip loses the GET method — it becomes POST
@app.post("/list_users")
def list_users(limit: int = Body(default=20)) -> dict: ...
```

## Directory-wide conversion

You can point intpot at a directory and it'll find and convert all framework apps:

```bash
intpot to cli ./myproject/
intpot to mcp ./myproject/ --output ./converted/
```

intpot scans for Python files, tries to detect a framework in each one, and converts everything it finds. Files that don't contain a recognized app are silently skipped.

Tip: use `intpot inspect ./myproject/` first to see what intpot detects before doing the actual conversion.

## Imports are carried over

If your source function uses `json`, `hashlib`, `datetime`, etc., those imports show up in the generated output. intpot inspects the source module to figure out which imports the function body needs.

```python
# MCP source uses hashlib and json
@mcp.tool()
def create_note(title: str, body: str) -> str:
    note_id = hashlib.md5(title.encode()).hexdigest()[:8]
    return json.dumps({"id": note_id, "title": title})

# Generated API output includes those imports
import hashlib
import json
# ... rest of the generated code
```

## Round-trip conversion: A -> B -> A

Converting from A to B and back to A won't give you identical code. Things that get lost or changed:

- **HTTP methods** default to POST after a round trip through CLI/MCP
- **Route paths** may change (e.g. `/users/{user_id}` becomes `/users_user_id` or similar)
- **`Depends()` calls** are stripped and replaced with comments
- **Formatting** will differ (intpot generates from templates, not from your original formatting)
- **Parameter descriptions** from MCP are empty, so a round trip MCP -> API -> MCP loses descriptions that existed in the API version

The function bodies are generally preserved well though, especially for simple functions.

## Tips

- **Preview before writing:** Skip `--output` to print to stdout first. Check the result before committing to a file.
- **Use inspect:** `intpot inspect source.py` shows what intpot extracted (functions, params, types) without generating anything. Useful for debugging unexpected output.
- **Start simple:** Convert one file at a time before doing directory-wide conversions.
- **Check TODOs:** If intpot can't carry over the function body (usually due to unparseable code), it generates a `# TODO: implement` placeholder. Grep for these after conversion.
- **Python API for scripting:** If you need to convert programmatically or in bulk:

```python
import intpot

app = intpot.load("server.py")
print(app.tools)          # see what was detected
print(app.to_cli())       # preview the output
app.write("out.py", "cli") # write to file
```

## Known limitations

- `Annotated[str, Body(...)]` style FastAPI parameters aren't fully supported yet
- Nested Typer sub-apps and Click groups are not handled
- `Depends()` is stripped, not converted to an equivalent pattern
- Generated code has `# TODO: implement` when the function body can't be carried over
- `format` as a parameter name gets sanitized (it's a Python builtin) — watch for `format_` in output
