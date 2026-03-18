# AGENTS.md

## Purpose

Build a practical C-header-to-purego binding generator.

## Guidlines

- Target scope is non-Windows first.
- Keep the generator practical and incremental; avoid treating pre-v1 details as frozen.
- Run `pytest` in the `nix` devshell by default because it requires `LIBCLANG_PATH`.
- See Justfile for useful commands for development.
- In sandbox, run the needed `just` target via `nix develop .#coding-agent -c "just <task>"` (e.g., `just check`, `just ci`, `just ci-strict`, `uv run pytest`).
- For automated checks outside sandbox, run `just ci` directly.
- For target-library coverage investigation, prefer `scripts/inspect_target_library.py` (e.g. `just inspect-libzstd`) over ad-hoc one-off commands.
