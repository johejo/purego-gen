# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201, PLR0911

"""CLI entrypoint for purego-gen."""

from __future__ import annotations

import sys

from purego_gen.cli_args import CliOptions, parse_options
from purego_gen.diagnostics import emit_generation_diagnostics
from purego_gen.generation_pipeline import (
    ClangParserError,
    RendererError,
    parse_and_filter,
    render_formatted_go_source,
    write_output,
)


def _system_exit_to_code(error: SystemExit) -> int:
    """Convert `SystemExit` payload into process-style code."""
    if isinstance(error.code, int):
        return error.code
    if error.code is None:
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entrypoint."""
    args = list(argv) if argv is not None else sys.argv[1:]
    try:
        options = parse_options(args)
    except SystemExit as error:
        return _system_exit_to_code(error)

    try:
        declarations, filtered_declarations = parse_and_filter(options)
    except ClangParserError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1
    except ValueError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1

    emit_generation_diagnostics(
        stream=sys.stderr,
        all_declarations=declarations,
        filtered_declarations=filtered_declarations,
        emit_kinds=options.emit_kinds,
    )

    try:
        formatted = render_formatted_go_source(options, filtered_declarations)
    except RendererError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1
    except RuntimeError as error:
        sys.stderr.write(f"purego-gen: {error}\n")
        return 1

    try:
        write_output(formatted, options.out)
    except OSError as error:
        sys.stderr.write(f"purego-gen: failed to write output: {error}\n")
        return 1

    sys.stderr.write(
        "purego-gen: generated bindings from function declarations and basic typedefs.\n"
    )
    return 0


__all__ = ["CliOptions", "main", "parse_options"]
