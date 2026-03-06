# Copyright (c) 2026 purego-gen contributors.

"""Compatibility wrapper for the packaged golden-cases CLI."""

from __future__ import annotations

from pathlib import Path

from purego_gen_e2e.golden_cases_cli import main as run_main


def main(argv: list[str] | None = None) -> int:
    """Run the packaged CLI while preserving script-relative repo discovery.

    Returns:
        Process-like exit code.
    """
    return run_main(argv, repo_root=Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    raise SystemExit(main())
