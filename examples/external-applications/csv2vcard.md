# External application case study: csv2vcard

This exercises an independently maintained, MIT-licensed application, not a source
application written for Intpot. The upstream source is used unchanged:

- Repository: https://github.com/tech4242/csv2vcard
- Revision: `04a99668550779603774d6d86635314421eccb56` (v0.6.0 source)
- CLI: `csv2vcard/cli.py`
- License: upstream `LICENSE.txt` (MIT); no upstream source is vendored here.

## Reproduce

From an Intpot source checkout, choose scratch paths outside the checkout:

```bash
uv sync --all-extras --locked --python 3.11

git clone https://github.com/tech4242/csv2vcard.git "$HOME/csv2vcard-case"
git -C "$HOME/csv2vcard-case" checkout --detach 04a99668550779603774d6d86635314421eccb56
uv pip install --python .venv/bin/python "$HOME/csv2vcard-case[cli]"

uv run --no-sync python examples/external_csv2vcard.py \
  --source-checkout "$HOME/csv2vcard-case" \
  --output-dir "$HOME/csv2vcard-case-results"
```

The output directory must not already exist. The driver checks the upstream revision,
requires a clean source checkout, and verifies that the installed Python source files
match that checkout. It uses two **synthetic example.com contacts**, not personal data.
The separate install is deliberate: this third-party package is not an Intpot dependency.
Use `--no-sync` afterward so uv does not remove it from the environment.

## Actual workflows

The driver runs the original `python -m csv2vcard.cli` commands as subprocesses:

1. Convert the sample CSV to two individual vCard 3.0 files.
2. Convert the same contacts to one combined vCard 4.0 file containing both cards.
3. Print the application's column-mapping JSON.
4. Reject an invalid vCard version without creating an output directory.
5. Reject a missing source file without creating an output directory.

The original `.vcf` artifacts, stdout/stderr, file digests, assessment and conversion
outcomes are retained under the chosen output directory, with a `report.json` summary.
No network server is started and no source file is rewritten.

## First reproduced Intpot blocker

Upstream constructs its Typer application under `if HAS_TYPER:` so the library remains
usable without its optional CLI dependency. Intpot's old AST prefilter only inspected
immediate module assignments: it rejected this installed, working CLI as having no
framework application, before attempting the import.

The bounded fix recognizes constructor assignments under module-level `if` and `try`
branches. It does not evaluate their conditions or enter function/class bodies. Actual
module import and framework-instance inspection still determine whether an app exists;
finding a constructor in an inactive branch is not enough. This is not an app-factory
or general dynamic-startup support claim.

## Remaining conversion boundary

**This is not a successful full csv2vcard-to-HTTP/MCP conversion.** Its `convert`
command exposes a `--version` parameter callback, which Intpot explicitly refuses to
translate. The driver records that refusal instead of removing the parameter,
rewriting upstream source, bypassing assessment or emitting a supposedly working server.

Path validation, multi-line CLI output and command/group callback behavior also need
qualification before any full-application equivalence claim. Fixing discovery alone
does not establish those guarantees. The next capability decision should be driven by
these actual workflows, not by counting this case study as completed conversion coverage.
