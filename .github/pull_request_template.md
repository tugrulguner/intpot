## Summary and motivation

<!-- What changed, and which concrete user or maintainer problem does it solve? -->

## Related issue or direct-PR reason

<!-- Use `Closes #<issue-number>` for tracked work. If there is no issue, explain why this is a small, scoped direct PR such as a focused fix, test, documentation repair, or maintenance change. -->

## Scope and non-goals

<!-- State what this PR changes and what it deliberately leaves alone. -->

## Safety and compatibility

<!-- Address public API compatibility, framework floors, source/target asymmetry, error behavior, generated-code validity, and security implications as applicable. -->

## Verification and behavioral evidence

<!-- List exact commands and results. A reviewer must be able to reproduce the evidence. -->

- [ ] `make check`
- [ ] `make build`
- [ ] Relevant oldest/latest framework compatibility lanes
- [ ] Real public CLI/API/runtime behavior exercised

## Generated artifact evidence

<!-- If inspection, transforms, generators, templates, or eject changed, execute generated output through its real consumer. A compile or string assertion alone is not enough. Write “Not applicable” only when no generated behavior changed. -->

- [ ] Generated CLI invoked
- [ ] Generated FastAPI app requested
- [ ] Generated FastMCP tool called
- [ ] Checked-in generated examples exercised where applicable

## Documentation and changelog

- [ ] Updated README, examples, shipped skills, or review guidance when their contract changed.
- [ ] Added `changelog.d/<issue-number>.<type>.md` for tracked user-facing work; or
- [ ] Added a unique `changelog.d/+<identifier>.<type>.md` orphan fragment for a small direct user-facing change; or
- [ ] This has no user-visible effect and should receive the maintainer-applied `skip-changelog` label.
- [ ] Did not edit `CHANGELOG.md` or package versions directly.

## Reviewer guidance

<!-- Point reviewers to the riskiest boundary, exact files, compatibility rows, negative cases, and evidence they should reproduce. -->
