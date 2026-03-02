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
- In Codex sandbox, use `nix develop .#coding-agent -c ...` (plain `nix develop -c ...` is intentionally rejected in Codex).
- In Codex sandbox, use `just agent-check` / `just agent-ci` for validation tasks.
- For automated checks outside Codex sandbox (agents/CI), run `just ci` directly.
- For target-library coverage investigation, prefer `scripts/inspect_target_library.py` (e.g. `just inspect-libzstd`) over ad-hoc one-off commands.

## Maintenance policy

- Keep changes minimal and incremental.
- Update docs only for user-visible behavior/API/CLI contract changes.
- Internal-only implementation tweaks (e.g. devShell guardrails, refactors) do not require routine updates to `DESIGN.md`/`TODO.md`/`README.md` unless they change documented workflows.
- Keep this file short; only add rules that are unlikely to change soon.
