# Copyright (c) 2026 purego-gen contributors.

"""CLI argument parsing for config-driven purego-gen execution."""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Validated CLI options."""

    config_path: str
    out: str


class _ParsedArgs(argparse.Namespace):
    """Typed argparse namespace."""

    config: str
    out: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="purego-gen",
        description="Generate low-level Go bindings for ebitengine/purego.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="Generator config JSON path.",
    )
    parser.add_argument(
        "--out",
        default="-",
        metavar="PATH",
        help="Output file path. Use '-' (or omit) to write to stdout.",
    )
    return parser


def parse_options(argv: list[str]) -> CliOptions:
    """Parse CLI arguments into validated options.

    Returns:
        Parsed config path and output path.
    """
    parser = _build_parser()
    namespace = parser.parse_args(argv, namespace=_ParsedArgs())
    return CliOptions(
        config_path=namespace.config,
        out=namespace.out,
    )


__all__ = ["CliOptions", "parse_options"]
