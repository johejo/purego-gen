# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201, DOC501

"""CLI argument parsing and validated options for purego-gen."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from purego_gen.emit_kinds import parse_emit_kinds
from purego_gen.identifier_utils import is_go_identifier, normalize_lib_id
from purego_gen.model import TypeMappingOptions


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Validated CLI options."""

    lib_id: str
    headers: tuple[str, ...]
    package: str
    out: str
    emit_kinds: tuple[str, ...]
    func_filter: str | None
    type_filter: str | None
    const_filter: str | None
    var_filter: str | None
    clang_args: tuple[str, ...]
    type_mapping: TypeMappingOptions


class _ParsedArgs(argparse.Namespace):
    """Typed argparse namespace."""

    lib_id: str
    headers: list[str]
    pkg: str
    out: str
    emit: tuple[str, ...]
    func_filter: str | None
    type_filter: str | None
    const_filter: str | None
    var_filter: str | None
    const_char_as_string: bool
    strict_enum_typedefs: bool
    typed_sentinel_constants: bool


def _parse_emit_kinds_arg(value: str) -> tuple[str, ...]:
    """Parse and validate `--emit` argument for argparse."""
    try:
        return parse_emit_kinds(value, option_name="--emit")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _parse_package_name(value: str) -> str:
    """Validate Go package name syntax."""
    if not is_go_identifier(value):
        message = "Go package name must match ^[A-Za-z_][A-Za-z0-9_]*$."
        raise argparse.ArgumentTypeError(message)
    return value


def _normalize_lib_id(value: str) -> str:
    """Normalize `--lib-id` to safe snake_case."""
    try:
        return normalize_lib_id(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="purego-gen",
        description="Generate low-level Go bindings for ebitengine/purego.",
        allow_abbrev=False,
        epilog="Pass clang flags after `--`, e.g. purego-gen ... -- -I./include -D_GNU_SOURCE",
    )
    parser.add_argument(
        "--lib-id", required=True, type=_normalize_lib_id, help="Library identifier."
    )
    parser.add_argument(
        "--header",
        action="append",
        required=True,
        default=[],
        dest="headers",
        metavar="PATH",
        help="Input C header path. Repeat for multiple headers.",
    )
    parser.add_argument(
        "--pkg",
        default="bindings",
        type=_parse_package_name,
        help="Generated Go package name (default: bindings).",
    )
    parser.add_argument(
        "--out",
        default="-",
        metavar="PATH",
        help="Output file path. Use '-' (or omit) to write to stdout.",
    )
    parser.add_argument(
        "--emit",
        default="func,type,const,var",
        type=_parse_emit_kinds_arg,
        help="Comma-separated categories to emit: func,type,const,var.",
    )
    parser.add_argument("--func-filter", help="Regex filter for function declarations.")
    parser.add_argument("--type-filter", help="Regex filter for type declarations.")
    parser.add_argument("--const-filter", help="Regex filter for constant declarations.")
    parser.add_argument("--var-filter", help="Regex filter for runtime variable declarations.")
    parser.add_argument(
        "--const-char-as-string",
        action="store_true",
        help="Map const char* function signature slots to Go string (default: off).",
    )
    parser.add_argument(
        "--strict-enum-typedefs",
        action="store_true",
        help="Emit enum typedef aliases as strict Go types when possible (default: off).",
    )
    parser.add_argument(
        "--typed-sentinel-constants",
        action="store_true",
        help="Emit large sentinel-style constants as typed uint64 constants (default: off).",
    )
    return parser


def _split_cli_and_clang_args(argv: list[str]) -> tuple[list[str], tuple[str, ...]]:
    """Split generator args from clang args using `--` separator."""
    if "--" not in argv:
        return list(argv), ()
    separator_index = argv.index("--")
    return list(argv[:separator_index]), tuple(argv[separator_index + 1 :])


def parse_options(argv: list[str]) -> CliOptions:
    """Parse CLI arguments into validated options."""
    parser = _build_parser()
    cli_argv, clang_argv = _split_cli_and_clang_args(argv)
    namespace = parser.parse_args(cli_argv, namespace=_ParsedArgs())
    return CliOptions(
        lib_id=namespace.lib_id,
        headers=tuple(namespace.headers),
        package=namespace.pkg,
        out=namespace.out,
        emit_kinds=namespace.emit,
        func_filter=namespace.func_filter,
        type_filter=namespace.type_filter,
        const_filter=namespace.const_filter,
        var_filter=namespace.var_filter,
        clang_args=clang_argv,
        type_mapping=TypeMappingOptions(
            const_char_as_string=namespace.const_char_as_string,
            strict_enum_typedefs=namespace.strict_enum_typedefs,
            typed_sentinel_constants=namespace.typed_sentinel_constants,
        ),
    )
