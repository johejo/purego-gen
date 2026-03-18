# Copyright (c) 2026 purego-gen contributors.

"""libclang-backed declaration parser."""

from __future__ import annotations

from pathlib import Path

from purego_gen.clang_collect import parse_header
from purego_gen.clang_runtime import (
    ClangParserError,
    build_macro_cursor_predicates,
    configure_libclang,
    load_cindex,
)
from purego_gen.clang_types import (
    CollectedDeclarations,
    ParseContext,
    SeenDeclarations,
    UnsavedFile,
)
from purego_gen.model import ParsedDeclarations, TypeMappingOptions


def parse_declarations(
    headers: tuple[str, ...],
    clang_args: tuple[str, ...],
    *,
    unsaved_files: tuple[UnsavedFile, ...] = (),
    type_mapping: TypeMappingOptions | None = None,
) -> ParsedDeclarations:
    """Parse declaration categories from headers via libclang.

    Returns:
        Parsed declarations in stable order.

    Raises:
        ClangParserError: libclang is unavailable or parsing fails.
    """
    resolved_type_mapping = type_mapping if type_mapping is not None else TypeMappingOptions()

    cindex = load_cindex()
    configure_libclang(cindex)

    try:
        index = cindex.Index.create()
    except cindex.LibclangError as error:
        message = (
            "failed to load libclang. Set `LIBCLANG_PATH` to the directory containing libclang."
        )
        raise ClangParserError(message) from error
    parse_context = ParseContext(
        cindex=cindex,
        index=index,
        clang_args=clang_args,
        macro_cursor_predicates=build_macro_cursor_predicates(cindex),
        type_mapping=resolved_type_mapping,
        unsaved_files=unsaved_files,
    )

    all_declarations = CollectedDeclarations(
        functions=[],
        typedefs=[],
        constants=[],
        runtime_vars=[],
        skipped_typedefs=[],
        record_typedefs=[],
    )
    seen = SeenDeclarations(
        function_names=set(),
        typedef_names=set(),
        constant_names=set(),
        runtime_var_names=set(),
    )

    unsaved_paths = {path for path, _ in unsaved_files}
    for header in headers:
        header_path = Path(header).resolve()
        if not header_path.exists() and str(header_path) not in unsaved_paths:
            message = f"header not found: {header_path}"
            raise ClangParserError(message)

        (
            parsed_functions,
            parsed_typedefs,
            parsed_constants,
            parsed_runtime_vars,
            parsed_skipped_typedefs,
            parsed_record_typedefs,
        ) = parse_header(
            parse_context=parse_context,
            header_path=header_path,
            seen=seen,
        )
        all_declarations.functions.extend(parsed_functions)
        all_declarations.typedefs.extend(parsed_typedefs)
        all_declarations.constants.extend(parsed_constants)
        all_declarations.runtime_vars.extend(parsed_runtime_vars)
        all_declarations.skipped_typedefs.extend(parsed_skipped_typedefs)
        all_declarations.record_typedefs.extend(parsed_record_typedefs)

    return ParsedDeclarations(
        functions=tuple(all_declarations.functions),
        typedefs=tuple(all_declarations.typedefs),
        constants=tuple(all_declarations.constants),
        runtime_vars=tuple(all_declarations.runtime_vars),
        skipped_typedefs=tuple(all_declarations.skipped_typedefs),
        record_typedefs=tuple(all_declarations.record_typedefs),
    )


__all__ = ["ClangParserError", "parse_declarations"]
