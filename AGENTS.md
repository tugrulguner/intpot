# AGENTS.md

Guidance for coding agents working **on intpot**. If you want intpot's skills for your
*own* project instead, run `intpot add skills`.

## What intpot is

Two halves that meet at one schema:

- **Runtime** — `@app.tool()` registers a function; `App.serve()` builds a live Typer /
  FastAPI / FastMCP instance, `App.eject()` returns standalone source.
- **Converter** — `intpot to cli|mcp|api` reads an existing Typer / FastMCP / FastAPI app
  and generates the equivalent in another framework.

Both compile an immutable `ApplicationSchema` (`src/intpot/core/models.py`) containing
`ToolSchema` and `ParameterSchema` records. Inspectors and registrations still create
mutable `ToolInfo` compatibility models at the edges; projection and generation consume
the canonical schema directly. When you add a capability, ask which side of that boundary
it belongs on.

```
   @app.tool()                    source .py file
        |                    DETECT -> INSPECT
        +-----> ApplicationSchema <----+
                     ToolSchema[]
              |                  |
     live framework          GENERATE
       instance            (Jinja template)
```

## Layout

| Path | What's there |
|------|--------------|
| `core/models.py` | Canonical `ApplicationSchema`/`ToolSchema`/`ParameterSchema` plus compatibility models |
| `core/detector.py` | Identifies the framework; **imports the source file to do it** |
| `core/inspectors/` | Framework → `ToolInfo` |
| `core/generators/` + `templates/*.j2` | `ApplicationSchema` (or legacy `ToolInfo`) → source code |
| `core/transforms.py` | Rewrites bodies and return types between frameworks |
| `runtime.py`, `runtime_builders.py` | The `App` class and live instance builders |
| `commands/` | One module per CLI command; `cli.py` wires them together |
| `templates/skills/` | Shipped to *users* by `intpot add skills` |

## Coding guidelines

Rules for changing intpot source — including the ones that each cost a real bug — and
the architectural contracts a change has to keep live in
[`src/intpot/AGENTS.md`](src/intpot/AGENTS.md). Agents read the nearest file in the
directory tree, so editing source picks them up automatically.

## Workflow

```bash
uv sync --all-extras     # never install globally; never use bare pip
make check               # ruff + pyright + pytest — must pass before a PR
```

Run Python through `.venv/bin/python` or `uv run`.

**Every user-facing change needs a changelog fragment.** Tracked work uses
`changelog.d/<issue-number>.<type>.md`. For a small direct change without an issue, run
`uv run towncrier create +.changed.md` and replace `changed` with `added`, `deprecated`,
`removed`, or `fixed` when appropriate. Numeric fragments refer to issues, never pull
requests. Write one sentence about what changed *for a user*, not what you did to the code.
CI rejects removed-only fragments and PR-number identifiers; a maintainer applies the
`skip-changelog` label for genuinely internal work. Never edit `CHANGELOG.md` by hand—it is
assembled at release time. See `changelog.d/README.md`.

**Never hand-edit the version**, and never bump it as part of a feature PR. It lives only
in `pyproject.toml`; `uv version 0.5.1` updates it and the lockfile together, and
`__version__` reads it back through `importlib.metadata`. Cutting a release is a
maintainer task — see `docs/releasing.md`.

**Do not commit** conflict copies (`file 2.py`), `.venv`, or your agent's own config
directory. Stage explicit paths rather than `git add -A`.

## Keeping the docs honest

Two doc surfaces rot, for different reasons, and both are read by agents rather than by
people who would notice:

| What | Read by | Update it when |
|------|---------|----------------|
| This file, and `docs/reviewing.md` | Anyone working **on** intpot | An internal contract changes: a field on `ToolInfo`/`ParameterInfo`, a base-class signature, a new inspector/generator/command, a new exception, a new Jinja filter, a return-type rule, a test convention |
| `src/intpot/templates/skills/*.md` | **Users'** agents, via `intpot add skills` | The public API changes: `@app.tool()`, `App.serve`, `App.eject`, `intpot.load`, any CLI command or flag — and update the README's CLI reference in the same PR |

The shipped skills went five months describing an API that no longer existed. Update
whichever surface applies in the same PR as the change, not afterwards.

