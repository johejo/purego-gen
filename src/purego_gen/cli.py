# Copyright (c) 2026 purego-gen contributors.

"""CLI entrypoint for purego-gen."""

from __future__ import annotations

import sys
from pathlib import Path

from purego_gen.cli_args import CliOptions, parse_options
from purego_gen.config import load_app_config, resolve_generator_config
from purego_gen.diagnostics import emit_generation_diagnostics
from purego_gen.generation_pipeline import (
    ClangParserError,
    RendererError,
    parse_and_filter,
    render_formatted_go_source,
    write_output,
)


def _system_exit_to_code(error: SystemExit) -> int:
    """Convert `SystemExit` payload into process-style code.

    Returns:
        Process-style exit code derived from `SystemExit`.
    """
    if isinstance(error.code, int):
        return error.code
    if error.code is None:
        return 0
    return 1


def _fail(message: str) -> int:
    """Write one prefixed error message and return failure code.

    Returns:
        Process-style failure code.
    """
    sys.stderr.write(f"purego-gen: {message}\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entrypoint.

    Returns:
        Process-style exit code.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    try:
        options = parse_options(args)
    except SystemExit as error:
        return _system_exit_to_code(error)

    try:
        app_config = load_app_config(Path(options.config_path))
        generator_config = resolve_generator_config(app_config.generator)
    except RuntimeError as error:
        return _fail(str(error))

    try:
        declarations, filtered_declarations = parse_and_filter(generator_config)
    except (ClangParserError, ValueError) as error:
        return _fail(str(error))

    emit_generation_diagnostics(
        stream=sys.stderr,
        all_declarations=declarations,
        filtered_declarations=filtered_declarations,
        emit_kinds=generator_config.emit_kinds,
    )

    try:
        formatted = render_formatted_go_source(generator_config, filtered_declarations)
    except (RendererError, RuntimeError) as error:
        return _fail(str(error))

    try:
        write_output(formatted, options.out)
    except OSError as error:
        return _fail(f"failed to write output: {error}")

    sys.stderr.write(
        "purego-gen: generated bindings from function declarations and basic typedefs.\n"
    )
    return 0


__all__ = ["CliOptions", "main", "parse_options"]
