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
    ConstantDecl,
    FunctionDecl,
    ParsedDeclarations,
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
    skip_reason: str | None


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


def _map_record_field_to_go_line(
    field_cursor: _CursorLike,
    *,
    index: int,
    seen_field_names: set[str],
) -> tuple[str | None, str | None]:
    """Map one record field cursor to a Go field line.

    Returns:
        Tuple of mapped field line and optional skip reason.
    """
    field_name_for_message = str(field_cursor.spelling) or f"<anonymous field #{index}>"
    if not field_cursor.spelling:
        skip_reason = f"anonymous field {field_name_for_message} is not supported in v1"
        return None, skip_reason
    if field_cursor.is_bitfield():
        skip_reason = f"bitfield {field_name_for_message} is not supported in v1"
        return None, skip_reason

    go_type = _map_type_to_go_name(field_cursor.type)
    if go_type is None:
        skip_reason = (
            f"unsupported field type for {field_name_for_message}: {field_cursor.type.spelling}"
        )
        return None, skip_reason

    base_name = _sanitize_go_identifier(
        str(field_cursor.spelling),
        fallback=f"field_{index}",
    )
    field_name = _allocate_unique_field_name(base_name, seen_field_names)
    seen_field_names.add(field_name)
    return f"\t{field_name} {go_type}", None


def _map_record_type_to_go_name(clang_type: _TypeLike) -> _RecordTypeMappingResult:
    """Map a simple C record type to a Go struct type literal.

    Returns:
        Mapping result with generated Go type literal or skip reason.
    """
    declaration = clang_type.get_declaration()
    declaration_kind_name = declaration.kind.name
    if declaration_kind_name == _UNION_DECL_KIND_NAME:
        skip_reason = "union typedefs are not supported in v1"
        return _RecordTypeMappingResult(go_type=None, skip_reason=skip_reason)
    if declaration_kind_name != _STRUCT_DECL_KIND_NAME:
        skip_reason = f"record kind {declaration_kind_name} is not supported in v1"
        return _RecordTypeMappingResult(go_type=None, skip_reason=skip_reason)

    field_lines: list[str] = []
    seen_field_names: set[str] = set()

    for index, child in enumerate(declaration.get_children(), start=1):
        if child.kind.name != _FIELD_DECL_KIND_NAME:
            continue

        field_line, skip_reason = _map_record_field_to_go_line(
            child,
            index=index,
            seen_field_names=seen_field_names,
        )
        if skip_reason is not None:
            return _RecordTypeMappingResult(go_type=None, skip_reason=skip_reason)
        if field_line is None:
            continue
        field_lines.append(field_line)
    if not field_lines:
        skip_reason = "struct has no supported fields in v1"
        return _RecordTypeMappingResult(go_type=None, skip_reason=skip_reason)
    return _RecordTypeMappingResult(
        go_type="struct {\n" + "\n".join(field_lines) + "\n}",
        skip_reason=None,
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


def _extract_typedef(cursor: _CursorLike) -> tuple[TypedefDecl | None, str | None]:
    """Convert a typedef cursor to model when it is basic.

    Returns:
        Normalized typedef declaration and optional skip reason.
    """
    underlying = cursor.underlying_typedef_type
    canonical = underlying.get_canonical()
    go_type = _map_type_to_go_name(underlying)
    if go_type is None:
        if canonical.kind.name == _RECORD_TYPE_KIND_NAME:
            mapping_result = _map_record_type_to_go_name(canonical)
            return None, mapping_result.skip_reason
        return None, None
    return (
        TypedefDecl(name=str(cursor.spelling), c_type=str(underlying.spelling), go_type=go_type),
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
    typedefs: list[TypedefDecl],
    skipped_typedefs: list[SkippedTypedefDecl],
) -> bool:
    """Collect one typedef declaration when applicable.

    Returns:
        `True` when cursor matched typedef handling branch.
    """
    if cursor.kind != typedef_decl_kind:
        return False
    if cursor.spelling in seen.typedef_names:
        return True

    typedef, skip_reason = _extract_typedef(cursor)
    if typedef is None:
        if skip_reason is not None:
            skipped_typedefs.append(
                SkippedTypedefDecl(
                    name=str(cursor.spelling),
                    c_type=str(cursor.underlying_typedef_type.spelling),
                    reason=skip_reason,
                )
            )
        return True
    seen.typedef_names.add(cursor.spelling)
    typedefs.append(typedef)
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
        return [], [], [], [], []

    functions: list[FunctionDecl] = []
    typedefs: list[TypedefDecl] = []
    constants: list[ConstantDecl] = []
    runtime_vars: list[RuntimeVarDecl] = []
    skipped_typedefs: list[SkippedTypedefDecl] = []
    for cursor in _walk_preorder(root_cursor):
        if not _is_cursor_from_header(cursor, header_path):
            continue

        if _collect_function(cursor, cindex.CursorKind.FUNCTION_DECL, seen, functions):
            continue
        if _collect_typedef(
            cursor,
            cindex.CursorKind.TYPEDEF_DECL,
            seen,
            typedefs,
            skipped_typedefs,
        ):
            continue
        if _collect_constant(cursor, cindex.CursorKind.ENUM_CONSTANT_DECL, seen, constants):
            continue
        if _collect_runtime_var(cursor, cindex.CursorKind.VAR_DECL, seen, runtime_vars):
            continue

    return functions, typedefs, constants, runtime_vars, skipped_typedefs


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

    all_functions: list[FunctionDecl] = []
    all_typedefs: list[TypedefDecl] = []
    all_constants: list[ConstantDecl] = []
    all_runtime_vars: list[RuntimeVarDecl] = []
    all_skipped_typedefs: list[SkippedTypedefDecl] = []
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
        ) = _parse_header(
            cindex=cindex,
            index=index,
            header_path=header_path,
            clang_args=clang_args,
            seen=seen,
        )
        all_functions.extend(parsed_functions)
        all_typedefs.extend(parsed_typedefs)
        all_constants.extend(parsed_constants)
        all_runtime_vars.extend(parsed_runtime_vars)
        all_skipped_typedefs.extend(parsed_skipped_typedefs)

    return ParsedDeclarations(
        functions=tuple(all_functions),
        typedefs=tuple(all_typedefs),
        constants=tuple(all_constants),
        runtime_vars=tuple(all_runtime_vars),
        skipped_typedefs=tuple(all_skipped_typedefs),
    )
