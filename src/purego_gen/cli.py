# Copyright (c) 2026 purego-gen contributors.

"""CLI entrypoint for purego-gen."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_ALLOWED_EMIT_KINDS: Final[frozenset[str]] = frozenset({"func", "type", "const", "var"})
_GO_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def _parse_emit_kinds(value: str) -> tuple[str, ...]:
    """Parse and validate `--emit` values.

    Returns:
        Parsed emit kinds in user-provided order.

    Raises:
        argparse.ArgumentTypeError: The value is empty or contains unsupported categories.
    """
    parsed = tuple(part.strip() for part in value.split(",") if part.strip())
    if not parsed:
        message = "--emit must contain at least one category."
        raise argparse.ArgumentTypeError(message)

    invalid = [kind for kind in parsed if kind not in _ALLOWED_EMIT_KINDS]
    if invalid:
        message = (
            f"Unsupported emit category: {', '.join(invalid)}. "
            "Supported values: func,type,const,var."
        )
        raise argparse.ArgumentTypeError(message)

    return parsed


def _parse_package_name(value: str) -> str:
    """Validate Go package name syntax.

    Returns:
        The package name if valid.

    Raises:
        argparse.ArgumentTypeError: The package name does not match the allowed pattern.
    """
    if _GO_IDENTIFIER_PATTERN.fullmatch(value) is None:
        message = "Go package name must match ^[A-Za-z_][A-Za-z0-9_]*$."
        raise argparse.ArgumentTypeError(message)
    return value


def _normalize_lib_id(value: str) -> str:
    """Normalize `--lib-id` to safe snake_case.

    Returns:
        A snake_case-safe identifier.

    Raises:
        argparse.ArgumentTypeError: `value` has no alphanumeric characters.
    """
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    if not normalized:
        message = "--lib-id must contain at least one alphanumeric character."
        raise argparse.ArgumentTypeError(message)
    if normalized[0].isdigit():
        normalized = f"lib_{normalized}"
    return normalized


def _build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser.

    Returns:
        Configured parser for the single-command interface.
    """
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
        type=_parse_emit_kinds,
        help="Comma-separated categories to emit: func,type,const,var.",
    )
    parser.add_argument("--func-filter", help="Regex filter for function declarations.")
    parser.add_argument("--type-filter", help="Regex filter for type declarations.")
    parser.add_argument("--const-filter", help="Regex filter for constant declarations.")
    parser.add_argument("--var-filter", help="Regex filter for runtime variable declarations.")
    return parser


def _split_cli_and_clang_args(argv: list[str]) -> tuple[list[str], tuple[str, ...]]:
    """Split generator args from clang args using `--` separator.

    Returns:
        Tuple of purego-gen arguments and clang passthrough arguments.
    """
    if "--" not in argv:
        return list(argv), ()

    separator_index = argv.index("--")
    cli_argv = list(argv[:separator_index])
    clang_argv = tuple(argv[separator_index + 1 :])
    return cli_argv, clang_argv


def parse_options(argv: list[str]) -> CliOptions:
    """Parse CLI arguments into validated options.

    Returns:
        Parsed and validated CLI options.
    """
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
    )


def _render_stub(options: CliOptions) -> str:
    """Render a deterministic stub output for the current milestone.

    Returns:
        Generated Go source code.
    """
    lines: list[str] = [
        "// Code generated by purego-gen; DO NOT EDIT.",
        "",
        f"package {options.package}",
        "",
    ]

    if "func" in options.emit_kinds:
        lines.extend([
            f"func purego_{options.lib_id}_register_functions(handle uintptr) error {{",
            "\t_ = handle",
            "\treturn nil",
            "}",
            "",
        ])

    if "var" in options.emit_kinds:
        lines.extend([
            f"func purego_{options.lib_id}_load_runtime_vars(handle uintptr) error {{",
            "\t_ = handle",
            "\treturn nil",
            "}",
            "",
        ])

    return "\n".join(lines)


def _write_output(rendered: str, out_path: str) -> None:
    """Write generated code to stdout or to a target file."""
    if out_path == "-":
        sys.stdout.write(rendered)
        return
    Path(out_path).write_text(rendered, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entrypoint.

    Returns:
        Process-like exit code.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    try:
        options = parse_options(args)
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        if error.code is None:
            return 0
        return 1

    rendered = _render_stub(options)
    try:
        _write_output(rendered, options.out)
    except OSError as error:
        sys.stderr.write(f"purego-gen: failed to write output: {error}\n")
        return 1

    sys.stderr.write(
        "purego-gen: generated placeholder bindings; parser and emitter are not implemented yet.\n"
    )
    return 0
