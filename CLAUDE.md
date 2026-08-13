# CLAUDE.md

See [AGENTS.md](AGENTS.md) — architecture, layout, the rules that come from real bugs,
and the contribution workflow. This file exists so Claude Code picks the same guidance up
automatically; keep the content in `AGENTS.md` so every agent reads one source.

`.claude/skills/` holds `review-code`, `pr-review`, and `sync-skills`. They are thin
wrappers — argument handling and tool scoping — around [`docs/reviewing.md`](docs/reviewing.md)
and `AGENTS.md`, which is where the actual guidance lives so that every agent reads it.
Don't put criteria or procedure in a skill file.
