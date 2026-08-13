---
name: review-code
description: Review uncommitted or staged code changes in the intpot repo. Use when asked to review local changes, check current diff, or review before committing.
disable-model-invocation: true
allowed-tools: Bash(git *) Bash(.venv/bin/python *) Bash(.venv/bin/pytest *) Read Grep Glob Agent
argument-hint: [file-path]
---

# intpot Local Code Review

Follow [`docs/reviewing.md`](../../../docs/reviewing.md) — the uncommitted-work path in
step 1, then steps 2 through 6, reporting locally rather than through `gh`.

`$ARGUMENTS` is an optional path to scope the review; with no argument, review every
uncommitted change.

The criteria come from [`AGENTS.md`](../../../AGENTS.md). Don't add any here — this file
is invisible to every agent that isn't Claude Code.
