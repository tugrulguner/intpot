# Exclusive informational requests: a runnable file converter

This is a purpose-built example, not qualification of an independently maintained
application. The original [Typer application](app.py) does not import Intpot.
It reads a UTF-8 text file and writes either escaped HTML or unchanged text.

This unreleased source-checkout example is qualified on Python 3.11 and needs all extras.
Deferred annotation providers are refused without evaluation; ordinary callbacks
on the tested Python 3.14.9 expose such providers, so use Python 3.11 here:

```sh
uv sync --all-extras --python 3.11
PYTHONPATH=examples uv run --no-sync python -m informational_text.app --version --format invalid
PYTHONPATH=examples uv run --no-sync python -m informational_text.app --formats
```

The version request prints `informational-text 1.0` and exits successfully even
though the format is invalid and neither file path was supplied. An ordinary call
still needs both paths and a valid format:

```sh
PYTHONPATH=examples uv run --no-sync python -m informational_text.app input.txt output.html --format html
```

## Exercise all three interfaces

```sh
uv run --no-sync python examples/informational_application_conformance.py
```

The driver performs real native console calls, starts a generated loopback HTTP
server, and calls a generated MCP server through a native stdio client. It verifies
identical HTML bytes, early information requests, and rejection of conflicting
informational flags. It stops its servers and prints the artifact directory.
That directory retains the three HTML files, generated servers, advertised schemas,
HTTP log and `report.json`. Use `--output-dir PATH` to choose a directory.

Generation is explicitly opted in. From the source checkout, the CLI uses the same policy:

```sh
uv run --no-sync intpot inspect examples/informational_text/app.py --json --callback-policy exclusive-informational
uv run --no-sync intpot to api examples/informational_text/app.py --callback-policy exclusive-informational -o generated_api.py
uv run --no-sync intpot to mcp examples/informational_text/app.py --callback-policy exclusive-informational -o generated_mcp.py
```

Or use the Python API:

```python
from pathlib import Path
import intpot

app = intpot.load("examples/informational_text/app.py")
Path("generated_api.py").write_text(
    app.to_api(callback_policy="exclusive-informational")
)
Path("generated_mcp.py").write_text(
    app.to_mcp(callback_policy="exclusive-informational")
)
```

The original source package remains a dependency. For these generated files, keep
`examples` on `PYTHONPATH`, or install the original package normally. The conformance
driver sets this explicitly for its children; a cached parent import is not enough.

## Contract boundaries

- HTTP/MCP inputs remain flat objects. A single active informational flag can bypass
  irrelevant conversion inputs; ordinary requests retain typed validation.
- Multiple active flags reject. Native CLI token order is deliberately not inferred
  from an unordered JSON object.
- Active callbacks run in fresh bounded workers. This isolates Python stdout capture,
  not arbitrary filesystem effects; it does not preserve shared mutable server state.
- Generated HTTP returns a result-text object. MCP returns text content with its
  typed structured result. Error envelopes remain transport-native.
- All paths refer to the server filesystem. This example provides no upload API,
  download API or safe arbitrary-public-filesystem boundary.
- Unqualified callbacks, environment/default-map activation and other conversion
  refusals remain guards. Default conversion still refuses callbacks.
- Programmatic `assess()`, `project()` and `write()` accept the same explicit policy.
  Pass projected schemas directly to generators: legacy tool lists do not carry it.
  The source-checkout CLI accepts `--callback-policy exclusive-informational` on
  `to api`, `to mcp` and `inspect`; broader compatibility checks remain separate work.
  Full Docling conversion is not established.
- Public v0.16.0 does not contain this feature. No release is implied.
