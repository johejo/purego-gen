# Copyright (c) 2026 purego-gen contributors.

"""CLI argument parsing for purego-gen subcommands."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

_DEFAULT_SAMPLE_SIZE = 12
_DEFAULT_EMIT_KINDS = "func,type,const,var"


@dataclass(frozen=True, slots=True)
class GenOptions:
    """Validated options for the ``gen`` subcommand."""

    config_path: str
    out: str


@dataclass(frozen=True, slots=True)
class InspectOptions:
    """Validated options for the ``inspect`` subcommand."""

    header_path: str
    clang_args: tuple[str, ...]
    sample_size: int
    render_out: str | None
    render_lib_id: str | None
    render_pkg: str
    render_emit: str
    func_filter: str | None
    type_filter: str | None
    const_filter: str | None
    var_filter: str | None


class _TopLevelArgs(argparse.Namespace):
    """Typed argparse namespace for top-level subcommand dispatch."""

    subcommand: str | None


class _GenArgs(argparse.Namespace):
    """Typed argparse namespace for gen subcommand."""

    config: str
    out: str


class _InspectArgs(argparse.Namespace):
    """Typed argparse namespace for inspect subcommand."""

    header_path: str
    clang_args: list[str]
    sample_size: int
    render_out: str | None
    render_lib_id: str | None
    render_pkg: str
    render_emit: str
    func_filter: str | None
    type_filter: str | None
    const_filter: str | None
    var_filter: str | None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="purego-gen",
        description="Generate low-level Go bindings for ebitengine/purego.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # gen subcommand
    gen_parser = subparsers.add_parser(
        "gen",
        help="Run code generation from a config file.",
        allow_abbrev=False,
    )
    gen_parser.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="Generator config JSON path.",
    )
    gen_parser.add_argument(
        "--out",
        default="-",
        metavar="PATH",
        help="Output file path. Use '-' (or omit) to write to stdout.",
    )

    # inspect subcommand
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect parser coverage for a header file.",
        allow_abbrev=False,
    )
    inspect_parser.add_argument("--header-path", required=True, help="Header file path.")
    inspect_parser.add_argument(
        "--clang-arg",
        action="append",
        default=[],
        dest="clang_args",
        help="Additional clang arg. Repeat this flag as needed.",
    )
    inspect_parser.add_argument(
        "--sample-size",
        type=int,
        default=_DEFAULT_SAMPLE_SIZE,
        help=f"How many functions/skipped typedefs to sample (default: {_DEFAULT_SAMPLE_SIZE}).",
    )
    inspect_parser.add_argument(
        "--render-out",
        help="Write rendered Go output to path (optional).",
    )
    inspect_parser.add_argument(
        "--render-lib-id",
        help="Library id used when rendering (default: bindings).",
    )
    inspect_parser.add_argument(
        "--render-pkg",
        default="bindings",
        help="Go package name used when rendering (default: bindings).",
    )
    inspect_parser.add_argument(
        "--render-emit",
        default=_DEFAULT_EMIT_KINDS,
        help=f"Comma-separated emit categories for render mode (default: {_DEFAULT_EMIT_KINDS}).",
    )
    inspect_parser.add_argument("--func-filter", help="Optional regex filter for function names.")
    inspect_parser.add_argument("--type-filter", help="Optional regex filter for type names.")
    inspect_parser.add_argument("--const-filter", help="Optional regex filter for constant names.")
    inspect_parser.add_argument(
        "--var-filter", help="Optional regex filter for runtime variable names."
    )

    return parser


def parse_options(argv: list[str]) -> GenOptions | InspectOptions:
    """Parse CLI arguments into validated options.

    Returns:
        Parsed options for either the gen or inspect subcommand.

    Raises:
        SystemExit: When no subcommand is provided or arguments are invalid.
    """
    parser = _build_parser()
    namespace = parser.parse_args(argv, namespace=_TopLevelArgs())

    if namespace.subcommand == "gen":
        gen_ns = parser.parse_args(argv, namespace=_GenArgs())
        return GenOptions(
            config_path=gen_ns.config,
            out=gen_ns.out,
        )

    if namespace.subcommand == "inspect":
        inspect_ns = parser.parse_args(argv, namespace=_InspectArgs())
        return InspectOptions(
            header_path=inspect_ns.header_path,
            clang_args=tuple(inspect_ns.clang_args),
            sample_size=inspect_ns.sample_size,
            render_out=inspect_ns.render_out,
            render_lib_id=inspect_ns.render_lib_id,
            render_pkg=inspect_ns.render_pkg,
            render_emit=inspect_ns.render_emit,
            func_filter=inspect_ns.func_filter,
            type_filter=inspect_ns.type_filter,
            const_filter=inspect_ns.const_filter,
            var_filter=inspect_ns.var_filter,
        )

    parser.print_help()
    raise SystemExit(2)


__all__ = ["GenOptions", "InspectOptions", "parse_options"]
