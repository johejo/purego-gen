# AGENTS.md

## Purpose

Build a practical C-header-to-purego binding generator.

## Guidelines

- Target scope is non-Windows first.
- Keep the generator practical and incremental; avoid treating pre-v1 details as frozen.
- If you are launched from within nix devshell; run commands directly (e.g., `just check`, `just ci`, `uv run pytest`).
- See Justfile for useful commands for development.
- For target-library coverage investigation, prefer `scripts/inspect_target_library.py` (e.g. `just inspect-libzstd`) over ad-hoc one-off commands.
