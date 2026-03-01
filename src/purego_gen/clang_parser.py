# Copyright (c) 2026 purego-gen contributors.

"""libclang-backed declaration parser."""

from __future__ import annotations

import importlib
import os
import re
from ctypes import c_uint
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from purego_gen.macro_constants import evaluate_object_like_macro_definition
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
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
    TypeMappingOptions,
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
_CHAR_TYPE_KINDS: Final[frozenset[str]] = frozenset({"CHAR_S", "CHAR_U"})
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


@dataclass(frozen=True, slots=True)
class _ParseContext:
    """Shared parse context reused across headers in one parse run."""

    cindex: _CIndexModule
    index: _IndexLike
    clang_args: tuple[str, ...]
    macro_cursor_predicates: _MacroCursorPredicates
    type_mapping: TypeMappingOptions


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
    def is_const_qualified(self) -> bool: ...


class _ArgumentLike(Protocol):
    spelling: str
    type: _TypeLike


class _CursorLike(Protocol):
    kind: _CursorKindLike
    spelling: str
    raw_comment: str
    location: _SourceLocationLike
    result_type: _TypeLike
    underlying_typedef_type: _TypeLike
    type: _TypeLike
    enum_value: int
    storage_class: _StorageClassLike

    def get_children(self) -> list[_CursorLike]: ...
    def get_tokens(self) -> list[_TokenLike]: ...

    def get_arguments(self) -> list[_ArgumentLike]: ...
    def is_bitfield(self) -> bool: ...
    def is_definition(self) -> bool: ...
    def get_bitfield_width(self) -> int: ...
    def get_field_offsetof(self) -> int: ...


class _TokenLike(Protocol):
    spelling: str


class _CursorBoolProbeLike(Protocol):
    """ctypes-backed libclang probe with cursor argument and bool-like result."""

    argtypes: list[object]
    restype: object

    def __call__(self, cursor: object) -> int: ...


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
    MACRO_DEFINITION: object


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
    Cursor: type[object]
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


@dataclass(frozen=True, slots=True)
class _MacroCursorPredicates:
    """libclang-backed cursor predicates used by macro extraction."""

    is_function_like: Callable[[_CursorLike], bool]
    is_builtin: Callable[[_CursorLike], bool]


@dataclass(slots=True)
class _MacroCollectionState:
    """Mutable state shared by macro constant collection in one header."""

    known_constant_values: dict[str, int]
    cursor_predicates: _MacroCursorPredicates


def _bind_cursor_bool_probe(
    *,
    cindex: _CIndexModule,
    symbol_name: str,
) -> Callable[[_CursorLike], bool] | None:
    """Bind one libclang cursor predicate via ctypes.

    Returns:
        Callable predicate when symbol binding succeeds, otherwise `None`.
    """
    conf_object = cast("object | None", getattr(cindex, "conf", None))
    if conf_object is None:
        return None
    lib_object = cast("object | None", getattr(conf_object, "lib", None))
    if lib_object is None:
        return None
    raw_probe = cast("object | None", getattr(lib_object, symbol_name, None))
    if raw_probe is None:
        return None

    probe = cast("_CursorBoolProbeLike", raw_probe)
    try:
        probe.argtypes = [cindex.Cursor]
        probe.restype = c_uint
    except AttributeError, TypeError:
        return None

    def _predicate(cursor: _CursorLike) -> bool:
        try:
            return bool(probe(cast("object", cursor)))
        except TypeError, ValueError:
            return False

    return _predicate


def _build_macro_cursor_predicates(cindex: _CIndexModule) -> _MacroCursorPredicates:
    """Build macro-related cursor predicates from libclang when available.

    Returns:
        Predicate bundle backed by libclang APIs when available.

    Raises:
        ClangParserError: Required macro predicate symbols are unavailable.
    """
    function_like_probe = _bind_cursor_bool_probe(
        cindex=cindex,
        symbol_name="clang_Cursor_isMacroFunctionLike",
    )
    if function_like_probe is None:
        message = (
            "loaded libclang does not expose `clang_Cursor_isMacroFunctionLike`; "
            "cannot classify macros without token fallback."
        )
        raise ClangParserError(message)
    builtin_probe = _bind_cursor_bool_probe(
        cindex=cindex,
        symbol_name="clang_Cursor_isMacroBuiltin",
    )
    if builtin_probe is None:
        message = (
            "loaded libclang does not expose `clang_Cursor_isMacroBuiltin`; "
            "cannot classify built-in macros without token fallback."
        )
        raise ClangParserError(message)
    return _MacroCursorPredicates(
        is_function_like=function_like_probe,
        is_builtin=builtin_probe,
    )


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
    if not declaration.is_definition():
        diagnostic = _UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
            message="incomplete struct typedef is treated as opaque handle",
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
    is_incomplete = (
        declaration.kind.name == _STRUCT_DECL_KIND_NAME and not declaration.is_definition()
    )
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
        is_incomplete=is_incomplete,
        is_opaque=is_incomplete,
    )


def _is_opaque_record_typedef(canonical_record_type: _TypeLike) -> bool:
    """Check whether a record typedef refers to an incomplete struct declaration.

    Returns:
        `True` when declaration is a forward-declared struct with no definition.
    """
    declaration = canonical_record_type.get_declaration()
    return declaration.kind.name == _STRUCT_DECL_KIND_NAME and not declaration.is_definition()


