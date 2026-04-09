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
- See also `./DESIGN.md`.

## Codex Orchestration

- Use `./scripts/codex-orchestrate.sh run` or `just codex-orchestrate` for the minimal planner/implementer/reviewer loop.
- Keep orchestration state only in `.codex/` and treat it as ephemeral local scratch data.
- `.codex/plan.txt` is planner output for one case, `.codex/review.txt` is the latest reviewer output, and `.codex/status.txt` is the current state.

### Roles

- `planner` inspects `tests/cases`, chooses one deterministic candidate that still needs implementation work, writes a decision-complete plan to `.codex/plan.txt`, runs `implementer`, and on success cherry-picks the resulting commit into the main worktree.
- `implementer` reads `.codex/plan.txt`, creates a temporary `git worktree`, implements the plan, asks `reviewer` for feedback, loops up to 5 review rounds, commits on convergence, and keeps the failed worktree for inspection when review does not converge.
- `reviewer` reviews the implementer work in `/review` style and writes either findings or `NO_FINDINGS` to `.codex/review.txt`.

### Defaults

- Run one case at a time, synchronously.
- Start from a clean main worktree with no staged, unstaged, or untracked files.
- Prefer a simple deterministic planner heuristic over a smart one.
- If review does not converge within 5 rounds, keep the implementer worktree for inspection, report its path in `.codex/status.txt`, and stop the loop.
