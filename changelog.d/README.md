# Changelog fragments

Every unreleased user-facing change is represented by one file in this directory rather
than a direct edit to `CHANGELOG.md`.

## Tracked work

When the change has a tracking issue, use its issue number:

```text
changelog.d/<issue-number>.<type>.md
```

Numeric fragments must name an issue, not a pull request. Towncrier links the release note
to the underlying user problem.

## Small direct changes

For a focused direct change without an issue, let Towncrier generate a unique orphan ID:

```bash
uv run towncrier create +.changed.md
```

Replace `changed` with `added`, `deprecated`, `removed`, or `fixed` when appropriate. Keep
the generated identifier; do not replace it with the pull-request number.

Write one sentence describing what changed **for someone using Intpot**, not what changed in
the implementation. Markdown is allowed. Do not add a manual issue or PR link.

For a genuinely internal-only change, a maintainer may apply `skip-changelog`. Deleting a
fragment does not satisfy CI, and `CHANGELOG.md` is assembled only during release
preparation.

## Previewing

```bash
make changelog-draft
```

This renders the next release section without modifying the working tree.
