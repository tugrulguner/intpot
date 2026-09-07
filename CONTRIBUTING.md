# Contributing to intpot

Thanks for helping improve Intpot. Intpot is a framework with two public halves—runtime and
conversion—that meet at the normalized `ToolInfo` schema. Contributions must preserve that
boundary and prove behavior at the framework surface users actually run.

## Choose the contribution path first

### Substantial contract work: open an issue first

Open a structured [feature request](https://github.com/tugrulguner/intpot/issues/new?template=feature.yml)
before changing public APIs, normalized models, inspector/generator contracts, runtime
behavior, framework compatibility floors, conversion guarantees, or cross-target semantics.
Start with the user problem and wait for contract alignment before implementation.

### Small direct changes

A focused bug fix, regression test, documentation correction, example repair, or maintenance
change may be opened directly when its scope is obvious and it does not introduce a new
public contract. Explain why a direct PR is appropriate in the pull-request template.

### Questions and early ideas

Use [Q&A](https://github.com/tugrulguner/intpot/discussions/categories/q-a) for usage help and
[Ideas / Roadmap](https://github.com/tugrulguner/intpot/discussions/categories/ideas-roadmap)
for an idea that is not yet a scoped proposal. Do not turn exploratory discussion into an
implementation before the contract is clear.

### Claimed community work

For a `good first issue` or `help wanted` issue, comment and wait for confirmation before
starting. Check the issue body, every comment, and open pull requests first so two
contributors do not solve the same problem.

## Development setup

After forking and cloning:

```bash
git clone https://github.com/YOUR_USERNAME/intpot.git
cd intpot
uv sync --all-extras
uv run pre-commit install
```

Create a focused branch from current `main`:

```bash
git checkout -b <type>/<short-description>
```

Run Python through `.venv/bin/python` or `uv run`; never install project dependencies
globally.

## Project structure

```text
src/intpot/
├── __init__.py          # Package exports (App, IntpotApp, load)
├── cli.py               # Main CLI entry point
├── runtime.py           # @app.tool(), serve, and eject
├── runtime_builders.py  # Live Typer/FastAPI/FastMCP builders
├── converter.py         # IntpotApp and load()
├── commands/            # CLI command handlers
├── core/
│   ├── models.py        # ToolInfo, ParameterInfo, SourceType
│   ├── detector.py      # Source detection; imports source files
│   ├── discovery.py     # Directory scanning
│   ├── transforms.py    # Cross-framework body/type transforms
│   ├── inspectors/      # Framework objects → ToolInfo
│   └── generators/      # ToolInfo → generated source
└── templates/           # Jinja2 source templates
```

The core flow is:

```text
source app → detect → inspect → ApplicationSchema → project/generate → target app
                                      ↘ runtime builders → live target
```

Read [`src/intpot/AGENTS.md`](src/intpot/AGENTS.md) before changing source. Its rules come
from real bugs, including generated code that compiled but failed when invoked and framework
checks that silently stopped discovering tools.

## Implementation expectations

- Preserve Intpot as a full framework, not a thin wrapper around one target.
- Keep runtime and conversion behavior aligned where they advertise the same contract.
- Treat immutable `ApplicationSchema`, `ToolSchema`, and `ParameterSchema` as the seam.
  `ToolInfo` and `ParameterInfo` are detached compatibility models at framework edges.
- Check all source and target frameworks affected by a normalized-schema or template change.
- Keep the minimum supported versions in `pyproject.toml` honest and exercise structural
  compatibility generations, not only the lockfile.
- Add type annotations to new functions and use `from __future__ import annotations`.
- Let Ruff own formatting; use `make format` rather than hand-formatting around failures.

## Tests and behavioral evidence

Run the complete quality gate:

```bash
make check
make build
```

`make check` runs Ruff, formatting, Pyright, and the complete test suite from `uv.lock`.
When a change touches framework internals, also run the relevant oldest and newest dependency
lanes documented in [`docs/reviewing.md`](docs/reviewing.md).

Generated code is only verified when its real consumer executes it:

- invoke generated Typer commands;
- send requests to generated FastAPI operations;
- call generated FastMCP tools;
- exercise checked-in generated examples when their source or contract changes.

A string assertion or successful `compile()` may supplement this evidence, but cannot replace
it. Record exact commands and results so a reviewer can reproduce them. Include negative
paths when the change affects detection, validation, rejection, or error reporting.

## Changelog fragments

Every user-facing change needs one Towncrier fragment:

- tracked work: `changelog.d/<issue-number>.<type>.md`;
- a small direct change without an issue: generate a unique orphan with
  `uv run towncrier create +.changed.md` and replace `changed` with the appropriate type.

Allowed types are `added`, `changed`, `deprecated`, `removed`, and `fixed`. Numeric fragments
must refer to the underlying issue, not the pull request. Describe the user-visible result in
one sentence. See [`changelog.d/README.md`](changelog.d/README.md).

For genuinely internal-only work, ask a maintainer to apply `skip-changelog`. Never remove a
fragment merely to satisfy CI, and never edit `CHANGELOG.md` directly.

## Pull request process

1. Confirm the contribution path and scope before implementation.
2. Rebase or merge current `main` before final verification.
3. Keep the PR focused; list explicit non-goals.
4. Add tests and behavioral evidence for the changed boundary.
5. Add the issue-backed or generated orphan changelog fragment.
6. Run `make check`, `make build`, and applicable compatibility/artifact checks.
7. Push the branch and open a PR against `tugrulguner/intpot:main`.
8. Use `Closes #<issue-number>` for tracked work, or explain why a direct PR is appropriate.
9. Point reviewers to the riskiest files and evidence in the PR template.
10. Respond to every review finding and wait for the new exact-head checks.

Reviewers follow [`docs/reviewing.md`](docs/reviewing.md). A green old head does not verify a
new push, and a review of one target does not establish parity across all generated targets.

## Reporting bugs

Use the structured [bug report](https://github.com/tugrulguner/intpot/issues/new?template=bug.yml).
Include a minimal source application, exact command or public API call, framework versions,
and generated output. Remove credentials, private source, and sensitive data before posting.

## Releasing

Releases are maintainer work described in [`docs/releasing.md`](docs/releasing.md). Do not
bump versions, edit lockfile version metadata manually, create tags, or assemble
`CHANGELOG.md` in a feature PR. Land a fragment and it will be included in release
preparation.
