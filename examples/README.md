# Examples

## Existing third-party application

[The csv2vcard case study](external-applications/csv2vcard.md) runs an unmodified,
pinned contact-conversion CLI, retains real vCard artifacts, and records current
Intpot discovery/conversion boundaries. Run it with `external_csv2vcard.py`; it
does not claim that the full third-party application converts successfully.

## Runnable application conversions

These are standalone Python applications generated from the three source examples,
not test fixtures. They include the supported business helpers and numeric validation,
and do not import intpot. Use this unreleased source checkout to generate them; public
v0.16.0 does not include the newer conversion guarantees.

```bash
uv sync --all-extras --locked --python 3.11
```

### Storage-cost and inventory CLIs

```bash
uv run --no-sync python examples/conversions/storage_quote_to_cli.py 100 --days 30
# {'cost': 120.0, 'size_gb': 100, 'days': 30, 'replicas': 2}

uv run --no-sync python examples/conversions/inventory_reservation_to_cli.py 25 --packs 3
# {'quantity': 25, 'packs': 3, 'cost': 900}
```

Optional `--receipt ./receipt.txt` writes a result after successful validation and
business-policy checks. Size `0` and quantity `0` are rejected. A reservation of
`100 --packs 2` exceeds available stock and fails without writing a receipt.

### Batch-order and inventory HTTP APIs

Start the batch-order API in one terminal:

```bash
uv run --no-sync python examples/conversions/batch_quote_to_api.py
```

Call it from another terminal:

```bash
curl --fail-with-body http://127.0.0.1:8000/quote \
  -H 'Content-Type: application/json' -d '{"quantity":3}'
# {"result":75}
```

Stop that server with Ctrl-C before starting the inventory API, which also uses port 8000:

```bash
uv run --no-sync python examples/conversions/inventory_reservation_to_api.py
```

```bash
curl --fail-with-body http://127.0.0.1:8000/reserve_inventory \
  -H 'Content-Type: application/json' -d '{"quantity":25,"packs":3}'
# {"quantity":25,"packs":3,"cost":900}
```

Both servers bind only to loopback. These examples use in-process policy calculations,
not persistent stock transactions or authenticated production services.

### Batch-order and storage MCP servers

`call_converted_mcp.py` starts each standalone server as a subprocess, calls its tool
through MCP stdio, prints the returned content and closes the connection:

```bash
uv run --no-sync python examples/call_converted_mcp.py batch '{"quantity":3}'
# 75

uv run --no-sync python examples/call_converted_mcp.py storage '{"size_gb":100,"days":30}'
# {"cost":120.0,"size_gb":100,"days":30,"replicas":2}
```

To connect another MCP client directly, configure its command as the environment's Python
and its argument as `examples/conversions/batch_quote_to_mcp.py` or
`examples/conversions/storage_quote_to_mcp.py` (use absolute paths outside this checkout).
The server runs on stdio; it is not an HTTP endpoint.

## Run the current source examples

The application-led conversion examples below require this source checkout. Public
v0.16.0 does not include the newer numeric-validation conversion guarantees.

```bash
uv sync --all-extras --locked --python 3.11
uv run --no-sync python scripts/verify_generated_examples.py
```

The verifier runs existing framework/diagnostic smoke tests **and all three application
conformance drivers**. They compare results, omitted defaults, invalid/missing inputs,
business errors and receipt effects through actual framework consumers. No network
server is left running. Native error/response formats can differ; explicit-null coercion
is not covered by the shared finite numeric input domain.

Run an individual application comparison with:

```bash
uv run --no-sync python examples/application_conformance.py
uv run --no-sync python examples/api_application_conformance.py
uv run --no-sync python examples/mcp_application_conformance.py
```

Each command prints a JSON report after its assertions pass. Valid calls write temporary
receipts; invalid inputs and business errors must not write them. Temporary files are
removed on exit. The batch-order comparison includes a low-level generated CLI check;
public same-source conversion remains refused.

`inventory_reservation.py` starts from MCP: numeric validation, defaults, stock-limit
policy and receipt effects. Run `mcp_application_conformance.py` for original native MCP
and generated CLI/HTTP comparison (unreleased; not public v0.16.0).

`storage_quote.py` is an HTTP storage-cost service with typed inclusive bounds, defaults,
ordinary helpers and receipt side effects. Run `api_application_conformance.py` to compare
its original HTTP and generated CLI/MCP consumers. This API-source numeric-validation
capability is unreleased; it is not part of public v0.16.0.

