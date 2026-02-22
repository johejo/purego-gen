# Copyright (c) 2026 purego-gen contributors.

"""libclang-backed declaration parser."""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast

from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_ANONYMOUS_FIELD,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD_KIND,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF,
    ConstantDecl,
    FunctionDecl,
    ParsedDeclarations,
    RecordFieldDecl,
    RecordTypedefDecl,
    RuntimeVarDecl,
    SkippedTypedefDecl,
    TypedefDecl,
)

_SEVERITY_ERROR: Final[int] = 3
_TYPE_KIND_TO_GO_TYPE: Final[dict[str, str]] = {
    "BOOL": "bool",
    "CHAR_S": "int8",
    "SCHAR": "int8",
    "CHAR_U": "uint8",
    "UCHAR": "uint8",
    "SHORT": "int16",
    "USHORT": "uint16",
    "INT": "int32",
    "UINT": "uint32",
    "LONG": "int64",
    "ULONG": "uint64",
    "LONGLONG": "int64",
    "ULONGLONG": "uint64",
    "FLOAT": "float32",
    "DOUBLE": "float64",
    "ENUM": "int32",
}
_FUNCTION_TYPE_KINDS: Final[frozenset[str]] = frozenset({"FUNCTIONPROTO", "FUNCTIONNOPROTO"})
_RECORD_TYPE_KIND_NAME: Final[str] = "RECORD"
_FIELD_DECL_KIND_NAME: Final[str] = "FIELD_DECL"
_STRUCT_DECL_KIND_NAME: Final[str] = "STRUCT_DECL"
_UNION_DECL_KIND_NAME: Final[str] = "UNION_DECL"
_GO_KEYWORDS: Final[frozenset[str]] = frozenset({
    "break",
    "case",
    "chan",
    "const",
    "continue",
    "default",
    "defer",
    "else",
    "fallthrough",
    "for",
    "func",
    "go",
    "goto",
    "if",
    "import",
    "interface",
    "map",
    "package",
    "range",
    "return",
    "select",
    "struct",
    "switch",
    "type",
    "var",
})


class ClangParserError(RuntimeError):
    """Raised when libclang parsing cannot complete."""


@dataclass(slots=True)
class _SeenDeclarations:
    """Deduplication keys for extracted declarations."""

    function_names: set[str]
    typedef_names: set[str]
    constant_names: set[str]
    runtime_var_names: set[str]


@dataclass(slots=True)
class _CollectedDeclarations:
    """Mutable declaration buffers for one parse run."""

    functions: list[FunctionDecl]
    typedefs: list[TypedefDecl]
    constants: list[ConstantDecl]
    runtime_vars: list[RuntimeVarDecl]
    skipped_typedefs: list[SkippedTypedefDecl]
    record_typedefs: list[RecordTypedefDecl]


class _SourceFileLike(Protocol):
    name: str


class _SourceLocationLike(Protocol):
    file: _SourceFileLike | None
    line: int
    column: int


class _TypeKindLike(Protocol):
    name: str


class _CursorKindLike(Protocol):
    name: str


class _TypeLike(Protocol):
    spelling: str
    kind: _TypeKindLike

    def get_canonical(self) -> _TypeLike: ...
    def get_pointee(self) -> _TypeLike: ...
    def get_declaration(self) -> _CursorLike: ...
    def get_size(self) -> int: ...
    def get_align(self) -> int: ...


class _ArgumentLike(Protocol):
    type: _TypeLike


class _CursorLike(Protocol):
    kind: _CursorKindLike
    spelling: str
    location: _SourceLocationLike
    result_type: _TypeLike
    underlying_typedef_type: _TypeLike
    type: _TypeLike
    enum_value: int
    storage_class: _StorageClassLike

    def get_children(self) -> list[_CursorLike]: ...

    def get_arguments(self) -> list[_ArgumentLike]: ...
    def is_bitfield(self) -> bool: ...
    def get_bitfield_width(self) -> int: ...
    def get_field_offsetof(self) -> int: ...


class _DiagnosticLike(Protocol):
    severity: int
    location: _SourceLocationLike
    spelling: str


