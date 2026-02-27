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
from purego_gen.model import ParsedDeclarations, TypeMappingOptions
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
    strict_opaque_handles: bool
    strict_enum_typedefs: bool
    typed_sentinel_constants: bool


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
    parser.add_argument(
        "--const-char-as-string",
        action="store_true",
        help="Map const char* function signature slots to Go string (default: off).",
    )
    parser.add_argument(
        "--strict-opaque-handles",
        action="store_true",
        help="Emit opaque struct handle typedefs as strict Go types (default: off).",
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
        type_mapping=TypeMappingOptions(
            const_char_as_string=namespace.const_char_as_string,
            strict_opaque_handles=namespace.strict_opaque_handles,
            strict_enum_typedefs=namespace.strict_enum_typedefs,
            typed_sentinel_constants=namespace.typed_sentinel_constants,
        ),
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


@dataclass(frozen=True, slots=True)
class _CompiledFilters:
    """Compiled regex filters resolved from CLI options."""

    func: re.Pattern[str] | None
    type_: re.Pattern[str] | None
    const: re.Pattern[str] | None
    var: re.Pattern[str] | None


def _compile_filters(options: CliOptions) -> _CompiledFilters:
    """Compile all regex filters from CLI options.

    Returns:
        Compiled filter bundle used by declaration filtering.
    """
    return _CompiledFilters(
        func=_compile_filter(options.func_filter, "--func-filter"),
        type_=_compile_filter(options.type_filter, "--type-filter"),
        const=_compile_filter(options.const_filter, "--const-filter"),
        var=_compile_filter(options.var_filter, "--var-filter"),
    )


def _validate_filter_match(
    *,
    emit_kinds: tuple[str, ...],
    option_value: str | None,
    option_name: str,
    emit_kind: str,
    has_match: bool,
) -> None:
    """Validate that a configured filter matches at least one emitted declaration.

    Raises:
        ValueError: The configured filter matched no declarations for an emitted category.
    """
    if option_value is None or emit_kind not in emit_kinds or has_match:
        return
    message = f"no declarations matched {option_name}: {option_value}"
    raise ValueError(message)


def _apply_filters(options: CliOptions, declarations: ParsedDeclarations) -> ParsedDeclarations:
    """Apply category-specific declaration filters.

    Returns:
        Filtered declarations.

    """
    compiled_filters = _compile_filters(options)

    functions = declarations.functions
    if compiled_filters.func is not None:
        functions = tuple(
            function for function in functions if compiled_filters.func.search(function.name)
        )

    typedefs = declarations.typedefs
    if compiled_filters.type_ is not None:
        typedefs = tuple(
            typedef for typedef in typedefs if compiled_filters.type_.search(typedef.name)
        )
    record_typedefs = declarations.record_typedefs
    if compiled_filters.type_ is not None:
        record_typedefs = tuple(
            record_typedef
            for record_typedef in record_typedefs
            if compiled_filters.type_.search(record_typedef.name)
        )

    constants = declarations.constants
    if compiled_filters.const is not None:
        constants = tuple(
            constant for constant in constants if compiled_filters.const.search(constant.name)
        )

    runtime_vars = declarations.runtime_vars
    if compiled_filters.var is not None:
        runtime_vars = tuple(
            runtime_var
            for runtime_var in runtime_vars
            if compiled_filters.var.search(runtime_var.name)
        )

    _validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.func_filter,
        option_name="--func-filter",
        emit_kind="func",
        has_match=bool(functions),
    )
    _validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.type_filter,
        option_name="--type-filter",
        emit_kind="type",
        has_match=bool(typedefs),
    )
    _validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.const_filter,
        option_name="--const-filter",
        emit_kind="const",
        has_match=bool(constants),
    )
    _validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.var_filter,
        option_name="--var-filter",
        emit_kind="var",
        has_match=bool(runtime_vars),
    )

    return ParsedDeclarations(
        functions=functions,
        typedefs=typedefs,
        constants=constants,
        runtime_vars=runtime_vars,
        skipped_typedefs=declarations.skipped_typedefs,
        record_typedefs=record_typedefs,
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
        declarations = parse_declarations(
            options.headers,
            options.clang_args,
            type_mapping=options.type_mapping,
        )
        filtered_declarations = _apply_filters(options, declarations)
    except ClangParserError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1
    except ValueError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1

    for skipped_typedef in declarations.skipped_typedefs:
        sys.stderr.write(
            "purego-gen: skipped typedef "
            f"{skipped_typedef.name} ({skipped_typedef.c_type}) "
            f"[{skipped_typedef.reason_code}]: {skipped_typedef.reason}\n"
        )

    try:
        rendered = render_go_source(
            package=options.package,
            lib_id=options.lib_id,
            emit_kinds=options.emit_kinds,
            declarations=filtered_declarations,
            type_mapping=options.type_mapping,
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
