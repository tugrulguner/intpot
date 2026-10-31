# AGENTS.md — `src/intpot/`

Rules for changing intpot source. The root `AGENTS.md` covers what intpot is, the
workflow, and keeping docs honest; this file covers the code itself.

## Rules that come from real bugs

**Tests must execute generated code.** Every generator test used to assert on the
generated *string*. Four separate bugs shipped that way — FastAPI handlers that returned
500 on every request, Typer commands that printed nothing — because the output looked
correct as text. `exec` the module and issue a real request or invoke a real command.

**A change to one template probably belongs in the other two.** The CLI and API templates
once hardcoded return annotations while the MCP one used the real type; that asymmetry
was the bug. When you touch `templates/*.j2`, check the sibling templates.

**`serve` and `eject` must expose the same interface.** They are the same app in two
forms. They once disagreed about whether parameters came from the query string or the
body. `tests/test_runtime_builders.py` checks representative body-parameter parity, not
every Python signature shape. Extend the parity cases whenever the signature contract
changes rather than assuming that one case proves the whole interface.

**Annotations must describe what the body actually returns.** FastAPI validates the
response against the return annotation, so `-> dict` over a body returning an `int` is a
runtime 500, not a type-checker complaint.

**Detection executes user code.** `detect_source` imports the module. Anything that scans
many files must tolerate one of them raising — see `core/discovery.py`.

**Identify framework objects structurally, never with `isinstance`.** typer 0.26 vendored
its own copy of click as `typer._click`, so a Typer app stopped being an instance of
anything in the standalone `click` package. Every check written against click failed at
once: the inspector found zero tools in any Typer app, silently, for two and a half
months. Match on what an object *has* — a `commands` mapping, a type's `name` — the way
`detector.py` and `_is_depends` already do. The same applies to any framework we don't
control, which is all of them.

**Generated code must parse whatever the source contains.** Descriptions, parameter names
and project names all come from someone else's code. A quote or newline in a description
produced an unterminated string literal; two parameter names sanitising onto one
identifier produced a duplicate argument. Never hand-write quotes around interpolated
text — use the `repr` filter, which is Python's own literal writer. Tests must `compile()`
the output, not inspect it.

**Error paths need their own probes.** Exercising the happy path never reaches them, so
they are where this codebase's bugs survive longest. #101 took three review rounds and
every finding was in an `except` branch: `SystemExit` slipping past `except Exception`, a
documented exception a wrapper had made unreachable, and a cause chain pointing at
itself. When you touch error handling, enumerate what can actually be raised and run each
one — a source that exits, a source that raises, a missing dependency, a missing sibling
module — rather than reasoning about them.

**A guard that can collect nothing must assert it found something.** The test asserting
every CLI flag appears in the README derives its cases by walking the command tree. When
that walk broke, the test quietly went from 22 assertions to 1 and kept reporting green —
worse than having no test, because it still looked like coverage. Any parametrised test
whose inputs come from introspection needs a floor on what discovery returns.

## Reviewing a change

The rules above came from bugs that shipped — check those first. Beyond them, these are
the contracts a change has to keep.

**Architecture**

- Inspectors subclass `BaseInspector` and return `list[ToolInfo]` from `inspect()`;
  generators subclass `BaseGenerator` and return `str` from `generate()`.
- `to cli` / `to mcp` / `to api` all delegate to `commands/_convert.py`'s `convert()`.
  A conversion command that reimplements it will drift from the other two.
- Commands take `typer.Argument` / `typer.Option` parameters and return `None`.
- Shared models belong in `core/models.py`, not beside their first consumer.

**Canonical schema and compatibility models**

- A required parameter is one whose `default is _SENTINEL`. Outside `core/`, use the
  `.required` property rather than comparing against the sentinel.
- `name` on both dataclasses has already been through `sanitize_identifier()` — don't
  sanitize it again.
- `ApplicationSchema` is the seam between both halves of intpot. Its nested `ToolSchema`
  and `ParameterSchema` records and collections are immutable; projections must build a
  new schema rather than mutate the source snapshot.
- `ToolInfo` and `ParameterInfo` remain mutable inspector/generator compatibility models.
  `.tools` returns detached copies, so mutating one must not change `.schema` or output.
- A semantic field added to either representation must be mapped in both conversion
  directions and reviewed across every inspector, generator, transform, and serializer.

**Templates**

- The custom Jinja filters are `repr`, `pascal`, and `escape_doc`, registered in
  `core/generators/_render.py`. An unknown filter raises `TemplateAssertionError` while
  loading the template.
- Path parameters in the API template must not get `= Path(...)`; FastAPI infers them
  from the route.
- Generated code carries its own imports — review the import block, not just the body.

**Transforms and return types** (`transforms.py`)