class _TranslationUnitLike(Protocol):
    diagnostics: list[_DiagnosticLike]
    cursor: _CursorLike | None


@dataclass(frozen=True, slots=True)
class _RecordTypeMappingResult:
    """Result of mapping a C record type into Go."""

    go_type: str | None
    unsupported_diagnostic: _UnsupportedTypeDiagnostic | None


@dataclass(frozen=True, slots=True)
class _UnsupportedTypeDiagnostic:
    """Stable diagnostic payload for unsupported type patterns."""

    code: str
    message: str


class _ConfigLike(Protocol):
    loaded: bool

    def set_library_path(self, path: str) -> None: ...


class _TranslationUnitConfigLike(Protocol):
    PARSE_SKIP_FUNCTION_BODIES: int


class _CursorKindConfigLike(Protocol):
    FUNCTION_DECL: object
    TYPEDEF_DECL: object
    ENUM_CONSTANT_DECL: object
    VAR_DECL: object


class _StorageClassLike(Protocol):
    name: str


class _IndexLike(Protocol):
    def parse(
        self,
        *,
        path: str,
        args: list[str],
        options: int,
    ) -> _TranslationUnitLike: ...


class _IndexFactoryLike(Protocol):
    def create(self) -> _IndexLike: ...


class _CIndexModule(Protocol):
    Config: _ConfigLike
    TranslationUnit: _TranslationUnitConfigLike
    CursorKind: _CursorKindConfigLike
    Index: _IndexFactoryLike
    TranslationUnitLoadError: type[Exception]
    LibclangError: type[Exception]


def _load_cindex() -> _CIndexModule:
    """Import `clang.cindex` module.

    Returns:
        cindex module with required interface.

    Raises:
        ClangParserError: Python clang bindings are unavailable.
    """
    try:
        module = importlib.import_module("clang.cindex")
    except ImportError as error:
        message = (
            "clang Python bindings are not installed. "
            "Install the dependency group that includes `clang`."
        )
        raise ClangParserError(message) from error
    return cast("_CIndexModule", module)


def _configure_libclang(cindex: _CIndexModule) -> None:
    """Configure libclang shared library lookup from environment."""
    library_path = os.getenv("LIBCLANG_PATH")
    if library_path and not cindex.Config.loaded:
        cindex.Config.set_library_path(library_path)


def _collect_diagnostics(
    translation_unit: _TranslationUnitLike,
    header_path: Path,
) -> tuple[str, ...]:
    """Collect error-level diagnostics.

    Returns:
        Tuple of diagnostic lines.
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


def _walk_preorder(cursor: _CursorLike) -> tuple[_CursorLike, ...]:
    """Collect all cursor nodes in preorder.

    Returns:
        Flat cursor list.
    """
    nodes: list[_CursorLike] = [cursor]
    for child in cursor.get_children():
        nodes.extend(_walk_preorder(child))
    return tuple(nodes)


def _is_cursor_from_header(cursor: _CursorLike, header_path: Path) -> bool:
    """Check if cursor originates from target header.

    Returns:
        `True` when cursor is declared in the target header.
    """
    location = cursor.location
    if location.file is None:
        return False
    return Path(location.file.name).resolve() == header_path


def _map_type_to_go_name(clang_type: _TypeLike) -> str | None:
    """Map libclang type into a basic Go type.

    Returns:
        Go type name when supported, otherwise `None`.
    """
    canonical = clang_type.get_canonical()
    kind_name = canonical.kind.name

    mapped = _TYPE_KIND_TO_GO_TYPE.get(kind_name)
    if mapped is not None:
        return mapped
    if kind_name == "POINTER":
        pointee_kind_name = canonical.get_pointee().get_canonical().kind.name
        if pointee_kind_name in _FUNCTION_TYPE_KINDS:
            # v1 function-pointer typedef support is intentionally low-level.
            return "uintptr"
    if kind_name == "POINTER":
        return "uintptr"
    if kind_name == _RECORD_TYPE_KIND_NAME:
        return _map_record_type_to_go_name(canonical).go_type
    return None


def _sanitize_go_identifier(raw: str, *, fallback: str) -> str:
    """Normalize arbitrary names into a Go identifier token.

    Returns:
        Go identifier-safe token.
    """
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", raw).strip("_")
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"f_{normalized}"
    if normalized in _GO_KEYWORDS:
        normalized = f"{normalized}_"
    return normalized


def _allocate_unique_field_name(base_name: str, seen_field_names: set[str]) -> str:
    """Allocate a unique Go field name within one struct literal.

    Returns:
        Field name unique within `seen_field_names`.
    """
    field_name = base_name
    suffix = 2
    while field_name in seen_field_names:
        field_name = f"{base_name}_{suffix}"
        suffix += 1
    return field_name


def _normalize_clang_metric(raw_value: int) -> int | None:
    """Normalize clang layout metric value.

    Returns:
        Integer value when non-negative, otherwise `None`.
    """
    if raw_value < 0:
        return None
    return int(raw_value)


def _safe_type_size_bytes(clang_type: _TypeLike) -> int | None:
    """Read type size in bytes from clang, tolerating unsupported cases.

    Returns:
        Type size in bytes when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(clang_type.get_size())
    except RuntimeError, TypeError, ValueError:
        return None


