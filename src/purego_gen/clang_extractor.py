# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201, TC001
# pyright: reportPrivateUsage=false, reportUnusedFunction=false

"""Declaration extraction and collection helpers for libclang parser."""

from __future__ import annotations

from purego_gen.clang_type_mapping import (
    _extract_record_typedef_decl,
    _is_opaque_record_typedef,
    _map_function_parameter_type_to_go_name,
    _map_function_result_type_to_go_name,
    _map_record_type_to_go_name,
    _map_type_to_go_name,
)
from purego_gen.clang_types import (
    _CollectedDeclarations,
    _CursorLike,
    _MacroCollectionState,
    _MacroCursorPredicates,
    _SeenDeclarations,
    _UnsupportedTypeDiagnostic,
)
from purego_gen.macro_constants import evaluate_object_like_macro_definition
from purego_gen.model import (
    ConstantDecl,
    FunctionDecl,
    RecordTypedefDecl,
    RuntimeVarDecl,
    SkippedTypedefDecl,
    TypedefDecl,
    TypeMappingOptions,
)

_RECORD_TYPE_KIND_NAME = "RECORD"


def _extract_cursor_comment(cursor: _CursorLike) -> str | None:
    """Extract one cursor raw comment when available."""
    raw_comment = str(getattr(cursor, "raw_comment", "") or "")
    if not raw_comment.strip():
        return None
    return raw_comment


def _extract_function(cursor: _CursorLike, *, type_mapping: TypeMappingOptions) -> FunctionDecl:
    """Convert a function cursor to model."""
    arguments = tuple(cursor.get_arguments())
    parameters = tuple(argument.type.spelling for argument in arguments)
    parameter_names = tuple(str(argument.spelling) for argument in arguments)
    go_parameter_types = tuple(
        _map_function_parameter_type_to_go_name(
            argument.type,
            type_mapping=type_mapping,
        )
        for argument in arguments
    )
    return FunctionDecl(
        name=str(cursor.spelling),
        result_c_type=str(cursor.result_type.spelling),
        parameter_c_types=parameters,
        parameter_names=parameter_names,
        go_result_type=_map_function_result_type_to_go_name(
            cursor.result_type,
            type_mapping=type_mapping,
        ),
        go_parameter_types=go_parameter_types,
        comment=_extract_cursor_comment(cursor),
    )


def _extract_typedef(
    cursor: _CursorLike,
) -> tuple[TypedefDecl | None, _UnsupportedTypeDiagnostic | None, RecordTypedefDecl | None]:
    """Convert a typedef cursor to model when it is basic."""
    underlying = cursor.underlying_typedef_type
    canonical = underlying.get_canonical()
    if canonical.kind.name == _RECORD_TYPE_KIND_NAME:
        mapping_result = _map_record_type_to_go_name(canonical)
        record_typedef = _extract_record_typedef_decl(
            cursor,
            canonical_record_type=canonical,
            mapping_result=mapping_result,
        )
        if mapping_result.go_type is None:
            if _is_opaque_record_typedef(canonical):
                return (
                    TypedefDecl(
                        name=str(cursor.spelling),
                        c_type=str(underlying.spelling),
                        go_type="uintptr",
                        comment=_extract_cursor_comment(cursor),
                    ),
                    None,
                    record_typedef,
                )
            return None, mapping_result.unsupported_diagnostic, record_typedef
        return (
            TypedefDecl(
                name=str(cursor.spelling),
                c_type=str(underlying.spelling),
                go_type=mapping_result.go_type,
                comment=_extract_cursor_comment(cursor),
            ),
            None,
            record_typedef,
        )

    go_type = _map_type_to_go_name(underlying)
    if go_type is None:
        return None, None, None
    return (
        TypedefDecl(
            name=str(cursor.spelling),
            c_type=str(underlying.spelling),
            go_type=go_type,
            comment=_extract_cursor_comment(cursor),
        ),
        None,
        None,
    )


def _extract_constant(cursor: _CursorLike) -> ConstantDecl:
    """Convert an enum constant cursor to model."""
    return ConstantDecl(
        name=str(cursor.spelling),
        value=int(cursor.enum_value),
        comment=_extract_cursor_comment(cursor),
    )


