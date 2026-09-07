# Roadmap

## Direction

Define typed Python tools once, serve them as CLI, API, or MCP interfaces, and generate
ordinary framework code that users can inspect and own. Keep the public entry points
small: `App.tool()`, `App.serve()`, `App.eject()`, and `load(...).to_cli()/to_api()/to_mcp()`.

The next milestone is confidence in the supported subset, not broader conversion claims:

- supported conversions preserve behavior;
- unsupported or lossy cases explain what cannot be preserved;
- live and generated interfaces agree on their shared interface semantics;
- documentation and shipped agent skills describe executable behavior.

The phases below express priority, not promised release dates. Correctness and contract
consolidation come before deeper transformations or performance infrastructure.

## v0.8 — Current foundation

- **One definition, three live interfaces:** registered Python functions can run through
  Typer, FastAPI, or FastMCP, or be ejected as framework source.
- **Six conversion directions:** existing Typer, FastAPI, and FastMCP applications can be
  inspected and converted within the documented supported subset.
- **Immutable conversion schema:** `ApplicationSchema`, `ToolSchema`, and `ParameterSchema`
  support inspection and generation; `ToolInfo` compatibility views remain available.
- **Target projections:** conversion exposes intermediate target projections before
  rendering. Some effective parameter defaults are still decided by templates.
- **Strict schema serialization:** supported non-JSON defaults use tagged `$intpot`
  envelopes; executable default rendering preserves supported value semantics.
- **Basic body transforms:** supported CLI output and return conventions are translated;
  FastAPI response annotations account for value, `None`, and fallthrough outcomes.
- **Explicit dependency refusal:** inspection records FastAPI dependencies, but conversion
  to CLI/MCP rejects unsupported dependency semantics rather than silently dropping them.
- **Practical tooling:** recursive Typer command inspection, direct import extraction,
  collision-safe directory output, actionable source failures, scaffolding, and agent skills.
- **Verification:** generated-artifact execution tests, conversion snapshot drift tests,
  and a Python 3.11–3.14 compatibility matrix.

Live serving currently uses registered callables and compatibility metadata; it does not
consume the immutable schema in the same way as generation. Completing shared interface
semantics is planned below. Live execution and standalone export also have deliberately
different capabilities: a callable may depend on runtime values that cannot be exported.

## Phase 1 — Correctness and honest documentation

- [ ] Preserve control flow in API/MCP-to-CLI conversion, including early returns, loop
      returns, and unreachable side effects. Prefer retaining implementation returns and
      letting the existing outer CLI wrapper print results over rewriting returns to echo.
- [ ] Replace substring-based import filtering with structural binding analysis. Remove
      imports only when their uses have actually been removed or translated.
- [ ] Add behavioral live-versus-ejected tests for parameter placement, defaults, response
      shapes, async behavior, errors, and naming—not only route/schema presence.