def _safe_type_align_bytes(clang_type: _TypeLike) -> int | None:
    """Read type alignment in bytes from clang, tolerating unsupported cases.

    Returns:
        Type alignment in bytes when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(clang_type.get_align())
    except RuntimeError, TypeError, ValueError:
        return None


def _safe_field_offset_bits(field_cursor: _CursorLike) -> int | None:
    """Read field offset in bits from clang, tolerating unsupported cases.

    Returns:
        Field offset in bits when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(field_cursor.get_field_offsetof())
    except RuntimeError, TypeError, ValueError:
        return None


def _safe_bitfield_width(field_cursor: _CursorLike) -> int | None:
    """Read bitfield width from clang, tolerating unsupported cases.

    Returns:
        Bitfield width in bits when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(field_cursor.get_bitfield_width())
    except RuntimeError, TypeError, ValueError:
        return None


def _evaluate_record_field_support(
    field_cursor: _CursorLike,
    *,
    index: int,
) -> tuple[str | None, _UnsupportedTypeDiagnostic | None]:
    """Evaluate whether one record field is supported by v1 mapping.

    Returns:
        Tuple of mapped Go type and optional unsupported diagnostic.
    """
    field_name_for_message = str(field_cursor.spelling) or f"<anonymous field #{index}>"
    if not field_cursor.spelling:
        diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_ANONYMOUS_FIELD,
            message=f"anonymous field {field_name_for_message} is not supported in v1",
        )
        return None, diagnostic
    if field_cursor.is_bitfield():
        diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
            message=f"bitfield {field_name_for_message} is not supported in v1",
        )
        return None, diagnostic

    go_type = _map_type_to_go_name(field_cursor.type)
    if go_type is None:
        diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
            message=(
                f"unsupported field type for {field_name_for_message}: {field_cursor.type.spelling}"
            ),
        )
        return None, diagnostic
    return go_type, None


def _map_record_field_to_go_line(
    field_cursor: _CursorLike,
    *,
    index: int,
    seen_field_names: set[str],
) -> tuple[str | None, _UnsupportedTypeDiagnostic | None]:
    """Map one record field cursor to a Go field line.

    Returns:
        Tuple of mapped field line and optional unsupported diagnostic.
    """
    go_type, unsupported_diagnostic = _evaluate_record_field_support(field_cursor, index=index)
    if unsupported_diagnostic is not None:
        return None, unsupported_diagnostic
    if go_type is None:
        fallback_diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
            message="unsupported field type",
        )
        return None, fallback_diagnostic

    base_name = _sanitize_go_identifier(
        str(field_cursor.spelling),
        fallback=f"field_{index}",
    )
    field_name = _allocate_unique_field_name(base_name, seen_field_names)
    seen_field_names.add(field_name)
    return f"\t{field_name} {go_type}", None


def _extract_record_field_decl(field_cursor: _CursorLike, *, index: int) -> RecordFieldDecl:
    """Extract structured metadata for one record field.

    Returns:
        Parsed field metadata for ABI/model validation.
    """
    canonical_field_type = field_cursor.type.get_canonical()
    go_type, unsupported_diagnostic = _evaluate_record_field_support(field_cursor, index=index)
    _ = go_type  # Explicitly ignore mapped type; model stores C-centric metadata.
    is_bitfield = field_cursor.is_bitfield()
    return RecordFieldDecl(
        name=str(field_cursor.spelling) or f"<anonymous field #{index}>",
        c_type=str(field_cursor.type.spelling),
        kind=str(field_cursor.kind.name),
        offset_bits=_safe_field_offset_bits(field_cursor),
        size_bytes=_safe_type_size_bytes(canonical_field_type),
        align_bytes=_safe_type_align_bytes(canonical_field_type),
        is_bitfield=is_bitfield,
        bitfield_width=_safe_bitfield_width(field_cursor) if is_bitfield else None,
        supported=unsupported_diagnostic is None,
        unsupported_code=(
            unsupported_diagnostic.code if unsupported_diagnostic is not None else None
        ),
        unsupported_reason=(
            unsupported_diagnostic.message if unsupported_diagnostic is not None else None
        ),
    )


def _map_record_type_to_go_name(clang_type: _TypeLike) -> _RecordTypeMappingResult:
    """Map a simple C record type to a Go struct type literal.

    Returns:
        Mapping result with generated Go type literal or unsupported diagnostic.
    """
    declaration = clang_type.get_declaration()
    declaration_kind_name = declaration.kind.name
    if declaration_kind_name == _UNION_DECL_KIND_NAME:
        diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF,
            message="union typedefs are not supported in v1",
        )
        return _RecordTypeMappingResult(go_type=None, unsupported_diagnostic=diagnostic)
    if declaration_kind_name != _STRUCT_DECL_KIND_NAME:
        diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD_KIND,
            message=f"record kind {declaration_kind_name} is not supported in v1",
        )
        return _RecordTypeMappingResult(go_type=None, unsupported_diagnostic=diagnostic)

    field_lines: list[str] = []
    seen_field_names: set[str] = set()

    for index, child in enumerate(declaration.get_children(), start=1):
        if child.kind.name != _FIELD_DECL_KIND_NAME:
            continue

        field_line, unsupported_diagnostic = _map_record_field_to_go_line(
            child,
            index=index,
            seen_field_names=seen_field_names,
        )
        if unsupported_diagnostic is not None:
            return _RecordTypeMappingResult(
                go_type=None,
                unsupported_diagnostic=unsupported_diagnostic,
            )
        if field_line is None:
            continue
        field_lines.append(field_line)
    if not field_lines:
        diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
            message="struct has no supported fields in v1",
        )
        return _RecordTypeMappingResult(go_type=None, unsupported_diagnostic=diagnostic)
    return _RecordTypeMappingResult(
        go_type="struct {\n" + "\n".join(field_lines) + "\n}",
        unsupported_diagnostic=None,
    )


def _extract_record_typedef_decl(
    cursor: _CursorLike,
    *,
    canonical_record_type: _TypeLike,
    mapping_result: _RecordTypeMappingResult,
) -> RecordTypedefDecl:
    """Extract structured record typedef metadata for ABI validation.

    Returns:
        Parsed record typedef metadata with field-level details.
    """
    declaration = canonical_record_type.get_declaration()
    fields = tuple(
        _extract_record_field_decl(field_cursor, index=index)
        for index, field_cursor in enumerate(declaration.get_children(), start=1)
        if field_cursor.kind.name == _FIELD_DECL_KIND_NAME
    )
    return RecordTypedefDecl(
        name=str(cursor.spelling),
        c_type=str(cursor.underlying_typedef_type.spelling),
        record_kind=str(declaration.kind.name),
        size_bytes=_safe_type_size_bytes(canonical_record_type),
        align_bytes=_safe_type_align_bytes(canonical_record_type),
        fields=fields,
        supported=mapping_result.go_type is not None,
        unsupported_code=(
            mapping_result.unsupported_diagnostic.code
            if mapping_result.unsupported_diagnostic is not None
            else None
        ),
        unsupported_reason=(
            mapping_result.unsupported_diagnostic.message
            if mapping_result.unsupported_diagnostic is not None
            else None
        ),
    )


def _extract_function(cursor: _CursorLike) -> FunctionDecl:
    """Convert a function cursor to model.

    Returns:
        Normalized function declaration.
    """
    parameters = tuple(argument.type.spelling for argument in cursor.get_arguments())
    return FunctionDecl(
        name=str(cursor.spelling),
        result_c_type=str(cursor.result_type.spelling),
        parameter_c_types=parameters,
    )


def _extract_typedef(
    cursor: _CursorLike,
) -> tuple[TypedefDecl | None, _UnsupportedTypeDiagnostic | None, RecordTypedefDecl | None]:
    """Convert a typedef cursor to model when it is basic.

    Returns:
        Normalized typedef declaration, optional unsupported diagnostic, and optional
        structured record typedef metadata.
    """
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
            return None, mapping_result.unsupported_diagnostic, record_typedef
        return (
            TypedefDecl(
                name=str(cursor.spelling),
                c_type=str(underlying.spelling),
                go_type=mapping_result.go_type,
            ),
            None,
            record_typedef,
        )

    go_type = _map_type_to_go_name(underlying)
    if go_type is None:
        return None, None, None
    return (
        TypedefDecl(name=str(cursor.spelling), c_type=str(underlying.spelling), go_type=go_type),
        None,
        None,
    )


def _extract_constant(cursor: _CursorLike) -> ConstantDecl:
    """Convert an enum constant cursor to model.

    Returns:
        Normalized compile-time constant declaration.
    """
    return ConstantDecl(name=str(cursor.spelling), value=int(cursor.enum_value))


def _extract_runtime_var(cursor: _CursorLike) -> RuntimeVarDecl:
    """Convert a runtime variable cursor to model.

    Returns:
        Normalized runtime variable declaration.
    """
    return RuntimeVarDecl(name=str(cursor.spelling), c_type=str(cursor.type.spelling))


def _is_extern_runtime_var(cursor: _CursorLike) -> bool:
    """Check whether a variable declaration represents an extern data symbol.

    Returns:
        `True` when the declaration has `extern` storage class.
    """
    return cursor.storage_class.name == "EXTERN"


def _collect_function(
    cursor: _CursorLike,
    function_decl_kind: object,
    seen: _SeenDeclarations,
    functions: list[FunctionDecl],
) -> bool:
    """Collect one function declaration when applicable.

    Returns:
        `True` when cursor matched function handling branch.
    """
    if cursor.kind != function_decl_kind:
        return False
    if cursor.spelling in seen.function_names:
        return True
    seen.function_names.add(cursor.spelling)
    functions.append(_extract_function(cursor))
    return True


def _collect_typedef(
    cursor: _CursorLike,
    typedef_decl_kind: object,
    seen: _SeenDeclarations,
    declarations: _CollectedDeclarations,
) -> bool:
    """Collect one typedef declaration when applicable.

    Returns:
        `True` when cursor matched typedef handling branch.
    """
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
    """Collect one compile-time constant declaration when applicable.

    Returns:
        `True` when cursor matched constant handling branch.
    """
    if cursor.kind != enum_constant_decl_kind:
        return False
    if cursor.spelling in seen.constant_names:
        return True
    seen.constant_names.add(cursor.spelling)
    constants.append(_extract_constant(cursor))
    return True


def _collect_runtime_var(
    cursor: _CursorLike,
    var_decl_kind: object,
    seen: _SeenDeclarations,
    runtime_vars: list[RuntimeVarDecl],
) -> bool:
    """Collect one runtime variable declaration when applicable.

    Returns:
        `True` when cursor matched runtime var handling branch.
    """
    if cursor.kind != var_decl_kind:
        return False
    if not _is_extern_runtime_var(cursor):
        return True
    if cursor.spelling in seen.runtime_var_names:
        return True
    seen.runtime_var_names.add(cursor.spelling)
    runtime_vars.append(_extract_runtime_var(cursor))
    return True


def _parse_translation_unit(
    cindex: _CIndexModule,
    index: _IndexLike,
    header_path: Path,
    clang_args: tuple[str, ...],
) -> _TranslationUnitLike:
    """Create translation unit for one header.

    Returns:
        Parsed translation unit.

    Raises:
        ClangParserError: Translation unit could not be loaded.
    """
    try:
        return index.parse(
            path=str(header_path),
            args=list(clang_args),
            options=cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES,
        )
    except cindex.TranslationUnitLoadError as error:
        message = f"failed to load translation unit for {header_path}"
        raise ClangParserError(message) from error


def _parse_header(
    cindex: _CIndexModule,
    index: _IndexLike,
    header_path: Path,
    clang_args: tuple[str, ...],
    seen: _SeenDeclarations,
) -> tuple[
    list[FunctionDecl],
    list[TypedefDecl],
    list[ConstantDecl],
    list[RuntimeVarDecl],
    list[SkippedTypedefDecl],
    list[RecordTypedefDecl],
]:
    """Parse one header and extract supported declarations.

    Returns:
        Extracted functions, typedefs, constants, and runtime variables.

    Raises:
        ClangParserError: Header parsing fails.
    """
    translation_unit = _parse_translation_unit(cindex, index, header_path, clang_args)
    diagnostic_messages = _collect_diagnostics(translation_unit, header_path)
    if diagnostic_messages:
        raise ClangParserError("\n".join(diagnostic_messages))

    root_cursor = translation_unit.cursor
    if root_cursor is None:
        return [], [], [], [], [], []

    declarations = _CollectedDeclarations(
        functions=[],
        typedefs=[],
        constants=[],
        runtime_vars=[],
        skipped_typedefs=[],
        record_typedefs=[],
    )
    for cursor in _walk_preorder(root_cursor):
        if not _is_cursor_from_header(cursor, header_path):
            continue

        if _collect_function(cursor, cindex.CursorKind.FUNCTION_DECL, seen, declarations.functions):
            continue
        if _collect_typedef(
            cursor,
            cindex.CursorKind.TYPEDEF_DECL,
            seen,
            declarations,
        ):
            continue
        if _collect_constant(
            cursor,
            cindex.CursorKind.ENUM_CONSTANT_DECL,
            seen,
            declarations.constants,
        ):
            continue
        if _collect_runtime_var(
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
    )


def parse_declarations(headers: tuple[str, ...], clang_args: tuple[str, ...]) -> ParsedDeclarations:
    """Parse declaration categories from headers via libclang.

    Returns:
        Parsed declarations in stable order.

    Raises:
        ClangParserError: libclang is unavailable or parsing fails.
    """
    cindex = _load_cindex()
    _configure_libclang(cindex)

    try:
        index = cindex.Index.create()
    except cindex.LibclangError as error:
        message = (
            "failed to load libclang. Set `LIBCLANG_PATH` to the directory containing libclang."
        )
        raise ClangParserError(message) from error

    all_declarations = _CollectedDeclarations(
        functions=[],
        typedefs=[],
        constants=[],
        runtime_vars=[],
        skipped_typedefs=[],
        record_typedefs=[],
    )
    seen = _SeenDeclarations(
        function_names=set(),
        typedef_names=set(),
        constant_names=set(),
        runtime_var_names=set(),
    )

    for header in headers:
        header_path = Path(header).resolve()
        if not header_path.exists():
            message = f"header not found: {header_path}"
            raise ClangParserError(message)

        (
            parsed_functions,
            parsed_typedefs,
            parsed_constants,
            parsed_runtime_vars,
            parsed_skipped_typedefs,
            parsed_record_typedefs,
        ) = _parse_header(
            cindex=cindex,
            index=index,
            header_path=header_path,
            clang_args=clang_args,
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
