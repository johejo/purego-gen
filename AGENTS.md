# AGENTS.md

This repository keeps agent instructions intentionally small.

## Purpose

Build a practical C-header-to-purego binding generator.

## Source of truth

- Detailed design: `DESIGN.md`
- Execution plan: `TODO.md`
- High-level project summary: `README.md`

Do not duplicate volatile details in this file.

## Stable project rules (v1)

- Target scope is non-Windows first.
- CLI is single-command: `purego-gen` (no subcommands in v1).
- `--lib-id` is required and is used in generated helper names.
- Generated identifiers are unexported and prefixed with `purego_`.
- Generated code expects a caller-provided library handle.
- Prefer panic-free registration flow (`Dlsym + RegisterFunc`) on v1 target OSes.
- Run `pytest` in the `nix` devshell by default because it requires `LIBCLANG_PATH`.
- In Codex sandbox, prefer `just agent-check` / `just agent-ci` (single cached nix entrypoint).
- For automated checks outside Codex sandbox (agents/CI), run `just ci` directly.
- Do not invoke `lefthook` from agents unless hook behavior itself is being tested.

## Maintenance policy

- Keep changes minimal and incremental.
- When behavior changes, update `DESIGN.md` first, then `TODO.md`, then `README.md` summary.
- Keep this file short; only add rules that are unlikely to change soon.
