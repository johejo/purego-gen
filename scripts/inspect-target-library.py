# Copyright (c) 2026 purego-gen contributors.

"""Inspect target-library parsing coverage using pkg-config + libclang."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from purego_gen.clang_parser import parse_declarations
from purego_gen.declaration_filters import (
    CompiledDeclarationFilters,
    apply_declaration_filters,
    compile_filter,
)
from purego_gen.emit_kinds import parse_emit_kinds
from purego_gen.identifier_utils import normalize_lib_id
from purego_gen.pkg_config import run_pkg_config_stdout, run_pkg_config_tokens
from purego_gen.renderer import render_go_source

if TYPE_CHECKING:
    from purego_gen.model import ParsedDeclarations

_DEFAULT_SAMPLE_SIZE = 12
_DEFAULT_EMIT_KINDS = "func,type,const,var"


@dataclass(frozen=True, slots=True)
class _ResolvedTarget:
    """Resolved target header and clang flags."""

    package_name: str
    header_path: Path
    cflags: tuple[str, ...]


class _ParsedArgs(argparse.Namespace):
    """Typed argparse namespace for this script."""

    pkg_config_package: str
    header: str
    sample_size: int
    render_out: str | None
    render_lib_id: str | None
    render_pkg: str
    render_emit: str
    func_filter: str | None
    type_filter: str | None
    const_filter: str | None
    var_filter: str | None


def _write_line(message: str = "") -> None:
    """Write one line to stdout."""
    sys.stdout.write(f"{message}\n")


def _filter_declarations(
    declarations: ParsedDeclarations,
    *,
    filters: CompiledDeclarationFilters,
) -> ParsedDeclarations:
    """Filter declarations by optional category regex patterns.

    Returns:
        Filtered declarations.
    """
    return apply_declaration_filters(declarations, filters=filters)


def _default_lib_id(package_name: str) -> str:
    """Derive a default lib id from pkg-config package name.

    Returns:
        Normalized lib id.
    """
    try:
        return normalize_lib_id(package_name.removeprefix("lib"))
    except ValueError:
        return "bindings"


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the inspection script.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Inspect parser coverage and optionally render generated Go source.",
    )
    parser.add_argument("--pkg-config-package", required=True, help="pkg-config package name.")
    parser.add_argument("--header", required=True, help="Header file name, e.g. zstd.h.")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=_DEFAULT_SAMPLE_SIZE,
        help=f"How many functions/skipped typedefs to sample (default: {_DEFAULT_SAMPLE_SIZE}).",
    )
    parser.add_argument(
        "--render-out",
        help="Write rendered Go output to path (optional).",
    )
    parser.add_argument(
        "--render-lib-id",
        help="Library id used when rendering (defaults to package-derived value).",
    )
    parser.add_argument(
        "--render-pkg",
        default="bindings",
        help="Go package name used when rendering (default: bindings).",
    )
    parser.add_argument(
        "--render-emit",
        default=_DEFAULT_EMIT_KINDS,
        help=f"Comma-separated emit categories for render mode (default: {_DEFAULT_EMIT_KINDS}).",
    )
    parser.add_argument("--func-filter", help="Optional regex filter for function names.")
    parser.add_argument("--type-filter", help="Optional regex filter for type names.")
    parser.add_argument("--const-filter", help="Optional regex filter for constant names.")
    parser.add_argument("--var-filter", help="Optional regex filter for runtime variable names.")
    return parser


def _render_output(
    declarations: ParsedDeclarations,
    *,
    out_path: Path,
    lib_id: str,
    package: str,
    emit_kinds: tuple[str, ...],
) -> None:
    """Render Go output and write it to file."""
    source = render_go_source(
        package=package,
        lib_id=lib_id,
        emit_kinds=emit_kinds,
        declarations=declarations,
    )
    out_path.write_text(source, encoding="utf-8")


def _resolve_target(package_name: str, header_name: str) -> _ResolvedTarget:
    """Resolve header path and clang flags from pkg-config.

    Returns:
        Resolved target metadata.

    Raises:
        RuntimeError: Header cannot be resolved from pkg-config.
    """
    cflags = run_pkg_config_tokens(package_name, "--cflags")
    include_dir = Path(run_pkg_config_stdout(package_name, "--variable=includedir")).expanduser()
    header_path = (include_dir / header_name).resolve()
    if not header_path.is_file():
        message = f"header not found from pkg-config includedir: {header_path}"
        raise RuntimeError(message)
    return _ResolvedTarget(package_name=package_name, header_path=header_path, cflags=cflags)


def _report_declarations(
    target: _ResolvedTarget,
    declarations: ParsedDeclarations,
    sample_size: int,
) -> None:
    """Write declaration summary report to stdout."""
    _write_line(f"package={target.package_name}")
    _write_line(f"header={target.header_path}")
    _write_line(f"clang_args={' '.join(target.cflags)}")
    _write_line(f"functions={len(declarations.functions)}")
    _write_line(f"typedefs={len(declarations.typedefs)}")
    _write_line(f"record_typedefs={len(declarations.record_typedefs)}")
    opaque_record_typedefs = tuple(
        record_typedef
        for record_typedef in declarations.record_typedefs
        if record_typedef.is_opaque
    )
    _write_line(f"opaque_record_typedefs={len(opaque_record_typedefs)}")
    _write_line(f"constants={len(declarations.constants)}")
    _write_line(f"runtime_vars={len(declarations.runtime_vars)}")
    _write_line(f"skipped_typedefs={len(declarations.skipped_typedefs)}")

    reason_counts = Counter(skipped.reason_code for skipped in declarations.skipped_typedefs)
    for reason_code, count in reason_counts.most_common():
        _write_line(f"skip_reason[{reason_code}]={count}")

    _write_line("sample_functions:")
    for function in declarations.functions[:sample_size]:
        params = ", ".join(function.parameter_c_types)
        _write_line(f"  {function.name}({params}) -> {function.result_c_type}")

    _write_line("sample_skipped_typedefs:")
    for skipped in declarations.skipped_typedefs[:sample_size]:
        _write_line(f"  {skipped.name}: {skipped.reason_code} :: {skipped.reason}")
    _write_line("sample_opaque_record_typedefs:")
    for record_typedef in opaque_record_typedefs[:sample_size]:
        _write_line(
            "  "
            f"{record_typedef.name}: {record_typedef.unsupported_code} :: "
            f"{record_typedef.unsupported_reason}"
        )


def _load_patterns(
    namespace: _ParsedArgs,
) -> CompiledDeclarationFilters:
    """Compile regex filters from parsed args.

    Returns:
        Compiled filter tuple in func/type/const/var order.
    """
    return CompiledDeclarationFilters(
        func=compile_filter(namespace.func_filter, option_name="--func-filter"),
        type_=compile_filter(namespace.type_filter, option_name="--type-filter"),
        const=compile_filter(namespace.const_filter, option_name="--const-filter"),
        var=compile_filter(namespace.var_filter, option_name="--var-filter"),
    )


def main(argv: list[str] | None = None) -> int:
    """Run the script.

    Returns:
        Process-like exit code.
    """
    parser = _build_arg_parser()
    namespace = parser.parse_args(argv, namespace=_ParsedArgs())

    if namespace.sample_size < 0:
        _write_line("sample-size must be >= 0.")
        return 1

    try:
        emit_kinds = parse_emit_kinds(namespace.render_emit, option_name="--render-emit")
        filters = _load_patterns(namespace)
        target = _resolve_target(str(namespace.pkg_config_package), str(namespace.header))
    except (RuntimeError, ValueError) as error:
        _write_line(str(error))
        return 1

    declarations = parse_declarations(headers=(str(target.header_path),), clang_args=target.cflags)
    filtered = _filter_declarations(declarations, filters=filters)
    _report_declarations(target, filtered, namespace.sample_size)

    render_out = namespace.render_out
    if render_out is not None:
        out_path = Path(render_out).expanduser().resolve()
        lib_id = namespace.render_lib_id or _default_lib_id(target.package_name)
        _render_output(
            filtered,
            out_path=out_path,
            lib_id=lib_id,
            package=namespace.render_pkg,
            emit_kinds=emit_kinds,
        )
        _write_line(f"rendered_go={out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
