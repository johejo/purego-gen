# Copyright (c) 2026 purego-gen contributors.

"""Translation-unit walking and declaration collection helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from purego_gen.clang_extractor import (
    collect_constant,
    collect_function,
    collect_macro_constant,
    collect_runtime_var,
    collect_typedef,
)
from purego_gen.clang_runtime import ClangParserError
from purego_gen.clang_types import (
    CollectedDeclarations,
    CursorLike,
    MacroCollectionState,
    ParseContext,
    SeenDeclarations,
    TranslationUnitLike,
)

if TYPE_CHECKING:
    from purego_gen.model import (
        ConstantDecl,
        FunctionDecl,
        RecordTypedefDecl,
        RuntimeVarDecl,
        SkippedTypedefDecl,
        TypedefDecl,
    )

_SEVERITY_ERROR: Final[int] = 3


def _collect_diagnostics(
    translation_unit: TranslationUnitLike,
    header_path: Path,
) -> tuple[str, ...]:
    """Collect error-level diagnostics.

    Returns:
        Tuple of diagnostic lines, empty when no error-level diagnostics exist.
    """
    diagnostics: list[str] = []
    for diagnostic in translation_unit.diagnostics:
        if diagnostic.severity < _SEVERITY_ERROR:
            continue
        location = diagnostic.location
        file_name = "<unknown>"
        if location.file is not None:
            file_name = location.file.name
        diagnostics.append(f"{file_name}:{location.line}:{location.column}: {diagnostic.spelling}")
    if not diagnostics:
        return ()
    return (f"failed to parse {header_path}:", *diagnostics)


def _walk_preorder(cursor: CursorLike) -> tuple[CursorLike, ...]:
    """Collect all cursor nodes in preorder.

    Returns:
        Preorder cursor tuple rooted at `cursor`.
    """
    nodes: list[CursorLike] = [cursor]
    for child in cursor.get_children():
        nodes.extend(_walk_preorder(child))
    return tuple(nodes)


def _is_cursor_from_header(cursor: CursorLike, header_path: Path) -> bool:
    """Check if cursor originates from target header.

    Returns:
        `True` when cursor source file exactly matches `header_path`.
    """
    location = cursor.location
    if location.file is None:
        return False
    return Path(location.file.name).resolve() == header_path


def _parse_translation_unit(
    parse_context: ParseContext,
    header_path: Path,
) -> TranslationUnitLike:
    """Create translation unit for one header.

    Returns:
        Parsed translation unit.

    Raises:
        ClangParserError: libclang fails to load translation unit.
    """
    cindex = parse_context.cindex
    parse_options = int(cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)
    detailed_preprocessing_record = getattr(
        cindex.TranslationUnit,
        "PARSE_DETAILED_PROCESSING_RECORD",
        0,
    )
    parse_options |= int(detailed_preprocessing_record)
    try:
        return parse_context.index.parse(
            path=str(header_path),
            args=list(parse_context.clang_args),
            unsaved_files=list(parse_context.unsaved_files) or None,
            options=parse_options,
        )
    except cindex.TranslationUnitLoadError as error:
        message = f"failed to load translation unit for {header_path}"
        raise ClangParserError(message) from error


def parse_header(
    parse_context: ParseContext,
    header_path: Path,
    seen: SeenDeclarations,
) -> tuple[
    list[FunctionDecl],
    list[TypedefDecl],
    list[ConstantDecl],
    list[RuntimeVarDecl],
    list[SkippedTypedefDecl],
    list[RecordTypedefDecl],
    set[str],
]:
    """Parse one header and extract supported declarations.

    Returns:
        Declaration lists grouped by category.

    Raises:
        ClangParserError: Translation unit parsing or diagnostics fail.
    """
    cindex = parse_context.cindex
    translation_unit = _parse_translation_unit(parse_context, header_path)
    diagnostic_messages = _collect_diagnostics(translation_unit, header_path)
    if diagnostic_messages:
        raise ClangParserError("\n".join(diagnostic_messages))

    root_cursor = translation_unit.cursor
    if root_cursor is None:
        return [], [], [], [], [], [], set()

    declarations = CollectedDeclarations(
        functions=[],
        typedefs=[],
        constants=[],
        runtime_vars=[],
        skipped_typedefs=[],
        record_typedefs=[],
        opaque_pointer_typedef_names=set(),
    )
    macro_state = MacroCollectionState(
        known_constant_values={},
        cursor_predicates=parse_context.macro_cursor_predicates,
    )
    macro_definition_kind = cast(
        "object | None",
        getattr(cindex.CursorKind, "MACRO_DEFINITION", None),
    )
    for cursor in _walk_preorder(root_cursor):
        if not _is_cursor_from_header(cursor, header_path):
            continue

        if collect_function(
            cursor,
            cindex.CursorKind.FUNCTION_DECL,
            seen,
            declarations.functions,
            type_mapping=parse_context.type_mapping,
        ):
            continue
        if collect_typedef(
            cursor,
            cindex.CursorKind.TYPEDEF_DECL,
            seen,
            declarations,
        ):
            continue
        if collect_constant(
            cursor,
            cindex.CursorKind.ENUM_CONSTANT_DECL,
            seen,
            declarations.constants,
        ):
            macro_state.known_constant_values[str(cursor.spelling)] = int(cursor.enum_value)
            continue
        if macro_definition_kind is not None and collect_macro_constant(
            cursor,
            macro_definition_kind,
            seen,
            declarations.constants,
            macro_state,
        ):
            continue
        if collect_runtime_var(
            cursor,
            cindex.CursorKind.VAR_DECL,
            seen,
            declarations.runtime_vars,
        ):
            continue

    return (
        declarations.functions,
        declarations.typedefs,
        declarations.constants,
        declarations.runtime_vars,
        declarations.skipped_typedefs,
        declarations.record_typedefs,
        declarations.opaque_pointer_typedef_names,
    )
