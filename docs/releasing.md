# Releasing intpot

For maintainers with push access to `tugrulguner/intpot`. Contributors don't need any of
this — open a PR with a changelog fragment and a maintainer takes it from there.

## Version

The version lives in exactly one place: `version` in `pyproject.toml`. `__version__` and
`intpot --version` both read it back through `importlib.metadata`, and `uv.lock` is
regenerated from it — never edit any of those by hand.

```bash
uv version 0.5.1          # or: uv version --bump patch|minor|major
```

That single command rewrites `pyproject.toml` and re-locks `uv.lock`.

## Steps

1. `make changelog` — towncrier assembles every fragment in `changelog.d/` into a dated
   `## [0.5.1]` section and deletes the fragments. Read the result before committing it;
   `make changelog-draft` renders the same thing without writing. The section is
   required, not optional — the release is blocked without it.
2. Read the assembled section and ask whether anything in it came off
   [`ROADMAP.md`](../ROADMAP.md) — move those items out of the planned list, and bump the
   "(current)" heading to the version you are cutting. Nothing enforces this: a test can
   assert a feature exists, but not that a roadmap still calls it unbuilt. The roadmap
   once described body transforms as a v2 goal for four months after they shipped.
3. Open a release PR and merge it once `make check` and CI are green.
4. Tag the merge commit and push the tag:

   ```bash
   git tag v0.5.1 && git push origin v0.5.1
   ```

## What the tag triggers

The tag starts [`.github/workflows/release.yml`](../.github/workflows/release.yml), which
gates on two things before publishing anything: the tag has to match the `pyproject.toml`
version, and `CHANGELOG.md` has to have a section for it. Once both pass and CI is green
it builds, publishes to PyPI through trusted publishing, then opens a GitHub Release for
the tag — notes taken from that changelog section, with the built wheel and sdist
attached.

Nothing in a release is written twice: the version comes from `pyproject.toml` and the
release notes come from `CHANGELOG.md`.
