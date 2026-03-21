# Copyright (c) 2026 purego-gen contributors.

"""libclang-to-model type mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from purego_gen.clang_types import (
    CursorLike,
    RecordTypeMappingResult,
    TypeLike,
    UnsupportedTypeDiagnostic,
)
from purego_gen.identifier_utils import sanitize_struct_field_identifier
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_ANONYMOUS_FIELD,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD_KIND,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_SIZE,
    RecordFieldDecl,
    RecordTypedefDecl,
    TypeMappingOptions,
)

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
_SIGNED_GO_TYPE_BY_SIZE: Final[dict[int, str]] = {1: "int8", 2: "int16", 4: "int32", 8: "int64"}
_UNSIGNED_GO_TYPE_BY_SIZE: Final[dict[int, str]] = {
    1: "uint8",
    2: "uint16",
    4: "uint32",
    8: "uint64",
}
_VARIABLE_SIZE_SIGNED_KINDS: Final[frozenset[str]] = frozenset({"LONG", "ENUM"})
_VARIABLE_SIZE_UNSIGNED_KINDS: Final[frozenset[str]] = frozenset({"ULONG"})
_FUNCTION_TYPE_KINDS: Final[frozenset[str]] = frozenset({"FUNCTIONPROTO", "FUNCTIONNOPROTO"})
_STRING_POINTEE_TYPE_KINDS: Final[frozenset[str]] = frozenset({"CHAR_S", "CHAR_U", "UCHAR"})
_RECORD_TYPE_KIND_NAME: Final[str] = "RECORD"
_CONSTANT_ARRAY_TYPE_KIND_NAME: Final[str] = "CONSTANTARRAY"
_FIELD_DECL_KIND_NAME: Final[str] = "FIELD_DECL"
_STRUCT_DECL_KIND_NAME: Final[str] = "STRUCT_DECL"
_UNION_DECL_KIND_NAME: Final[str] = "UNION_DECL"
# Alignment >8 (e.g. __int128, SIMD types) falls back to unaligned [S]byte.
_ALIGN_TYPE_BY_BYTES: Final[dict[int, str]] = {2: "int16", 4: "int32", 8: "int64"}


def _map_pointer_type_to_go_name(canonical_type: TypeLike) -> str:
    pointee_canonical = canonical_type.get_pointee().get_canonical()
    pointee_kind_name = pointee_canonical.kind.name
    if pointee_kind_name in _FUNCTION_TYPE_KINDS:
        return "uintptr"
    if pointee_kind_name in _STRING_POINTEE_TYPE_KINDS:
        return "uintptr"
    if pointee_kind_name in {"VOID", "POINTER", _RECORD_TYPE_KIND_NAME}:
        return "uintptr"
    size_mapped = _map_variable_size_type_to_go_name(pointee_kind_name, pointee_canonical)
    if size_mapped is not None:
        return f"*{size_mapped}"
    static_mapped = _TYPE_KIND_TO_GO_TYPE.get(pointee_kind_name)
    if static_mapped is not None:
        return f"*{static_mapped}"
    return "uintptr"


def _map_constant_array_type_to_go_name(canonical_type: TypeLike) -> str | None:
    element_type = canonical_type.get_array_element_type().get_canonical()
    element_go_type = map_type_to_go_name(element_type)
    if element_go_type is None:
        return None
    array_size = canonical_type.get_array_size()
    if array_size < 0:
        return None
    return f"[{array_size}]{element_go_type}"


def _map_variable_size_type_to_go_name(kind_name: str, canonical: TypeLike) -> str | None:
    """Resolve a variable-size integer kind using libclang size metadata.

    Returns:
        Mapped Go type name when size is available, otherwise `None`.
    """
    if kind_name in _VARIABLE_SIZE_SIGNED_KINDS:
        size = _safe_type_size_bytes(canonical)
        if size is not None:
            return _SIGNED_GO_TYPE_BY_SIZE.get(size)
    elif kind_name in _VARIABLE_SIZE_UNSIGNED_KINDS:
        size = _safe_type_size_bytes(canonical)
        if size is not None:
            return _UNSIGNED_GO_TYPE_BY_SIZE.get(size)
    return None


def map_type_to_go_name(clang_type: TypeLike) -> str | None:
    """Map libclang type into a basic Go type.

    Returns:
        Mapped Go type name when supported, otherwise `None`.
    """
    canonical = clang_type.get_canonical()
    kind_name = canonical.kind.name

    size_mapped = _map_variable_size_type_to_go_name(kind_name, canonical)
    if size_mapped is not None:
        return size_mapped

    mapped = _TYPE_KIND_TO_GO_TYPE.get(kind_name)
    if mapped is not None:
        return mapped
    if kind_name == "POINTER":
        return _map_pointer_type_to_go_name(canonical)
    if kind_name == _CONSTANT_ARRAY_TYPE_KIND_NAME:
        return _map_constant_array_type_to_go_name(canonical)
    if kind_name == _RECORD_TYPE_KIND_NAME:
        return map_record_type_to_go_name(canonical).go_type
    return None


def _allocate_unique_field_name(base_name: str, seen_field_names: set[str]) -> str:
    """Allocate a unique Go field name within one struct literal.

    Returns:
        Unique field name not present in `seen_field_names`.
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
        Non-negative metric value, or `None` for unsupported negative values.
    """
    if raw_value < 0:
        return None
    return int(raw_value)


def _safe_type_size_bytes(clang_type: TypeLike) -> int | None:
    """Read type size in bytes from clang, tolerating unsupported cases.

    Returns:
        Type size in bytes when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(clang_type.get_size())
    except RuntimeError, TypeError, ValueError:
        return None