def _map_function_parameter_type_to_go_name(
    clang_type: _TypeLike, *, type_mapping: TypeMappingOptions
) -> str:
    """Map one function parameter type into a Go type.

    Returns:
        Go parameter type name.
    """
    canonical = clang_type.get_canonical()
    if type_mapping.const_char_as_string and canonical.kind.name == "POINTER":
        pointee = canonical.get_pointee().get_canonical()
        if pointee.kind.name in _CHAR_TYPE_KINDS and pointee.is_const_qualified():
            return "string"
    mapped = _map_type_to_go_name(clang_type)
    if mapped is not None:
        return mapped
    # Keep function emission total-order and compilable for v1 unknowns.
    return "uintptr"


def _map_function_result_type_to_go_name(
    clang_type: _TypeLike, *, type_mapping: TypeMappingOptions
) -> str | None:
    """Map one function result type into a Go type.

    Returns:
        Go result type name, or `None` for `void`.
    """
    canonical = clang_type.get_canonical()
    if canonical.kind.name == "VOID":
        return None
    if type_mapping.const_char_as_string and canonical.kind.name == "POINTER":
        pointee = canonical.get_pointee().get_canonical()
        if pointee.kind.name in _CHAR_TYPE_KINDS and pointee.is_const_qualified():
            return "string"
    mapped = _map_type_to_go_name(clang_type)
    if mapped is not None:
        return mapped
    # Keep function emission total-order and compilable for v1 unknowns.
    return "uintptr"


def _extract_cursor_comment(cursor: _CursorLike) -> str | None:
    """Extract one cursor raw comment when available.

    Returns:
        Raw comment text, or `None` when cursor has no non-empty comment.
    """
    raw_comment = str(getattr(cursor, "raw_comment", "") or "")
    if not raw_comment.strip():
        return None
    return raw_comment


def _extract_function(cursor: _CursorLike, *, type_mapping: TypeMappingOptions) -> FunctionDecl:
    """Convert a function cursor to model.

    Returns:
        Normalized function declaration.
    """
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
    """Convert an enum constant cursor to model.

    Returns:
        Normalized compile-time constant declaration.
    """
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
    """Extract one object-like macro constant when expression is supported.

    Returns:
        Parsed compile-time constant, or `None` when macro is unsupported.
    """
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
    """Convert a runtime variable cursor to model.

    Returns:
        Normalized runtime variable declaration.
    """
    return RuntimeVarDecl(
        name=str(cursor.spelling),
        c_type=str(cursor.type.spelling),
        comment=_extract_cursor_comment(cursor),
    )


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
    *,
    type_mapping: TypeMappingOptions,
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
    functions.append(
        _extract_function(
            cursor,
            type_mapping=type_mapping,
        )
    )
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


def _collect_macro_constant(
    cursor: _CursorLike,
    macro_definition_kind: object,
    seen: _SeenDeclarations,
    constants: list[ConstantDecl],
    macro_state: _MacroCollectionState,
) -> bool:
    """Collect one object-like macro constant when expression is supported.

    Returns:
        `True` when cursor matched macro handling branch.
    """
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
    parse_context: _ParseContext,
    header_path: Path,
) -> _TranslationUnitLike:
    """Create translation unit for one header.

    Returns:
        Parsed translation unit.

    Raises:
        ClangParserError: Translation unit could not be loaded.
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
            options=parse_options,
        )
    except cindex.TranslationUnitLoadError as error:
        message = f"failed to load translation unit for {header_path}"
        raise ClangParserError(message) from error


def _parse_header(
    parse_context: _ParseContext,
    header_path: Path,
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
    cindex = parse_context.cindex
    translation_unit = _parse_translation_unit(parse_context, header_path)
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
    macro_state = _MacroCollectionState(
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

        if _collect_function(
            cursor,
            cindex.CursorKind.FUNCTION_DECL,
            seen,
            declarations.functions,
            type_mapping=parse_context.type_mapping,
        ):
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
            macro_state.known_constant_values[str(cursor.spelling)] = int(cursor.enum_value)
            continue
        if macro_definition_kind is not None and _collect_macro_constant(
            cursor,
            macro_definition_kind,
            seen,
            declarations.constants,
            macro_state,
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


def parse_declarations(
    headers: tuple[str, ...],
    clang_args: tuple[str, ...],
    *,
    type_mapping: TypeMappingOptions | None = None,
    map_const_char_pointer_to_string: bool | None = None,
) -> ParsedDeclarations:
    """Parse declaration categories from headers via libclang.

    Returns:
        Parsed declarations in stable order.

    Raises:
        ClangParserError: libclang is unavailable or parsing fails.
        ValueError: Type-mapping options are mutually inconsistent.
    """
    resolved_type_mapping = type_mapping if type_mapping is not None else TypeMappingOptions()
    if map_const_char_pointer_to_string is not None:
        if (
            type_mapping is not None
            and type_mapping.const_char_as_string != map_const_char_pointer_to_string
        ):
            message = (
                "conflicting type mapping options: `type_mapping.const_char_as_string` and "
                "`map_const_char_pointer_to_string` differ"
            )
            raise ValueError(message)
        resolved_type_mapping = TypeMappingOptions(
            const_char_as_string=map_const_char_pointer_to_string,
            strict_enum_typedefs=resolved_type_mapping.strict_enum_typedefs,
            typed_sentinel_constants=resolved_type_mapping.typed_sentinel_constants,
        )

    cindex = _load_cindex()
    _configure_libclang(cindex)

    try:
        index = cindex.Index.create()
    except cindex.LibclangError as error:
        message = (
            "failed to load libclang. Set `LIBCLANG_PATH` to the directory containing libclang."
        )
        raise ClangParserError(message) from error
    parse_context = _ParseContext(
        cindex=cindex,
        index=index,
        clang_args=clang_args,
        macro_cursor_predicates=_build_macro_cursor_predicates(cindex),
        type_mapping=resolved_type_mapping,
    )

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