**Verify each claim against the source, not against the previous wording.** Two rules in
this repo's review criteria survived a rewrite while being wrong, because they were edited
as prose: "the API return type is always `dict`" (false since #56) and "`discover_sources`
skips files silently" (false since #59). If a rule came from a real bug, name the bug —
that is what stops the next person deleting it as noise.

`tests/test_skills_content.py` and `tests/test_docs.py` catch the mechanical cases: a
shipped skill naming a field that no longer exists, a CLI flag missing from the README, a
path in this file that git doesn't know about. They can't catch a rule that is merely
wrong.

**Nothing vendor-specific is tracked in this repo.** There is no `.claude/`, `.cursor/`,
or `.windsurf/` directory here, and there was: the review criteria lived in Claude-only
skill files, where no other agent could read them and nobody noticed two of them going
wrong. Guidance goes in this file or `docs/reviewing.md`, both of which every tool and
every human reads. If your agent wants a shortcut wrapping them, keep it untracked.

(`intpot add skills` writing `.claude/skills/` into a *user's* project is the product, and
unrelated — it emits six formats and privileges none of them.)

**Converter missing-body assessment:** source schemas remain inspectable when function source cannot be recovered, but public conversion refuses those tools by default. `allow_scaffold=True` / `--allow-scaffold` emits a labeled `NotImplementedError`; never use successful dummy returns. Keep callback and dependency guards non-bypassable. Direct low-level generators remain backward compatible and do not guarantee converter assessment.

**Missing body bindings:** public converter assessment statically renders target implementations and reuses scope-aware global analysis to diagnose absent bindings. Keep `missing_binding` per-target and do not bypass refusal with scaffold permission. Body-recovery fields remain body-only. Ordered generated function decorator/default/eager-annotation loads use `core/definition_bindings.py` and per-target `missing_definition_binding` diagnostics, including support functions and public wrappers. Use `annotation_missing()` for per-target `missing_annotation_binding` on string/postponed annotation global roots against actual completed-module bindings, excluding annotation-only declarations. Parse type-position strings without evaluating them; preserve imported Literal/Annotated aliases and their value strings. `annotation_missing()` also recognizes nested type-position strings in imported standard `collections.abc.Callable` annotations (including aliases and qualified imports), alongside the existing typing forms; unknown subscriptions and Literal metadata remain value-safe and are not interpreted as types. Keep before-write refusal and scaffold non-bypassability. This does not certify type resolution, alias values, framework registration timing, initializer behavior, imports or runtime initialization. Direct generators and live App remain separate compatibility paths.

**Bounded binding chains (unreleased):** `core/binding_chains.py` adds `references[*].dependency_chain` to missing body/definition/annotation binding diagnostics. Use only scoped global-body references among that tool's emitted wrapper, implementation and retained helpers; choose one shortest lexically deterministic path per owner and leave unreachable, rebound or unanalyzable owners unavailable. Paths are static binding dependencies, not runtime calls or execution traces. Preserve existing diagnostic fields, provenance, guards, code-string APIs and before-write/scaffold behavior. The transitive missing-helper example uses an explicit caller-authored schema, not expanded source recovery.

**Definition provenance (v0.14.0):** `core/provenance.py` captures owning-file definition bounds by matching existing callable code to compiled file source without executing it. `ToolInfo`/`ToolSchema` carry `source_location` and `support_source_locations` through adapters, projections and JSON. Top-level diagnostic locations describe tool definitions; generated references may identify implementation/helper origins, while synthetic wrappers remain unavailable. Never infer coordinates from application source_path or generated AST positions. These are inspection snapshots and caller-supplied schema metadata is not authenticated evidence. Keep conversion/refusal behavior unchanged.

**Bounded helper recovery:** inspector callable globals/file/code establish provenance, not application source_path. Carry ordered `support_definitions` separately through ToolInfo/ToolSchema adapters and JSON; reserve and validate support bindings at generation. Do not copy module startup, dynamic state, closures, decorated helpers, or arbitrary classes. Keep the unsupported dynamic-value refusal example alongside the successful runnable helper example.

**v0.13.0 refusal assessment:** `unsupported_cli_parameter_callback` is per source parameter and target; `unsupported_fastapi_dependency` is only for `SourceType.API` and includes route context. Both refuse before writes even with scaffold permission. Their `reference_analysis="skipped_due_to_refusal"` field is per refusal diagnostic: do not imply binding analysis ran for blocked targets. Consequences say behavior would be lost without equivalent implementation; conversion is refused. Keep README and shipped CLI/Python skills explicit that these diagnostics require v0.13.0 or newer; until publication, use a source checkout.