def _safe_type_align_bytes(clang_type: TypeLike) -> int | None:
    """Read type alignment in bytes from clang, tolerating unsupported cases.

    Returns:
        Type alignment in bytes when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(clang_type.get_align())
    except RuntimeError, TypeError, ValueError:
        return None


def _safe_field_offset_bits(field_cursor: CursorLike) -> int | None:
    """Read field offset in bits from clang, tolerating unsupported cases.

    Returns:
        Field offset in bits when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(field_cursor.get_field_offsetof())
    except RuntimeError, TypeError, ValueError:
        return None


def _safe_bitfield_width(field_cursor: CursorLike) -> int | None:
    """Read bitfield width from clang, tolerating unsupported cases.

    Returns:
        Bitfield width when available, otherwise `None`.
    """
    try:
        return _normalize_clang_metric(field_cursor.get_bitfield_width())
    except RuntimeError, TypeError, ValueError:
        return None


def _evaluate_record_field_support(
    field_cursor: CursorLike,
    *,
    index: int,
) -> tuple[str | None, UnsupportedTypeDiagnostic | None]:
    """Evaluate whether one record field is supported by v1 mapping.

    Returns:
        Pair of mapped Go type (if any) and unsupported diagnostic (if any).
    """
    field_name_for_message = str(field_cursor.spelling) or f"<anonymous field #{index}>"
    if not field_cursor.spelling:
        diagnostic = UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_ANONYMOUS_FIELD,
            message=f"anonymous field {field_name_for_message} is not supported in v1",
        )
        return None, diagnostic
    if field_cursor.is_bitfield():
        diagnostic = UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
            message=f"bitfield {field_name_for_message} is not supported in v1",
        )
        return None, diagnostic

    go_type = map_type_to_go_name(field_cursor.type)
    if go_type is None:
        diagnostic = UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
            message=(
                f"unsupported field type for {field_name_for_message}: {field_cursor.type.spelling}"
            ),
        )
        return None, diagnostic
    return go_type, None


def _map_record_field_to_go_line(
    field_cursor: CursorLike,
    *,
    index: int,
    seen_field_names: set[str],
) -> tuple[str | None, UnsupportedTypeDiagnostic | None]:
    """Map one record field cursor to a Go field line.

    Returns:
        Pair of rendered Go field line (if supported) and unsupported diagnostic (if any).
    """
    go_type, unsupported_diagnostic = _evaluate_record_field_support(field_cursor, index=index)
    if unsupported_diagnostic is not None:
        return None, unsupported_diagnostic
    if go_type is None:
        fallback_diagnostic = UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
            message="unsupported field type",
        )
        return None, fallback_diagnostic

    base_name = sanitize_struct_field_identifier(
        str(field_cursor.spelling),
        fallback=f"field_{index}",
    )
    field_name = _allocate_unique_field_name(base_name, seen_field_names)
    seen_field_names.add(field_name)
    if go_type == "uintptr":
        return f"\t// C: {field_cursor.type.spelling}\n\t{field_name} {go_type}", None
    return f"\t{field_name} {go_type}", None


def _extract_record_field_decl(
    field_cursor: CursorLike,
    *,
    index: int,
    seen_field_names: set[str],
) -> RecordFieldDecl:
    """Extract structured metadata for one record field.

    Returns:
        Record field metadata declaration.
    """
    canonical_field_type = field_cursor.type.get_canonical()
    go_type, unsupported_diagnostic = _evaluate_record_field_support(field_cursor, index=index)
    is_bitfield = field_cursor.is_bitfield()

    resolved_go_name: str | None = None
    resolved_go_type: str | None = go_type
    if unsupported_diagnostic is None and go_type is not None:
        base_name = sanitize_struct_field_identifier(
            str(field_cursor.spelling),
            fallback=f"field_{index}",
        )
        resolved_go_name = _allocate_unique_field_name(base_name, seen_field_names)
        seen_field_names.add(resolved_go_name)

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
        go_name=resolved_go_name,
        go_type=resolved_go_type,
    )


