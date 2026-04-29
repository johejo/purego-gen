# AGENTS.md

## Purpose

Build a practical C-header-to-purego binding generator.

## Guidelines

- Target scope is non-Windows first.
- Keep the generator practical and incremental; avoid treating pre-v1 details as frozen.
- If you are launched from within nix devshell; run commands directly (e.g., `just check`, `just ci`, `uv run pytest`).
- See Justfile for useful commands for development.
- For target-library coverage investigation, prefer `purego-gen inspect` over ad-hoc one-off commands.
- For one-shot python script, use `./scripts/uv-run-python-src.sh`.
- For Zig work, prefer expanding `tests/cases` golden coverage over adding extra Zig-only unit tests unless a low-level helper is hard to validate through golden cases.
- For Zig golden-case work, prefer cases that either minimize output drift from existing support or unlock a meaningful chunk of missing surface area in one pass.
- Treat Zig golden output as `gofmt`-normalized when comparing against `generated.go`, and be careful to free owned memory on unsupported/skip paths in Zig declaration extraction.
- See also `./DESIGN.md`.