`batch_quote.py` is a real bounded-order Typer CLI with same-module helpers, defaults
and receipt side effects. `application_conformance.py` executes the original and
generated CLI/API/MCP consumers and verifies valid totals, rejected inputs and failures
before receipt writes. Numeric-range conversion requires the unreleased source slice;
public v0.16.0 does not provide this guarantee.

`reference_locations.py` requires v0.16.0 or newer. It runs an original
HTTP API with a dynamic binding, checks exact original identifier ranges and Python/CLI
JSON parity, then proves unchanged refusal before writes and unavailable ranges after
a source change.

`binding_chains.py` requires v0.15.0 or newer. It runs a helper-backed
original HTTP API and generated CLI, then explains an explicitly caller-authored
incomplete schema. A separate real-source refusal verifies CLI/Python report parity
and no output writes; the synthetic fixture does not expand source recovery.

`source_provenance.py` (requires v0.14.0 or newer) executes an original HTTP API
with TestClient, verifies tool/helper definition coordinates, compares Python and
CLI JSON assessments, and preserves refusal before writes. Dynamic/synthetic
metadata stays unavailable; definition bounds are not exact missing-name positions.

This directory contains example source files and their generated conversions.

## Source Files

### Basic

| File | Framework | Description |
|------|-----------|-------------|
| `cli_app.py` | Typer CLI | Two commands: `add` and `greet` |
| `mcp_server.py` | FastMCP | Two tools: `add` and `greet` |
| `api_app.py` | FastAPI | Two endpoints: `/add` and `/greet` |

### Advanced

| File | Framework | Description |
|------|-----------|-------------|
| `advanced_cli.py` | Typer CLI | Task manager with `json`, multiple commands, booleans |
| `advanced_mcp.py` | FastMCP | Notes server with `hashlib`, `datetime`, `json`, async tools |
| `advanced_api.py` | FastAPI | User CRUD with `Body(...)`, `Optional`, path params, multiple HTTP methods |
| `dependency_api.py` | FastAPI | Authenticated profile route with `Depends()`; intentionally rejected by CLI/MCP conversion |

## Definition-binding diagnostics

`definition_bindings.py` exercises the eager diagnostics published in v0.11.1 and the
v0.12.0 string/postponed-annotation name check. It creates a
temporary FastAPI source with a Pydantic `Model` annotation and requests the original endpoint.
It then reports `missing_definition_binding` for MCP and `missing_annotation_binding` for CLI.
Both conversions raise `MissingBindingError` before any output directory, even with scaffold opt-in.

```bash
uv run --all-extras --with httpx python examples/definition_bindings.py
```

This checks missing global roots; it does not recover classes or certify complete annotation resolution.
The example starts no network server and removes its temporary source on exit.

## Generated Conversions

The `conversions/` directory contains 18 standalone conversion outputs: 6 basic,
6 advanced and 6 application conversions listed above. `bash scripts/demo.sh`
regenerates all of them from their source applications.

### Basic

| Output File | Command |
|-------------|---------|
| `conversions/cli_to_mcp.py` | `intpot to mcp examples/cli_app.py` |
| `conversions/cli_to_api.py` | `intpot to api examples/cli_app.py` |
| `conversions/mcp_to_cli.py` | `intpot to cli examples/mcp_server.py` |
| `conversions/mcp_to_api.py` | `intpot to api examples/mcp_server.py` |
| `conversions/api_to_cli.py` | `intpot to cli examples/api_app.py` |
| `conversions/api_to_mcp.py` | `intpot to mcp examples/api_app.py` |

### Advanced

| Output File | Command |
|-------------|---------|
| `conversions/advanced_cli_to_mcp.py` | `intpot to mcp examples/advanced_cli.py` |
| `conversions/advanced_cli_to_api.py` | `intpot to api examples/advanced_cli.py` |
| `conversions/advanced_mcp_to_cli.py` | `intpot to cli examples/advanced_mcp.py` |
| `conversions/advanced_mcp_to_api.py` | `intpot to api examples/advanced_mcp.py` |
| `conversions/advanced_api_to_cli.py` | `intpot to cli examples/advanced_api.py` |
| `conversions/advanced_api_to_mcp.py` | `intpot to mcp examples/advanced_api.py` |

`dependency_api.py` deliberately exercises FastAPI `Depends()`. It remains runnable and
inspectable, but conversion to CLI or MCP is expected to fail before writing output until
[dependency mapping](https://github.com/tugrulguner/intpot/issues/20) is implemented. The
demo verifies both rejection paths while retaining the complete supported conversion set.

## Regenerating

To regenerate all conversions, verify the expected dependency rejections, and execute the
selected checked-in generated CLI/API/MCP artifacts, the dependency FastAPI route,
and all three application conformance suites:

```bash
bash scripts/demo.sh
```