def _build_padding_field_line(padding_bytes: int) -> str:
    """Build a Go struct padding field line.

    Returns:
        Rendered ``_ [N]byte`` padding field line.
    """
    return f"\t_ [{padding_bytes}]byte"


@dataclass(slots=True)
class _StructPaddingTracker:
    """Tracks byte offsets for explicit struct padding insertion."""

    _current_offset_bytes: int = 0
    _available: bool = True
    _field_offset_bytes: int = 0

    def pre_field_gap(self, field_cursor: CursorLike) -> int:
        """Return padding bytes needed before this field, or 0."""
        if not self._available:
            return 0
        field_offset_bits = _safe_field_offset_bits(field_cursor)
        if field_offset_bits is None or field_offset_bits % 8 != 0:
            self._available = False
            return 0
        self._field_offset_bytes = field_offset_bits // 8
        gap = self._field_offset_bytes - self._current_offset_bytes
        return max(gap, 0)

    def advance(self, field_cursor: CursorLike) -> None:
        """Advance the offset tracker past a successfully mapped field."""
        if not self._available:
            return
        field_size = _safe_type_size_bytes(field_cursor.type.get_canonical())
        if field_size is not None:
            self._current_offset_bytes = self._field_offset_bytes + field_size
        else:
            self._available = False

    def tail_gap(self, struct_type: TypeLike) -> int:
        """Return tail padding bytes needed after the last field, or 0."""
        if not self._available:
            return 0
        struct_size = _safe_type_size_bytes(struct_type)
        if struct_size is not None and struct_size > self._current_offset_bytes:
            return struct_size - self._current_offset_bytes
        return 0


def _build_alignment_wrapper_type(size_bytes: int, align_bytes: int) -> str:
    """Build a Go type literal for a union represented as an opaque byte array.

    Returns:
        Go type literal string (either ``[S]byte`` or ``struct { _ [0]<align>; _ [S]byte }``).
    """
    if align_bytes <= 1:
        return f"[{size_bytes}]byte"
    align_type = _ALIGN_TYPE_BY_BYTES.get(align_bytes)
    if align_type is None:
        return f"[{size_bytes}]byte"
    return f"struct {{\n\t_ [0]{align_type}\n\t_ [{size_bytes}]byte\n}}"


def _check_record_declaration_support(
    declaration: CursorLike,
) -> UnsupportedTypeDiagnostic | None:
    """Check whether a record declaration is supported for v1 mapping.

    Returns:
        Unsupported diagnostic when the declaration cannot be mapped, otherwise `None`.
    """
    declaration_kind_name = declaration.kind.name
    if declaration_kind_name not in {_STRUCT_DECL_KIND_NAME, _UNION_DECL_KIND_NAME}:
        return UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD_KIND,
            message=f"record kind {declaration_kind_name} is not supported in v1",
        )
    if declaration_kind_name == _STRUCT_DECL_KIND_NAME and not declaration.is_definition():
        return UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
            message="incomplete struct typedef is treated as opaque handle",
        )
    return None


def _map_union_type_to_go_name(clang_type: TypeLike) -> RecordTypeMappingResult:
    """Map a union type to an opaque byte array with alignment wrapper.

    Returns:
        Mapping result with Go type text or unsupported diagnostic.
    """
    size_bytes = _safe_type_size_bytes(clang_type)
    align_bytes = _safe_type_align_bytes(clang_type)
    if size_bytes is None or size_bytes <= 0:
        diagnostic = UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_SIZE,
            message="union has unknown or zero size",
        )
        return RecordTypeMappingResult(go_type=None, unsupported_diagnostic=diagnostic)
    return RecordTypeMappingResult(
        go_type=_build_alignment_wrapper_type(size_bytes, align_bytes or 1),
        unsupported_diagnostic=None,
    )


