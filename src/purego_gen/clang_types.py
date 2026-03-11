# Copyright (c) 2026 purego-gen contributors.

"""Shared internal typing definitions for libclang parser modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from purego_gen.model import (
        ConstantDecl,
        FunctionDecl,
        RecordTypedefDecl,
        RuntimeVarDecl,
        SkippedTypedefDecl,
        TypedefDecl,
        TypeMappingOptions,
    )


@dataclass(slots=True)
class SeenDeclarations:
    """Deduplication keys for extracted declarations."""

    function_names: set[str]
    typedef_names: set[str]
    constant_names: set[str]
    runtime_var_names: set[str]


@dataclass(slots=True)
class CollectedDeclarations:
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


class TypeLike(Protocol):
    """Minimal libclang type protocol used by parser helpers."""

    spelling: str
    kind: _TypeKindLike

    def get_canonical(self) -> TypeLike:
        """Return canonicalized type view."""
        ...

    def get_pointee(self) -> TypeLike:
        """Return pointed-at type for pointer-like kinds."""
        ...

    def get_declaration(self) -> CursorLike:
        """Return declaration cursor for this type."""
        ...

    def get_size(self) -> int:
        """Return type size in bytes or negative sentinel."""
        ...

    def get_align(self) -> int:
        """Return type alignment in bytes or negative sentinel."""
        ...

    def is_const_qualified(self) -> bool:
        """Return whether type is const qualified."""
        ...

    def get_array_element_type(self) -> TypeLike:
        """Return element type for array-like kinds."""
        ...

    def get_array_size(self) -> int:
        """Return array element count or negative sentinel."""
        ...


class _ArgumentLike(Protocol):
    spelling: str
    type: TypeLike


class CursorLike(Protocol):
    """Minimal libclang cursor protocol used by parser helpers."""

    kind: _CursorKindLike
    spelling: str
    raw_comment: str
    location: _SourceLocationLike
    result_type: TypeLike
    underlying_typedef_type: TypeLike
    type: TypeLike
    enum_value: int
    storage_class: _StorageClassLike

    def get_children(self) -> list[CursorLike]:
        """Return direct child cursors."""
        ...

    def get_tokens(self) -> list[_TokenLike]:
        """Return source tokens under this cursor."""
        ...

    def get_arguments(self) -> list[_ArgumentLike]:
        """Return function argument cursors."""
        ...

    def is_bitfield(self) -> bool:
        """Return whether cursor represents a bitfield."""
        ...

    def is_definition(self) -> bool:
        """Return whether cursor is a full definition."""
        ...

    def get_bitfield_width(self) -> int:
        """Return bitfield width or negative sentinel."""
        ...

    def get_field_offsetof(self) -> int:
        """Return field offset in bits or negative sentinel."""
        ...


class _TokenLike(Protocol):
    spelling: str


class CursorBoolProbeLike(Protocol):
    """ctypes-backed libclang probe with cursor argument and bool-like result."""

    argtypes: list[object]
    restype: object

    def __call__(self, cursor: object) -> int:
        """Call probe and return libclang bool-like integer value."""
        ...


class _DiagnosticLike(Protocol):
    severity: int
    location: _SourceLocationLike
    spelling: str


class TranslationUnitLike(Protocol):
    """Minimal libclang translation unit protocol."""

    diagnostics: list[_DiagnosticLike]
    cursor: CursorLike | None


@dataclass(frozen=True, slots=True)
class UnsupportedTypeDiagnostic:
    """Stable diagnostic payload for unsupported type patterns."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RecordTypeMappingResult:
    """Result of mapping a C record type into Go."""

    go_type: str | None
    unsupported_diagnostic: UnsupportedTypeDiagnostic | None


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
    ) -> TranslationUnitLike: ...


class _IndexFactoryLike(Protocol):
    def create(self) -> _IndexLike: ...


class CIndexModule(Protocol):
    """Minimal `clang.cindex` module protocol used by parser runtime."""

    Config: _ConfigLike
    TranslationUnit: _TranslationUnitConfigLike
    CursorKind: _CursorKindConfigLike
    Index: _IndexFactoryLike
    Cursor: type[object]
    TranslationUnitLoadError: type[Exception]
    LibclangError: type[Exception]


@dataclass(frozen=True, slots=True)
class MacroCursorPredicates:
    """libclang-backed cursor predicates used by macro extraction."""

    is_function_like: Callable[[CursorLike], bool]
    is_builtin: Callable[[CursorLike], bool]


@dataclass(slots=True)
class MacroCollectionState:
    """Mutable state shared by macro constant collection in one header."""

    known_constant_values: dict[str, int]
    cursor_predicates: MacroCursorPredicates


@dataclass(frozen=True, slots=True)
class ParseContext:
    """Shared parse context reused across headers in one parse run."""

    cindex: CIndexModule
    index: _IndexLike
    clang_args: tuple[str, ...]
    macro_cursor_predicates: MacroCursorPredicates
    type_mapping: TypeMappingOptions