- The AST pass maps CLI `typer.echo` calls to returned values and `typer.Exit` to
  return/raise behavior. API/MCP returns remain returns when targeting CLI; the generated
  command wrapper prints the implementation result so early returns still terminate it.
- `_target_return_type` decides the implementation annotation. Generated CLI command
  wrappers are always `None`, while their implementation functions keep the source return
  annotation.
- API annotations must describe every reachable path. Scalar returns are wrapped as
  `{"result": ...}`, but the presence of one `return` does not prove that a conditional
  body cannot fall through to `None`. Treating `dict` as unconditional is what made every
  generated FastAPI handler 500 before #56; ignoring fallthrough creates the same failure
  on only some requests.
- MCP keeps the source annotation, except from CLI, where it becomes `str`. Plain terminal CLI echoes must return text rather than raw numeric values under that schema; evaluate the expression once, preserve None as empty text, and avoid builtin/parameter collisions.

**CLI parameter callbacks**

- `ParameterInfo` and `ParameterSchema` append the boolean `unsupported_callback`; retain
  positional compatibility, equality/hash, adapters, and JSON mapping (only true is emitted).
- CLI inspection captures callable parameter callbacks from constructed parameters and
  registered-command fallback metadata. Do not store live callbacks or repr strings.
- A parameter named `help` can be a real user input. Exclude synthetic help only when
  it does not expose a value to the command, not by name alone; otherwise its callback
  bypasses refusal. Keep a real framework auto-help control in callback regressions.
- `core/callbacks.py` guards API/MCP projection and direct generation, raising public
  `UnsupportedCLIParameterCallbackError` before output is written. Inspection stays available.
- Callback validation can run before the command body. Compare rejected source inputs and
  conversion refusal, not just retained bodies or successful calls. This guard is not a
  generalized assessment engine and does not change live `App` behavior.

**Errors**

- `detect_source()` raises `DetectionError`. Commands catch it and exit through
  `typer.Exit(1)` with a message on stderr — never a traceback.