- [ ] Align the README, architecture illustrations, cookbook, and shipped skills with the
      implementation. Distinguish `App` from `IntpotApp`, including `.project()` and `.tools`
      behavior; keep public-command guidance in parity ([#121](https://github.com/tugrulguner/intpot/issues/121)).
- [ ] Execute cookbook and shipped-skill examples, including single-tool CLI applications,
      so prose and expected output cannot drift independently of tests.
- [ ] Keep contributor guidance accurate and agent installation predictable
      ([#123](https://github.com/tugrulguner/intpot/issues/123),
      [#122](https://github.com/tugrulguner/intpot/issues/122)).

Acceptance: the original failure cases have generated-consumer regressions, documented
examples execute, and the supported Python/framework matrix remains green. Source-level
audit findings must be reproduced before treating their fixes as verified.

## Phase 2 — Complete the shared interface contract

- [ ] Centralize target decisions for names, parameter placement, required/default rules,
      descriptions, and response policy. Projections should expose those decisions rather
      than leave hidden defaults to templates.
- [ ] Reuse shared interface decisions in live builders and source renderers while keeping
      callable bindings separate from recovered source. Do not make live serving depend
      on every value being serializable or exportable.
- [ ] Transform immutable schema records directly and share unchanged parameters. Keep
      mutable `ToolInfo` adaptation at compatibility boundaries rather than repeatedly
      thawing, deep-copying, and refreezing records during projection.
- [ ] Isolate existing default-value freezing, serialization, identity, and source-rendering
      behavior behind a small private module. Preserve supported values and regression
      coverage; do not replace these contracts with generic `repr()` or JSON conversion.
- [ ] Expose structured conversion diagnostics: preserved, adapted, unsupported, and
      requiring manual implementation. Diagnose unresolved symbols and missing bodies
      instead of letting generated source appear complete without qualification.

Acceptance: shared behavior is defined once, projections explain the emitted interface,
and compatibility APIs retain their documented behavior. No generated-code execution is
introduced as a prerequisite for live serving.

## Phase 3 — Practical conversion coverage

- [ ] Carry a bounded dependency closure within one source module: referenced helper
      functions, constants, classes, models, defaults, annotations, decorators, and base
      classes. Start with explicitly supported cases; diagnose dynamic or ambiguous cases
      rather than promise arbitrary Python recovery.
- [ ] Preserve parameter descriptions and supported `Annotated` metadata across targets
      ([#1](https://github.com/tugrulguner/intpot/issues/1),
      [#3](https://github.com/tugrulguner/intpot/issues/3),
      [#9](https://github.com/tugrulguner/intpot/issues/9),
      [#38](https://github.com/tugrulguner/intpot/issues/38)).
- [ ] Preserve repeatable Typer/Click options and collection cardinality in target schemas.
- [ ] Support package and sibling imports with explicit loading semantics. Direct file
      loading currently does not add the source directory to `sys.path`.
- [ ] Support explicit app selection and bounded factory loading without making directory
      discovery import every Python file.
- [ ] Define multi-method FastAPI route semantics instead of reducing them to one method.
- [ ] Generate nested command hierarchies ([#2](https://github.com/tugrulguner/intpot/issues/2)).
      Recursive inspection already works; hierarchy generation remains separate work.
- [ ] Add realistic runnable examples demonstrating these capabilities and their refusal
      paths ([#5](https://github.com/tugrulguner/intpot/issues/5)).

Acceptance: each new capability includes a supported-case example, an unsupported-case
policy, and execution through the generated target—not merely a matching source string.

## Phase 4 — Profile, then optimize

- [ ] Establish reproducible benchmarks separating cold startup, inspection, projection,
      and rendering for small and larger applications. Record Python and dependency versions.
- [ ] Measure the benefit of immutable structural sharing during projection.
- [ ] Reuse function analysis and a module/import index within one inspection operation
      instead of reparsing the same module for each tool.
- [ ] Evaluate compiled-template reuse while preserving per-render alias isolation and
      concurrency safety.

There are no speedup commitments yet. Avoid persistent caches, parallel conversion, native
extensions, or new performance dependencies until representative measurements justify them.
Low-risk removal of redundant work can accompany earlier correctness changes when tested.

## Later — Bounded deeper transformations

These are research directions, not a promise of universal equivalence between frameworks.
Each requires an explicit semantic contract and independent acceptance criteria.

- **Dependency injection mapping** ([#20](https://github.com/tugrulguner/intpot/issues/20)):
  preserve applicable dependency ordering, caching, security, exception propagation, and
  cleanup lifetime. Replacing `Depends()` with a context manager alone is not equivalence.
  Keep unsupported conversions rejected until a particular subset is proven.
- **Pydantic model parameters** ([#17](https://github.com/tugrulguner/intpot/issues/17)):
  define target-specific representation and validation before choosing flattening. MCP and
  HTTP can represent structured inputs differently from CLI arguments.
- **Cross-module dependency resolution:** only after same-module closure is reliable;
  distinguish project code from external packages and avoid implicit environment provisioning.
- **Deeper body/error transforms** ([#19](https://github.com/tugrulguner/intpot/issues/19)):
  add individual supported patterns for HTTP/MCP errors, context objects, streaming, and
  background work. Reject cases without a meaningful target equivalent.
- **Simultaneous serving** ([#32](https://github.com/tugrulguner/intpot/issues/32)):
  defer until interface parity is established; specify transports, startup, shutdown,
  cancellation, and CLI interaction before adding `serve --all`.

## Boundaries

- Keep Typer, FastAPI, and FastMCP as the supported framework focus.
- Keep generated output ordinary Python with no intpot runtime dependency; other application
  dependencies may still be required.
- Do not add a runtime bridge for adapting arbitrary existing framework applications.
  Building live interfaces from `intpot.App` remains a core capability.
- Do not attempt unrestricted Python transpilation or claim that every framework behavior
  has a lossless equivalent.
- Keep variadic tool signatures unsupported: `*args` and `**kwargs` do not have one
  consistent CLI/API/MCP representation. Prefer explicit named parameters.
- Preserve the trusted-source boundary: detection imports code; inspection and dry-run
  conversion are not sandboxes.
- Do not introduce a plugin system or another generalized intermediate representation just
  to support the current three backends.

Linked items have existing issue discussions; unlinked items are directional work, not
implementation commitments. Check current issues and open work before starting a scoped
change. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and contribution guidance.
