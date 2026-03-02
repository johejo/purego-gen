# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201, DOC501, TC001

"""Generation pipeline helpers for CLI orchestration."""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404
import sys
from pathlib import Path

from purego_gen.clang_parser import ClangParserError, parse_declarations
from purego_gen.cli_args import CliOptions
from purego_gen.declaration_filters import (
    CompiledDeclarationFilters,
    apply_declaration_filters,
    compile_filter,
    validate_filter_match,
)
from purego_gen.model import ParsedDeclarations
from purego_gen.renderer import RendererError, render_go_source


def _compile_filters(options: CliOptions) -> CompiledDeclarationFilters:
    """Compile all regex filters from CLI options."""
    return CompiledDeclarationFilters(
        func=compile_filter(options.func_filter, option_name="--func-filter"),
        type_=compile_filter(options.type_filter, option_name="--type-filter"),
        const=compile_filter(options.const_filter, option_name="--const-filter"),
        var=compile_filter(options.var_filter, option_name="--var-filter"),
    )


def apply_cli_filters(options: CliOptions, declarations: ParsedDeclarations) -> ParsedDeclarations:
    """Apply CLI category-specific declaration filters with match validation."""
    filtered = apply_declaration_filters(declarations, filters=_compile_filters(options))
    validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.func_filter,
        option_name="--func-filter",
        emit_kind="func",
        has_match=bool(filtered.functions),
    )
    validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.type_filter,
        option_name="--type-filter",
        emit_kind="type",
        has_match=bool(filtered.typedefs),
    )
    validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.const_filter,
        option_name="--const-filter",
        emit_kind="const",
        has_match=bool(filtered.constants),
    )
    validate_filter_match(
        emit_kinds=options.emit_kinds,
        option_value=options.var_filter,
        option_name="--var-filter",
        emit_kind="var",
        has_match=bool(filtered.runtime_vars),
    )
    return filtered


def parse_and_filter(options: CliOptions) -> tuple[ParsedDeclarations, ParsedDeclarations]:
    """Parse declarations then apply CLI filters."""
    declarations = parse_declarations(
        options.headers,
        options.clang_args,
        type_mapping=options.type_mapping,
    )
    return declarations, apply_cli_filters(options, declarations)


def render_formatted_go_source(options: CliOptions, declarations: ParsedDeclarations) -> str:
    """Render Go source and format via gofmt."""
    rendered = render_go_source(
        package=options.package,
        lib_id=options.lib_id,
        emit_kinds=options.emit_kinds,
        declarations=declarations,
        type_mapping=options.type_mapping,
    )
    return format_go_source(rendered)


def format_go_source(source: str) -> str:
    """Format generated Go source code using `gofmt`."""
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


def write_output(rendered: str, out_path: str) -> None:
    """Write generated code to stdout or to a target file."""
    if out_path == "-":
        sys.stdout.write(rendered)
        return
    Path(out_path).write_text(rendered, encoding="utf-8")


__all__ = [
    "ClangParserError",
    "RendererError",
    "apply_cli_filters",
    "parse_and_filter",
    "render_formatted_go_source",
    "write_output",
]