def map_record_type_to_go_name(clang_type: TypeLike) -> RecordTypeMappingResult:
    """Map a simple C record type to a Go struct type literal.

    Returns:
        Mapping result with Go type text or unsupported diagnostic.
    """
    declaration = clang_type.get_declaration()
    unsupported = _check_record_declaration_support(declaration)
    if unsupported is not None:
        return RecordTypeMappingResult(go_type=None, unsupported_diagnostic=unsupported)

    if declaration.kind.name == _UNION_DECL_KIND_NAME:
        return _map_union_type_to_go_name(clang_type)

    field_lines: list[str] = []
    seen_field_names: set[str] = set()
    real_field_count = 0
    padding = _StructPaddingTracker()
    for index, child in enumerate(declaration.get_children(), start=1):
        if child.kind.name != _FIELD_DECL_KIND_NAME:
            continue

        gap = padding.pre_field_gap(child)
        if gap > 0:
            field_lines.append(_build_padding_field_line(gap))

        field_line, unsupported_diagnostic = _map_record_field_to_go_line(
            child,
            index=index,
            seen_field_names=seen_field_names,
        )
        if unsupported_diagnostic is not None:
            return RecordTypeMappingResult(
                go_type=None,
                unsupported_diagnostic=unsupported_diagnostic,
            )
        if field_line is None:
            continue
        field_lines.append(field_line)
        real_field_count += 1
        padding.advance(child)

    tail = padding.tail_gap(clang_type)
    if tail > 0:
        field_lines.append(_build_padding_field_line(tail))

    if real_field_count == 0:
        diagnostic = UnsupportedTypeDiagnostic(
            code=TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
            message="struct has no supported fields in v1",
        )
        return RecordTypeMappingResult(go_type=None, unsupported_diagnostic=diagnostic)
    return RecordTypeMappingResult(
        go_type="struct {\n" + "\n".join(field_lines) + "\n}",
        unsupported_diagnostic=None,
    )


def extract_record_typedef_decl(
    cursor: CursorLike,
    *,
    canonical_record_type: TypeLike,
    mapping_result: RecordTypeMappingResult,
) -> RecordTypedefDecl:
    """Extract structured record typedef metadata for ABI validation.

    Returns:
        Structured record typedef declaration metadata.
    """
    declaration = canonical_record_type.get_declaration()
    is_incomplete = (
        declaration.kind.name == _STRUCT_DECL_KIND_NAME and not declaration.is_definition()
    )
    seen_field_names: set[str] = set()
    fields = tuple(
        _extract_record_field_decl(field_cursor, index=index, seen_field_names=seen_field_names)
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


def is_opaque_pointer_typedef(canonical_pointer_type: TypeLike) -> bool:
    """Check whether a pointer typedef refers to an opaque handle pattern.

    Detects two patterns:
    1. Incomplete struct pointer: ``typedef struct _foo* foo;``
    2. Single-void-pointer struct: ``typedef struct { void *internal_ptr; } *foo;``

    Returns:
        `True` when typedef references an opaque pointer handle.
    """
    pointee = canonical_pointer_type.get_pointee().get_canonical()
    if pointee.kind.name != _RECORD_TYPE_KIND_NAME:
        return False
    declaration = pointee.get_declaration()
    if declaration.kind.name != _STRUCT_DECL_KIND_NAME:
        return False
    if not declaration.is_definition():
        return True
    field_decls = [
        child for child in declaration.get_children() if child.kind.name == _FIELD_DECL_KIND_NAME
    ]
    if len(field_decls) != 1:
        return False
    field_canonical = field_decls[0].type.get_canonical()
    if field_canonical.kind.name != "POINTER":
        return False
    return field_canonical.get_pointee().get_canonical().kind.name == "VOID"


def is_opaque_record_typedef(canonical_record_type: TypeLike) -> bool:
    """Check whether a record typedef refers to an incomplete struct declaration.

    Returns:
        `True` when typedef references an incomplete struct declaration.
    """
    declaration = canonical_record_type.get_declaration()
    return declaration.kind.name == _STRUCT_DECL_KIND_NAME and not declaration.is_definition()


def map_function_parameter_type_to_go_name(
    clang_type: TypeLike, *, type_mapping: TypeMappingOptions
) -> str:
    """Map one function parameter type into a Go type.

    Returns:
        Mapped Go parameter type.
    """
    canonical = clang_type.get_canonical()
    if type_mapping.const_char_as_string and canonical.kind.name == "POINTER":
        pointee = canonical.get_pointee().get_canonical()
        if pointee.kind.name in _STRING_POINTEE_TYPE_KINDS and pointee.is_const_qualified():
            return "string"
    mapped = map_type_to_go_name(clang_type)
    if mapped is not None:
        return mapped
    return "uintptr"


def map_function_result_type_to_go_name(
    clang_type: TypeLike, *, type_mapping: TypeMappingOptions
) -> str | None:
    """Map one function result type into a Go type.

    Returns:
        Mapped Go result type, or `None` for `void`.
    """
    canonical = clang_type.get_canonical()
    if canonical.kind.name == "VOID":
        return None
    if type_mapping.const_char_as_string and canonical.kind.name == "POINTER":
        pointee = canonical.get_pointee().get_canonical()
        if pointee.kind.name in _STRING_POINTEE_TYPE_KINDS and pointee.is_const_qualified():
            return "string"
    mapped = map_type_to_go_name(clang_type)
    if mapped is not None:
        return mapped
    return "uintptr"
