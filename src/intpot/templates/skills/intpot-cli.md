# intpot CLI

**intpot** does two things: it lets you define tools once and serve them as a Typer CLI,
FastAPI app, or FastMCP server, and it converts existing apps between those three
frameworks.

## When to Use

- The user wants one set of functions available as a CLI, an HTTP API, **and** an MCP
  server without maintaining three codebases — use `intpot.App`
- The user has an existing Typer / FastMCP / FastAPI app and wants it in another
  framework — use `intpot to ...`
- The user wants to see what intpot extracts from a file before converting — use
  `intpot inspect`
- The user wants a new project skeleton — use `intpot init`

Scaffold commands require a project name followed by `--type`:

```bash
intpot init my-project --type cli
intpot init my-project --type mcp
intpot init my-project --type api
```

## Write once, serve everywhere

Define tools with `@app.tool()` in a plain Python file:

```python
from intpot import App

app = App("my-app")

@app.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
```

Serve the same file in any mode:

```bash
intpot serve app.py --cli          # Typer CLI
intpot serve app.py --api          # FastAPI on 127.0.0.1:8000
intpot serve app.py --mcp          # FastMCP server
```

In `--cli` mode, arguments after the flags go to the app:

```bash
$ intpot serve app.py --cli add 2 3
5
```

Use `--` when the app defines a flag intpot also defines (`--host`, `--port`):

```bash
intpot serve app.py --cli -- mytool --port 5
```

Export the same app as standalone framework code, with no intpot dependency:

```bash
intpot eject app.py --to api       # or cli, mcp
intpot eject app.py --to cli --output cli_app.py
```

## Convert an existing app

```bash
intpot to cli server.py            # MCP or API source -> Typer CLI
intpot to mcp app.py               # CLI or API source -> FastMCP server
intpot to api app.py               # CLI or MCP source -> FastAPI app

intpot to cli server.py --output cli_app.py
intpot to cli ./myproject/         # every app in a directory
intpot to cli server.py --dry-run  # print output; do not write generated files
intpot to mcp app.py --verbose     # detection details on stderr
```

## Inspect without generating

```bash
intpot inspect server.py           # table of extracted tools
intpot inspect server.py --json    # normalized ToolInfo as JSON
```

Prefer `--json` when you need to reason about the result programmatically.

## Options

| Option | Applies to | Description |
|--------|-----------|-------------|
| `--output`, `-o` | `to *`, `eject` | Output path (prints to stdout if omitted) |
| `--dry-run` | `to *` | Preview generated code without writing files |
| `--verbose`, `-v` | `to *`, `inspect` | Show detection details on stderr |
| `--json` | `inspect` | Emit JSON instead of a table |
| `--host` / `--port` | `serve --api` | Defaults `127.0.0.1` / `8000` |
| `--version`, `-V` | top level | Print the installed version |

## Things to know

- **Detection imports the source file.** `intpot to ...` and `intpot inspect` execute the
  module to find the app instance, so arbitrary module-level code still runs. `--dry-run`
  only prevents generated output files from being written; it is not a sandbox. Only
  convert source code you trust.
- **`serve --api` binds `127.0.0.1`.** Pass `--host 0.0.0.0` to expose it on the network.
  Code from `eject --to api` and `init --type api` binds loopback too; change the `host=`
  argument in the generated file to opt in.
- **`serve --api` reads arguments from a JSON body**, not the query string — the same
  shape `eject --to api` generates.
- **Converted code carries the original body over** where the frameworks agree, and
  rewrites it where they don't. A tool whose body can't be recovered gets a
  `# TODO: implement` stub.

## Verify generated code

Successful generation does not prove that the generated program works. After every
conversion or eject:

1. **Compile** it with `python -m py_compile generated.py`.
2. **Import** the generated module in the environment where it will run.
3. **Invoke** real behavior: run a generated CLI command, issue a request with FastAPI's
   `TestClient`, or call a generated MCP tool. Checking text or `--help` alone is not a
   behavioral test.

Current unsupported or lossy cases include nested Typer sub-apps, repeatable CLI options,
some FastAPI `Annotated[..., Body(...)]` parameters, `Depends()` (recorded in a comment
but stripped from non-API targets), factory-created apps, and routes with multiple HTTP
methods. A missing recoverable body becomes a `# TODO: implement` stub.

intpot carries direct import statements referenced by a tool body. It does not yet copy
same-module helpers, constants, classes, models, or closure values. It does not discover
or install transitive dependencies across imported modules. Direct file loading does not
add the source directory to `sys.path`, so sibling imports may require installing the
package or setting `PYTHONPATH`. intpot does not reproduce configuration or provision
external services; verify those explicitly rather than assuming generated code is
standalone.

## Installation

```bash
pip install intpot            # core: init, inspect, add skills, Typer CLI output
pip install intpot[mcp]       # + FastMCP support
pip install intpot[api]       # + FastAPI support
pip install intpot[all]       # everything
```

Install `[mcp]` or `[api]` when intpot must inspect or load a source using that framework,
or when you serve, import, or invoke that target. Emitting source text alone does not
require the target extra, but verifying or running the emitted program does.
