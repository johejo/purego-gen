# Copyright (c) 2026 purego-gen contributors.

"""Generation pipeline helpers for CLI orchestration."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from purego_gen.clang_parser import ClangParserError, parse_declarations
from purego_gen.declaration_filters import (
    CompiledDeclarationFilters,
    apply_declaration_filters,
    compile_filter_spec,
    validate_filter_match,
)
from purego_gen.process_exec import run_command
from purego_gen.renderer import RendererError, render_go_source

if TYPE_CHECKING:
    from purego_gen.generator_config import GeneratorConfig
    from purego_gen.model import ParsedDeclarations


def _compile_filters(config: GeneratorConfig) -> CompiledDeclarationFilters:
    """Compile all configured filters into regex patterns.

    Returns:
        Compiled per-category regex filters.
    """
    return CompiledDeclarationFilters(
        func=compile_filter_spec(config.parse.func_filter, option_name="--func-filter"),
        type_=compile_filter_spec(config.parse.type_filter, option_name="--type-filter"),
        const=compile_filter_spec(config.parse.const_filter, option_name="--const-filter"),
        var=compile_filter_spec(config.parse.var_filter, option_name="--var-filter"),
        func_exclude=compile_filter_spec(
            config.parse.func_exclude_filter,
            option_name="--func-exclude-filter",
        ),
        type_exclude=compile_filter_spec(
            config.parse.type_exclude_filter,
            option_name="--type-exclude-filter",
        ),
        const_exclude=compile_filter_spec(
            config.parse.const_exclude_filter,
            option_name="--const-exclude-filter",
        ),
        var_exclude=compile_filter_spec(
            config.parse.var_exclude_filter,
            option_name="--var-exclude-filter",
        ),
    )


def apply_cli_filters(
    config: GeneratorConfig,
    declarations: ParsedDeclarations,
) -> ParsedDeclarations:
    """Apply CLI category-specific declaration filters with match validation.

    Returns:
        Filtered declarations that satisfy configured CLI filters.
    """
    filtered = apply_declaration_filters(declarations, filters=_compile_filters(config))
    validate_filter_match(
        emit_kinds=config.emit_kinds,
        option_value=config.parse.func_filter,
        option_name="--func-filter",
        emit_kind="func",
        has_match=bool(filtered.functions),
    )
    validate_filter_match(
        emit_kinds=config.emit_kinds,
        option_value=config.parse.type_filter,
        option_name="--type-filter",
        emit_kind="type",
        has_match=bool(filtered.typedefs),
    )
    validate_filter_match(
        emit_kinds=config.emit_kinds,
        option_value=config.parse.const_filter,
        option_name="--const-filter",
        emit_kind="const",
        has_match=bool(filtered.constants),
    )
    validate_filter_match(
        emit_kinds=config.emit_kinds,
        option_value=config.parse.var_filter,
        option_name="--var-filter",
        emit_kind="var",
        has_match=bool(filtered.runtime_vars),
    )
    return filtered


def parse_and_filter(config: GeneratorConfig) -> tuple[ParsedDeclarations, ParsedDeclarations]:
    """Parse declarations then apply CLI filters.

    Returns:
        Pair of all parsed declarations and filtered declarations.
    """
    declarations = parse_declarations(
        config.parse.headers,
        config.parse.clang_args,
        unsaved_files=tuple((overlay.path, overlay.content) for overlay in config.parse.overlays),
        type_mapping=config.render.type_mapping,
    )
    return declarations, apply_cli_filters(config, declarations)


def render_formatted_go_source(
    config: GeneratorConfig,
    declarations: ParsedDeclarations,
    *,
    skip_gofmt: bool = False,
) -> str:
    """Render Go source and optionally format via gofmt.

    Returns:
        Rendered (and optionally gofmt-formatted) Go source text.
    """
    rendered = render_go_source(
        package=config.package,
        lib_id=config.lib_id,
        emit_kinds=config.emit_kinds,
        declarations=declarations,
        render=config.render,
    )
    if skip_gofmt:
        return rendered
    return format_go_source(rendered)


def format_go_source(source: str) -> str:
    """Format generated Go source code using `gofmt`.

    Returns:
        Formatted Go source text.

    Raises:
        RuntimeError: `gofmt` is unavailable or formatting fails.
    """
    gofmt_path = shutil.which("gofmt")
    if gofmt_path is None:
        message = "gofmt is not available in PATH."
        raise RuntimeError(message)

    result = run_command(
        [gofmt_path],
        stdin_text=source,
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
