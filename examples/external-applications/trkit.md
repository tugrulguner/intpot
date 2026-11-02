# trkit: a packaged Turkish text workflow (unreleased)

This second independently maintained application exercises real string inputs,
a default/custom separator, Turkish Unicode normalization, package helper calls
and text output. It does not read contact data or require network credentials.

- Upstream: https://github.com/ardazeybek-dev/trkit
- Pinned revision: `b86ef6464f514782b6643771cc73119174c7d4e1` (trkit 0.2.0)
- License: MIT; see the unchanged upstream `LICENSE`.
- Selected command: `slug`, from `src/trkit/cli.py`.

## Reproduce

From an Intpot source checkout with the unreleased changes:

```bash
uv sync --all-extras --python 3.11
git clone https://github.com/ardazeybek-dev/trkit /path/to/trkit
git -C /path/to/trkit checkout b86ef6464f514782b6643771cc73119174c7d4e1
uv pip install --python .venv/bin/python /path/to/trkit
.venv/bin/python examples/external_trkit.py \
  --source-checkout /path/to/trkit \
  --output-dir /path/to/new-results
```

Choose a fresh output directory. The driver verifies the pinned clean checkout,
MIT license and installed Python source bytes. It invokes the original CLI in
subprocesses, emits two standalone server files, starts a temporary loopback HTTP
server and a real MCP stdio subprocess, compares outputs and closes both servers.
It saves original stdout/stderr, generated Python, server logs and `report.json`.
Only synthetic text is supplied. Project synchronization can remove the extra
upstream package; install it again after syncing and use `.venv/bin/python`.

## Run the applications directly

```bash
.venv/bin/python -m trkit.cli slug 'İstanbul IĞDIR çay'
# istanbul-igdir-cay
.venv/bin/python -m trkit.cli slug 'İstanbul IĞDIR çay' --separator _
# istanbul_igdir_cay
```

Generate without editing upstream source:

```python
import intpot
from trkit.cli import app

selected = intpot.load(app).select("slug")
selected.write("slug_api.py", "api")
selected.write("slug_mcp.py", "mcp")
```

Keep trkit installed: normalization retains its real package dependency, not a
vendored copy or replacement helper. Start the generated HTTP server and call it:

```bash
.venv/bin/python slug_api.py
# In another terminal:
curl http://127.0.0.1:8000/slug \
  -H 'Content-Type: application/json' \
  -d '{"text_":"İstanbul IĞDIR çay","separator":"_"}'
# {"result":"istanbul_igdir_cay"}
```

The generated MCP server exposes only `slug`, with required string `text_` and
optional string `separator` defaulting to `-`. The driver calls the actual stdio
server for default/custom separators, punctuation and empty text. It retains MCP
client output validation; no schema checking is disabled.

## Demonstrated blocker and bounded change

Before the fix, loading the imported Typer instance and selecting `slug` emitted
`from . import text`. Both generated servers then failed to import outside the
original package: `attempted relative import with no known parent package`.

The inspector resolves relative imports from the original callable's package
context, verifies the binding by identity against an already-loaded module/export,
and emits an absolute import. It does not import candidate modules, evaluate
conditions, invoke dynamic module attribute hooks, or copy package startup code.
Missing or inconsistent package/binding evidence does not certify an import.
This is source-import recovery, not a new intermediate representation.

## Errors and limits

- Missing text is rejected by the original CLI (exit 2), HTTP (422) and MCP.
- HTTP/MCP additionally reject non-string JSON input; CLI shell arguments are text,
  so that JSON-type rejection is not claimed as an identical CLI input case.
- An invalid regex replacement separator is a business/helper error: original CLI
  exits 1, HTTP returns 500 and MCP reports a tool error. Their error envelopes differ.
- Valid empty text returns an empty slug, not a missing-input error.
- No persistent file effects belong to this text-only workflow.
- Only ordinary `slug` invocations are qualified. Global `--version` and root CLI
  lifecycle behavior, validators, plate lookup and other commands are not converted
  by this case study. The root version callback does nothing for these default
  invocations; selection does not promise arbitrary root callback equivalence.
- Use `intpot.load(app)` with the normally imported instance. Direct loading of
  `src/trkit/cli.py` by filesystem path still lacks package import context and is
  not fixed here. No upstream source edits or callback-parameter stripping are used.
- This behavior is unreleased; public v0.16.0 does not include this capability.
