# Copyright (c) 2026 purego-gen contributors.

"""Inspect parser coverage for one header using explicit header/clang inputs."""

from __future__ import annotations

import json
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
from purego_gen.helper_rendering import (
    detect_callback_registration_patterns,
    find_callback_candidates,
)
from purego_gen.renderer import render_go_source

if TYPE_CHECKING:
    from purego_gen.cli_args import InspectOptions
    from purego_gen.model import ParsedDeclarations


@dataclass(frozen=True, slots=True)
class _ResolvedTarget:
    """Resolved target header and clang flags."""

    header_path: Path
    clang_args: tuple[str, ...]


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


def _default_lib_id() -> str:
    """Return fallback lib id for optional render mode.

    Returns:
        Fallback lib id.
    """
    return "bindings"


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


def _resolve_target(header_path: str, *, clang_args: tuple[str, ...]) -> _ResolvedTarget:
    """Resolve header path and clang flags from explicit inputs.

    Returns:
        Resolved target metadata.

    Raises:
        RuntimeError: Header path is invalid.
    """
    resolved_header_path = Path(header_path).expanduser().resolve()
    if not resolved_header_path.is_file():
        message = f"header path does not exist: {resolved_header_path}"
        raise RuntimeError(message)
    return _ResolvedTarget(header_path=resolved_header_path, clang_args=clang_args)


def _report_declarations(
    target: _ResolvedTarget,
    declarations: ParsedDeclarations,
    sample_size: int,
) -> None:
    """Write declaration summary report to stdout."""
    _write_line("package=manual")
    _write_line(f"header={target.header_path}")
    _write_line(f"clang_args={' '.join(target.clang_args)}")
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

    callback_candidates = find_callback_candidates(declarations)
    _write_line(f"callback_candidates={len(callback_candidates)}")
    _write_line("sample_callback_candidates:")
    for func_name, matching_params in callback_candidates[:sample_size]:
        params_str = ", ".join(f"{name}({c_type})" for name, c_type in matching_params)
        _write_line(f"  {func_name}: {params_str}")

    registration_patterns = detect_callback_registration_patterns(declarations)
    _write_line(f"callback_registration_patterns={len(registration_patterns)}")
    _write_line("sample_callback_registration_patterns:")
    for pattern in registration_patterns[:sample_size]:
        parts = [f"callback={pattern.callback_param}"]
        if pattern.userdata_param:
            parts.append(f"userdata={pattern.userdata_param}")
        if pattern.destructor_param:
            parts.append(f"destructor={pattern.destructor_param}")
        _write_line(f"  {pattern.function}: {', '.join(parts)}")


def _emit_callback_config(declarations: ParsedDeclarations) -> None:
    """Emit a callback_inputs config snippet as JSON to stdout."""
    candidates = find_callback_candidates(declarations)
    if not candidates:
        _write_line("callback_inputs: (none)")
        return
    callback_inputs = [
        {"function": func_name, "parameters": [name for name, _ in params]}
        for func_name, params in candidates
    ]
    _write_line("callback_inputs:")
    _write_line(json.dumps(callback_inputs, indent=2))


def _load_patterns(
    options: InspectOptions,
) -> CompiledDeclarationFilters:
    """Compile regex filters from parsed options.

    Returns:
        Compiled filter tuple in func/type/const/var order.
    """
    return CompiledDeclarationFilters(
        func=compile_filter(options.func_filter, option_name="--func-filter"),
        type_=compile_filter(options.type_filter, option_name="--type-filter"),
        const=compile_filter(options.const_filter, option_name="--const-filter"),
        var=compile_filter(options.var_filter, option_name="--var-filter"),
        func_exclude=compile_filter(options.func_exclude, option_name="--func-exclude"),
        type_exclude=compile_filter(options.type_exclude, option_name="--type-exclude"),
        const_exclude=compile_filter(options.const_exclude, option_name="--const-exclude"),
        var_exclude=compile_filter(options.var_exclude, option_name="--var-exclude"),
    )


def _list_declaration_names(
    declarations: ParsedDeclarations,
    emit_kinds: tuple[str, ...],
) -> None:
    """Write sorted declaration names by category to stdout."""
    kind_entries: list[tuple[str, list[str]]] = []
    if "func" in emit_kinds:
        kind_entries.append(("functions", sorted(f.name for f in declarations.functions)))
    if "type" in emit_kinds:
        names = sorted(
            {td.name for td in declarations.typedefs}
            | {rt.name for rt in declarations.record_typedefs}
        )
        kind_entries.append(("types", names))
    if "const" in emit_kinds:
        kind_entries.append(("constants", sorted(c.name for c in declarations.constants)))
    if "var" in emit_kinds:
        kind_entries.append(("variables", sorted(v.name for v in declarations.runtime_vars)))
    for label, names in kind_entries:
        _write_line(f"{label}:")
        for name in names:
            _write_line(f"  {name}")


def run_inspect(options: InspectOptions) -> int:
    """Run the inspect subcommand.

    Returns:
        Process-like exit code.
    """
    if options.sample_size < 0:
        _write_line("sample-size must be >= 0.")
        return 1

    try:
        emit_kinds = parse_emit_kinds(options.render_emit, option_name="--render-emit")
        filters = _load_patterns(options)
        target = _resolve_target(
            options.header_path,
            clang_args=options.clang_args,
        )
    except (RuntimeError, ValueError) as error:
        _write_line(str(error))
        return 1

    declarations = parse_declarations(
        headers=(str(target.header_path),),
        clang_args=target.clang_args,
    )
    filtered = _filter_declarations(declarations, filters=filters)
    _report_declarations(target, filtered, options.sample_size)

    if options.list_names:
        _list_declaration_names(filtered, emit_kinds)

    if options.emit_callback_config:
        _emit_callback_config(filtered)

    render_out = options.render_out
    if render_out is not None:
        out_path = Path(render_out).expanduser().resolve()
        lib_id = options.render_lib_id or _default_lib_id()
        _render_output(
            filtered,
            out_path=out_path,
            lib_id=lib_id,
            package=options.render_pkg,
            emit_kinds=emit_kinds,
        )
        _write_line(f"rendered_go={out_path}")

    return 0


__all__ = ["run_inspect"]
