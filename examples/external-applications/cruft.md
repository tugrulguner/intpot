# Cruft: selected create workflow through real consumers

This case study converts only Cruft's `create` command and exercises its generated HTTP and stdio MCP consumers against a synthetic local Cookiecutter template. It does **not** convert the full Cruft application. The selected run is intentionally bounded to `--no-input`, `--default-config`, a trusted local template and absolute existing output-parent directories; it is not evidence for interactive prompting, remote templates, path-policy equivalence, or other Cruft commands.

## Reproduce

Use the exact clean MIT-licensed Cruft source revision `33f6b722fc6fe4b5d26a351e487372e5e4375ab2`. The driver refuses a different commit or a dirty source checkout, compares every installed Cruft package `.py` file byte-for-byte to the checkout, and records the resolved versions and executable. Its fixtures are generated under the new output directory and committed locally using only the explicit identity `Synthetic Fixture <fixture@example.invalid>`; no upstream commit or file is changed.

From the Intpot checkout, create a disposable environment using Python 3.11 and uv. The candidate proof environment used for the observed run had Python 3.11, Intpot 0.16.0 editable from this checkout, Cruft 0.0.0 editable from the pinned source, Typer 0.29.0, Click 8.5.1, Cookiecutter 2.7.1, FastAPI 0.162.4 and FastMCP 4.1.8. Recreate it with the pinned source and the documented Intpot project setup, then add the case-study dependencies to that interpreter:

```sh
git clone https://github.com/cruft/cruft.git cruft-source
git -C cruft-source checkout --detach 33f6b722fc6fe4b5d26a351e487372e5e4375ab2
uv venv --python 3.11 .case-study-venv
uv pip install --python .case-study-venv/bin/python -e ./cruft-source -e '.[all]' 'typer==0.29.0' 'click==8.5.1' 'cookiecutter==2.7.1' 'fastapi==0.162.4' 'fastmcp==4.1.8'
```

Run in the checkout directory so the editable Intpot install points at this source tree; if the project's extras or its uv environment differ, install Intpot's declared CLI/API/MCP dependencies into the disposable interpreter explicitly. Do not use the canonical project venv for Cruft-only dependencies. Confirm the interpreter, installed package versions and source commit before interpreting results.

```sh
.case-study-venv/bin/python examples/external_cruft.py \
  --source-checkout /absolute/path/to/cruft-source \
  --output-dir /absolute/path/to/new-case-study-output
```

The output path must not already exist. It contains the synthetic fixture, its local Git history, generated standalone API/MCP files, exact command stdout/stderr, HTTP/MCP server logs, output trees and SHA-256 maps, plus `report.json`. Existing destination refusal is expected behavior; explicit overwrite is separately exercised. Failures retain a report with `completed: false` and the actual error; in particular, an MCP client-side output-schema rejection of `None` is recorded as an error, never counted as success. The driver owns and reaps its HTTP server and uses an isolated HOME/Git configuration.

## Observed result

The driver writes the executed result to `<output-dir>/report.json`. The exact observed environment was Python 3.11, Intpot 0.16.0, Cruft distribution metadata `0.0.0`, Typer 0.29.0, Click 8.5.1, Cookiecutter 2.7.1, FastAPI 0.162.4 and FastMCP 4.1.8. `0.0.0` is the version metadata exposed by this editable pinned-source build; it is not a claim that this is a published Cruft release. Cruft's public latest release 2.16.0 is distinct. Attribution here rests on the clean exact source commit and byte identity across all 18 installed Cruft Python files, not the distribution version string. Native Cruft, generated HTTP and a real stdio MCP client each created the same two files (`consumer_result/README.md` and `.cruft.json`) with identical SHA-256 hashes. Each consumer refused a repeat creation without changing any file bytes; explicitly enabling overwrite restored the original byte hashes. HTTP returned JSON `null` on successful void calls. The fixed MCP output normalized Cruft's ordinary silent fallthrough to empty text, which satisfies the generated string contract; nested function/class returns, API result behavior and broader output equivalence are not claimed.

In the retained pre-fix baseline, native and HTTP behavior passed, but MCP created the project and then the actual client rejected structured `None` against its declared string result. That was a real validation failure after filesystem effects, not a passing case. The observed project revision was checked against a clean pinned checkout, and the installed Cruft Python source was byte-verified. The repository's last push was 2024-12-25, so this study does not characterize Cruft as currently maintained or active in 2026.

**Boundary:** `full_application_conversion_verified` remains `false`. This is one successful, effectful selected command with constrained inputs, not a full Cruft application conversion or a general claim about other applications.
