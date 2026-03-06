# Copyright (c) 2026 purego-gen contributors.

"""CLI entrypoint for golden case update/check workflows."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import cast

from purego_gen_e2e.golden_cases_lib import check_cases, discover_cases, update_cases


class _ParsedArgs(argparse.Namespace):
    """Typed argparse namespace for this script."""

    mode: str
    strict_head: bool
    cases: list[str]


def _parse_args(argv: list[str] | None = None) -> _ParsedArgs:
    parser = argparse.ArgumentParser(
        description="Update/check case-driven golden outputs and runtime checks.",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("update", "check"),
        help="Operation mode: update generated.go files or run checks.",
    )
    parser.add_argument(
        "--strict-head",
        action="store_true",
        help="Compare generated.go against HEAD only (no working-tree fallback).",
    )
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        default=[],
        help="Run only selected case id. Repeatable.",
    )
    return cast("_ParsedArgs", parser.parse_args(argv))


def _resolve_installed_purego_gen_command() -> tuple[str, ...] | None:
    purego_gen_binary = shutil.which("purego-gen")
    if purego_gen_binary is None:
        return None
    return (purego_gen_binary,)


def main(
    argv: list[str] | None = None,
    *,
    repo_root: Path | None = None,
) -> int:
    """Run script entrypoint.

    Returns:
        Process-like exit code.
    """
    args = _parse_args(argv)
    resolved_repo_root = repo_root if repo_root is not None else Path.cwd()
    purego_gen_command = _resolve_installed_purego_gen_command()

    try:
        cases = discover_cases(repo_root=resolved_repo_root, selected_case_ids=args.cases)
        if args.mode == "update":
            update_cases(
                cases=cases,
                repo_root=resolved_repo_root,
                python_executable=sys.executable,
                purego_gen_command=purego_gen_command,
            )
        else:
            check_cases(
                cases=cases,
                repo_root=resolved_repo_root,
                python_executable=sys.executable,
                strict_head=args.strict_head,
                purego_gen_command=purego_gen_command,
            )
    except (RuntimeError, TypeError, ValueError) as error:
        sys.stderr.write(f"{error}\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
