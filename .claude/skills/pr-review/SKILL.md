---
name: pr-review
description: Review a GitHub pull request on the intpot repo. Use when asked to review a PR, given a PR URL or number, or told to check a pull request.
disable-model-invocation: true
allowed-tools: Bash(gh *) Bash(git *) Bash(.venv/bin/python *) Bash(.venv/bin/pytest *) Read Grep Glob Agent
argument-hint: <pr-number-or-url>
---

# intpot PR Review

Follow [`docs/reviewing.md`](../../../docs/reviewing.md) — the pull-request path in step 1,
then steps 2 through 6. `$ARGUMENTS` is the PR number or URL wherever that document writes
`<pr>`.

The criteria come from [`AGENTS.md`](../../../AGENTS.md), as step 3 says. Nothing about
reviewing this codebase is written in this file on purpose: it is the one place other
agents can't read, so anything that lands here is invisible to them and goes stale
unnoticed. It has before.