- `discover_sources()` stays quiet about files that simply aren't apps (verbose only),
  but always reports an import failure to stderr. A scan has to survive one bad file
  without going silent about it (#59).
- **`except Exception` does not catch everything.** `SystemExit` and `KeyboardInterrupt`
  derive from `BaseException`. A source calling `sys.exit()` at import — which
  `argparse.parse_args()` does on a bad parse — went straight through detection: intpot
  exited with *that source's* code and printed nothing, and a directory scan stopped
  there. Catch `SystemExit` explicitly alongside `Exception`; widening to `BaseException`
  instead would swallow Ctrl-C.
- **An exception subclass rewires every `except` for its parent.** Subclassing
  `DetectionError` is how a new failure kind reaches existing handlers unchanged — and
  also how it reaches the ones that should have treated it differently. Any site that
  tells the two apart has to catch the subclass *first*, or the parent matches and the
  distinction silently disappears. Adding a subclass means auditing every existing
  handler for the parent, `discover_sources()` above being the one that matters.
- **`raise X from Y` mutates X.** It sets `X.__cause__ = Y`. When `Y.__cause__` is
  already `X` — which it is whenever you unwrap and re-raise — the chain points at itself
  and anything walking it loops. Re-raise an untouched original `from None`; chain a
  newly built error from what actually failed.
- **Wrapping an exception can break a documented contract.** `load()` documents that it
  raises `ModuleNotFoundError`; wrapping import failures made its own handler
  unreachable. Check `Raises:` docstrings and callers before introducing a wrapper.

**Tests**

- Use the `tmp_source` fixture from `conftest.py`; CLI tests use `typer.testing.CliRunner`.
- Assert on behaviour, not on `exit_code == 0`.
- Name them `test_<scenario>` or `test_<framework>_<scenario>`; assert on raised errors
  with `pytest.raises(ErrorClass, match="...")`.

**Style**

- Every file opens with `from __future__ import annotations`.
- Ruff owns formatting (88 columns, double quotes, isort with intpot first-party) —
  don't review it. B008 is suppressed deliberately, so
  `typer.Option()` and `typer.Argument()` as defaults are correct.
- Don't ask for docstrings, annotations, or abstractions on code the change didn't touch.

**Missing body bindings:** public converter assessment statically renders target implementations and reuses scope-aware global analysis to diagnose absent bindings. Keep `missing_binding` per-target and do not bypass refusal with scaffold permission. Body-recovery fields remain body-only. Ordered generated function decorator/default/eager-annotation loads use `core/definition_bindings.py` and per-target `missing_definition_binding` diagnostics, including support functions and public wrappers. Use `annotation_missing()` for per-target `missing_annotation_binding` on string/postponed annotation global roots against actual completed-module bindings, excluding annotation-only declarations. Parse type-position strings without evaluating them; preserve imported Literal/Annotated aliases and their value strings. Keep before-write refusal and scaffold non-bypassability. This does not certify type resolution, alias values, framework registration timing, initializer behavior, imports or runtime initialization. Direct generators and live App remain separate compatibility paths.

**MCP-source numeric validation (unreleased):** preserve ordinary finite inclusive primitive Field/Annotated bounds through minimum/maximum. Carry unsupported_mcp_numeric_range through records/hash/adapters/true-only JSON/runtime detachment, with source-specific UnsupportedMCPNumericRangeError and assessment/refusal before writes even with scaffolds. Inspect actual annotation validators as well as bounds; do not trust JSON schema alone or execute factories. Preserve optional dependency imports and existing guard precedence. Exercise inventory_reservation.py via mcp_application_conformance.py through original native MCP, generated CLI/HTTP, defaults, rejections, stock-limit error and receipts. No general Pydantic/context/model conversion promise.

**API-source numeric validation (unreleased):** reuse minimum/maximum for ordinary finite inclusive ge/le constraints on primitive int/float fields, inspecting normalized Query/Body/Header/Path metadata (including ordinary required Annotated declarations). Preserve `unsupported_api_numeric_range` through records, immutable equality/hash, adapters, detached runtime copies and true-only JSON. Refuse exclusive/multiple-of/strict/custom/unknown numeric validation and unsupported defaults with UnsupportedAPINumericRangeError before writes/scaffolds; retain dependency/callback precedence. Execute storage_quote.py via api_application_conformance.py: source HTTP, native generated CLI/MCP, defaults, validation, helper error and receipt side effects. No broad Pydantic/model/MCP-source constraint recovery claim.

**Application-led numeric ranges (unreleased):** preserve ordinary CLI integer/float inclusive finite bounds through `minimum`/`maximum` parameter fields, adapters, hashes, JSON and generation. `unsupported_numeric_range` marks clamp/exclusive/custom range semantics for explicit assessment and `UnsupportedCLINumericRangeError` before writes, even with scaffold permission. Reuse the canonical schema and native target validation, preserving existing callback/dependency precedence. Run `examples/application_conformance.py` through native clients: original CLI, low-level same-source CLI renderer, public CLI-to-API/MCP conversion; test valid totals/defaults, rejected bounds/types, business errors and receipt side effects. Public same-source conversion remains refused. Plain terminal CLI echoes targeting MCP evaluate once and return text matching the existing str output schema (None becomes empty text); reserve original parameter/body names for local builtins/value aliases and leave API scalar returns unchanged. No client validation bypass. General output options/binary streams/explicit-return/control-flow equivalence and reverse API/MCP constraint recovery are not certified.

**Exact body-reference locations (v0.16.0 release candidate):** `core/reference_locations.py` maps only unchanged captured plain-body global loads to source ranges, using `source_digest`/`support_source_digests` from verified decoded source. Recheck digest and bounds; require whole retained-body equality to the original and emitted suffix. Decline nested/deferred scopes, transformed or stale source and over-budget ranges explicitly. Columns are 1-based Unicode characters, with exclusive end positions. Preserve definition-location snapshots, dependency chains, guards and policy; caller metadata is not authenticated.

**Bounded binding chains (v0.15.0):** `core/binding_chains.py` adds `references[*].dependency_chain` to missing body/definition/annotation binding diagnostics. Use only scoped global-body references among that tool's emitted wrapper, implementation and retained helpers; choose one shortest lexically deterministic path per owner and leave unreachable, rebound or unanalyzable owners unavailable. Paths are static binding dependencies, not runtime calls or execution traces. Preserve existing diagnostic fields, provenance, guards, code-string APIs and before-write/scaffold behavior. The transitive missing-helper example uses an explicit caller-authored schema, not expanded source recovery.

**Definition provenance (v0.14.0):** `core/provenance.py` captures owning-file definition bounds by matching existing callable code to compiled file source without executing it. `ToolInfo`/`ToolSchema` carry `source_location` and `support_source_locations` through adapters, projections and JSON. Top-level diagnostic locations describe tool definitions; generated references may identify implementation/helper origins, while synthetic wrappers remain unavailable. Never infer coordinates from application source_path or generated AST positions. These are inspection snapshots and caller-supplied schema metadata is not authenticated evidence. Keep conversion/refusal behavior unchanged.

**Bounded helper recovery:** inspector callable globals/file/code establish provenance, not application source_path. Carry ordered `support_definitions` separately through ToolInfo/ToolSchema adapters and JSON; reserve and validate support bindings at generation. Do not copy module startup, dynamic state, closures, decorated helpers, or arbitrary classes. Keep the unsupported dynamic-value refusal example alongside the successful runnable helper example.