def _extract_macro_constant(
    cursor: _CursorLike,
    *,
    known_constant_values: dict[str, int],
    macro_cursor_predicates: _MacroCursorPredicates,
) -> ConstantDecl | None:
    """Extract one object-like macro constant when expression is supported."""
    if macro_cursor_predicates.is_builtin(cursor):
        return None

    is_function_like = macro_cursor_predicates.is_function_like(cursor)
    evaluated = evaluate_object_like_macro_definition(
        token_spellings=tuple(token.spelling for token in cursor.get_tokens()),
        known_constant_values=known_constant_values,
        is_function_like=is_function_like,
    )
    if evaluated is None:
        return None
    return ConstantDecl(
        name=str(cursor.spelling),
        value=evaluated,
        comment=_extract_cursor_comment(cursor),
    )


def _extract_runtime_var(cursor: _CursorLike) -> RuntimeVarDecl:
    """Convert a runtime variable cursor to model."""
    return RuntimeVarDecl(
        name=str(cursor.spelling),
        c_type=str(cursor.type.spelling),
        comment=_extract_cursor_comment(cursor),
    )


def _is_extern_runtime_var(cursor: _CursorLike) -> bool:
    """Check whether a variable declaration represents an extern data symbol."""
    return cursor.storage_class.name == "EXTERN"


def _collect_function(
    cursor: _CursorLike,
    function_decl_kind: object,
    seen: _SeenDeclarations,
    functions: list[FunctionDecl],
    *,
    type_mapping: TypeMappingOptions,
) -> bool:
    """Collect one function declaration when applicable."""
    if cursor.kind != function_decl_kind:
        return False
    if cursor.spelling in seen.function_names:
        return True
    seen.function_names.add(cursor.spelling)
    functions.append(_extract_function(cursor, type_mapping=type_mapping))
    return True


def _collect_typedef(
    cursor: _CursorLike,
    typedef_decl_kind: object,
    seen: _SeenDeclarations,
    declarations: _CollectedDeclarations,
) -> bool:
    """Collect one typedef declaration when applicable."""
    if cursor.kind != typedef_decl_kind:
        return False
    if cursor.spelling in seen.typedef_names:
        return True

    typedef, unsupported_diagnostic, record_typedef = _extract_typedef(cursor)
    if record_typedef is not None:
        declarations.record_typedefs.append(record_typedef)
    if typedef is None:
        if unsupported_diagnostic is not None:
            declarations.skipped_typedefs.append(
                SkippedTypedefDecl(
                    name=str(cursor.spelling),
                    c_type=str(cursor.underlying_typedef_type.spelling),
                    reason_code=unsupported_diagnostic.code,
                    reason=unsupported_diagnostic.message,
                )
            )
        return True
    seen.typedef_names.add(cursor.spelling)
    declarations.typedefs.append(typedef)
    return True


def _collect_constant(
    cursor: _CursorLike,
    enum_constant_decl_kind: object,
    seen: _SeenDeclarations,
    constants: list[ConstantDecl],
) -> bool:
    """Collect one compile-time constant declaration when applicable."""
    if cursor.kind != enum_constant_decl_kind:
        return False
    if cursor.spelling in seen.constant_names:
        return True
    seen.constant_names.add(cursor.spelling)
    constants.append(_extract_constant(cursor))
    return True


def _collect_macro_constant(
    cursor: _CursorLike,
    macro_definition_kind: object,
    seen: _SeenDeclarations,
    constants: list[ConstantDecl],
    macro_state: _MacroCollectionState,
) -> bool:
    """Collect one object-like macro constant when expression is supported."""
    if cursor.kind != macro_definition_kind:
        return False
    if cursor.spelling in seen.constant_names:
        return True

    extracted = _extract_macro_constant(
        cursor,
        known_constant_values=macro_state.known_constant_values,
        macro_cursor_predicates=macro_state.cursor_predicates,
    )
    if extracted is None:
        return True
    seen.constant_names.add(cursor.spelling)
    constants.append(extracted)
    macro_state.known_constant_values[extracted.name] = extracted.value
    return True


def _collect_runtime_var(
    cursor: _CursorLike,
    var_decl_kind: object,
    seen: _SeenDeclarations,
    runtime_vars: list[RuntimeVarDecl],
) -> bool:
    """Collect one runtime variable declaration when applicable."""
    if cursor.kind != var_decl_kind:
        return False
    if not _is_extern_runtime_var(cursor):
        return True
    if cursor.spelling in seen.runtime_var_names:
        return True
    seen.runtime_var_names.add(cursor.spelling)
    runtime_vars.append(_extract_runtime_var(cursor))
    return True
