# Copyright (c) 2026 purego-gen contributors.

"""CLI entrypoint for purego-gen."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from purego_gen.clang_parser import ClangParserError, parse_declarations
from purego_gen.model import ParsedDeclarations
from purego_gen.renderer import RendererError, render_go_source

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


def _compile_filter(pattern: str | None, option: str) -> re.Pattern[str] | None:
    """Compile one regex filter option.

    Returns:
        Compiled regex, or `None` when pattern is not provided.

    Raises:
        ValueError: Pattern has invalid syntax.
    """
    if pattern is None:
        return None
    try:
        return re.compile(pattern)
    except re.error as error:
        message = f"invalid {option} regex: {error}"
        raise ValueError(message) from error


def _apply_filters(options: CliOptions, declarations: ParsedDeclarations) -> ParsedDeclarations:
    """Apply category-specific declaration filters.

    Returns:
        Filtered declarations.

    Raises:
        ValueError: A provided category filter regex is invalid, or matches no
            declarations in an emitted category.
    """
    func_filter = _compile_filter(options.func_filter, "--func-filter")
    type_filter = _compile_filter(options.type_filter, "--type-filter")
    const_filter = _compile_filter(options.const_filter, "--const-filter")
    var_filter = _compile_filter(options.var_filter, "--var-filter")

    functions = declarations.functions
    if func_filter is not None:
        functions = tuple(function for function in functions if func_filter.search(function.name))

    typedefs = declarations.typedefs
    if type_filter is not None:
        typedefs = tuple(typedef for typedef in typedefs if type_filter.search(typedef.name))

    constants = declarations.constants
    if const_filter is not None:
        constants = tuple(constant for constant in constants if const_filter.search(constant.name))

    runtime_vars = declarations.runtime_vars
    if var_filter is not None:
        runtime_vars = tuple(
            runtime_var for runtime_var in runtime_vars if var_filter.search(runtime_var.name)
        )

    if options.func_filter is not None and "func" in options.emit_kinds and not functions:
        message = f"no declarations matched --func-filter: {options.func_filter}"
        raise ValueError(message)
    if options.type_filter is not None and "type" in options.emit_kinds and not typedefs:
        message = f"no declarations matched --type-filter: {options.type_filter}"
        raise ValueError(message)
    if options.const_filter is not None and "const" in options.emit_kinds and not constants:
        message = f"no declarations matched --const-filter: {options.const_filter}"
        raise ValueError(message)
    if options.var_filter is not None and "var" in options.emit_kinds and not runtime_vars:
        message = f"no declarations matched --var-filter: {options.var_filter}"
        raise ValueError(message)

    return ParsedDeclarations(
        functions=functions,
        typedefs=typedefs,
        constants=constants,
        runtime_vars=runtime_vars,
    )


def _write_output(rendered: str, out_path: str) -> None:
    """Write generated code to stdout or to a target file."""
    if out_path == "-":
        sys.stdout.write(rendered)
        return
    Path(out_path).write_text(rendered, encoding="utf-8")


def _format_go_source(source: str) -> str:
    """Format generated Go source code using `gofmt`.

    Returns:
        gofmt-formatted Go source.

    Raises:
        RuntimeError: gofmt is unavailable or formatting fails.
    """
    gofmt_path = shutil.which("gofmt")
    if gofmt_path is None:
        message = "gofmt is not available in PATH."
        raise RuntimeError(message)

    result = subprocess.run(  # noqa: S603
        [gofmt_path],
        capture_output=True,
        check=False,
        input=source,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "gofmt failed."
        message = f"failed to format generated code with gofmt: {detail}"
        raise RuntimeError(message)
    return result.stdout


def _system_exit_to_code(error: SystemExit) -> int:
    """Convert `SystemExit` payload into process-style code.

    Returns:
        Integer exit code.
    """
    if isinstance(error.code, int):
        return error.code
    if error.code is None:
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entrypoint.

    Returns:
        Process-like exit code.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    try:
        options = parse_options(args)
    except SystemExit as error:
        return _system_exit_to_code(error)

    try:
        declarations = parse_declarations(options.headers, options.clang_args)
        filtered_declarations = _apply_filters(options, declarations)
    except ClangParserError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1
    except ValueError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1

    try:
        rendered = render_go_source(
            package=options.package,
            lib_id=options.lib_id,
            emit_kinds=options.emit_kinds,
            declarations=filtered_declarations,
        )
    except RendererError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1

    try:
        formatted = _format_go_source(rendered)
        _write_output(formatted, options.out)
    except (RuntimeError, OSError) as error:
        if isinstance(error, OSError):
            sys.stderr.write(f"purego-gen: failed to write output: {error}\n")
        else:
            sys.stderr.write(f"purego-gen: {error}\n")
        return 1

    sys.stderr.write(
        "purego-gen: generated bindings from function declarations and basic typedefs.\n"
    )
    return 0
