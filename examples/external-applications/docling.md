# Docling: native file-producing workflow, conversion currently blocked

This experiment uses the unchanged [Docling](https://github.com/docling-project/docling)
application at commit `07154cdc82500058ad9377bac92beed3de820458` (MIT;
`docling-slim` 2.145.0). It establishes a real local HTML-to-Markdown baseline and
records Intpot's first conversion blocker. **It does not demonstrate a working
Docling HTTP or MCP conversion.**

## Run the experiment

Use Python 3.11 and Intpot's current source checkout. The public Intpot version is
still 0.16.0; this experiment is maintained against unreleased main.

```bash
git clone https://github.com/docling-project/docling.git /path/to/docling
git -C /path/to/docling checkout --detach 07154cdc82500058ad9377bac92beed3de820458

# From the Intpot checkout, after normal project synchronization:
uv pip install --python .venv/bin/python '/path/to/docling[standard]'
.venv/bin/python examples/external_docling.py \
  --source-checkout /path/to/docling \
  --output-dir /path/to/new-docling-evidence
```

The output directory must not already exist. The driver verifies the clean pinned
checkout and all installed `docling/**/*.py` source bytes, writes explicitly synthetic
HTML containing Unicode text, a list, a table and a local link, and invokes the actual
installed `docling` and `intpot` console executables. It retains literal commands,
stdout/stderr, exit codes, destination snapshots, output files and a JSON report.
The experiment exits successfully only when its native controls and the documented
conversion refusal are reproduced. That exit code is **not** conversion success;
`generated_consumers_verified` and `full_application_conversion_verified` remain false.

The official `standard` extra is intentional. An initial installation using only
`[cli,format-html]` installed successfully but its CLI refused local conversion because
its eager local-stack/plugin initialization required `torch`. The standard bundle
resolved that environment prerequisite without changing Docling. This workflow needs
no model-weight download, but installing the standard dependencies is substantially
larger than installing only the HTML parser.

## Native result observed

The actual native commands were equivalent to:

```bash
docling convert case.html --from html --output native
docling convert case.html --from html --to md --output native
```

The default output and explicit Markdown output matched. The driver seeds `case.md`
with sentinel content before the second call and verifies that the real conversion
replaces it with the original Markdown bytes. Heading/text, Unicode, list and table
content are checked. A missing input returned exit 1; an invalid output format returned
exit 2. Neither rejection produced its destination directory or output files in the
recorded run. The report records effects independently of error messages.

`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set by the driver. Those flags alone
do not prove zero network access. A separate local investigation also reproduced the
native output with Python socket DNS/connect attempts blocked by an audit hook. That
instrumented result covers those Python audit events, not all native-library or
subprocess network paths; it is not a network-sandbox claim.

## Current Intpot boundary

The actual public CLI attempts are:

```bash
intpot to api /path/to/docling/docling/cli/main.py \
  --tool convert --output converted-api.py
intpot to mcp /path/to/docling/docling/cli/main.py \
  --tool convert --output converted-mcp.py
```

Both return exit 1 with:

```text
Collection or compound enum annotations are not supported
```

No requested generated file is created. The current refusal is an explicit inspection
boundary for collections of enum values. It precedes callback assessment and
consumer execution; it is not a failure of Docling's native converter.

At baseline `f167cd4`, the first actual failure was instead Intpot's unconditional
rejection of enum defaults during canonical schema construction. The unreleased string-enum
slice supports ordinary importable scalar choices and defaults. A real intermediate run
then reached the existing refusal for Docling's three parameter callbacks. Additional
negative controls now explicitly reject enum collections, which still lack cardinality
and element-type support, rather than converting them into unchecked scalar strings.
This newly explicit inspection boundary is the current first blocker.

Source inspection found 76 parameters on Docling's selected `convert` command, including
collections, enum choices, and three eager callback parameters (`show_external_plugins`,
`version`, `docling_logo`). Fixing enum defaults alone would not establish conversion of
this command. No parameters were removed, callbacks disabled, helper wrappers substituted,
or upstream files edited to manufacture a successful result.

## Next capability investigation

The first unreleased slice implements ordinary importable scalar string-enum parameters
and defaults with detached immutable schema data, normal source-package type imports,
allowed-value validation and rejected-input checks before file effects. Native CLI,
generated CLI, HTTP and MCP exercise a controlled package fixture, not the Docling command.
Unimportable/custom/non-string enums, member aliases, case-insensitive choices and enum
collections remain refused. Collections and callback/lifecycle semantics are still
separate barriers for Docling. Native CLI, generated HTTP and
stdio MCP file-effect comparisons are acceptance gates for eventual workflow support,
not completed results in this experiment.

The server-side path contract is also distinct from a file-upload/download API and from
safe public filesystem access. This experiment makes neither promise.
