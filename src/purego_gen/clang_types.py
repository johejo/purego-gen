# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: TC001, PYI046
# pyright: reportPrivateUsage=false, reportUnusedClass=false

"""Shared internal typing definitions for libclang parser modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from purego_gen.model import (
    ConstantDecl,
    FunctionDecl,
    RecordTypedefDecl,
    RuntimeVarDecl,
    SkippedTypedefDecl,
    TypedefDecl,
    TypeMappingOptions,
)

if TYPE_CHECKING:
    from collections.abc import Callable


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
class _UnsupportedTypeDiagnostic:
    """Stable diagnostic payload for unsupported type patterns."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class _RecordTypeMappingResult:
    """Result of mapping a C record type into Go."""

    go_type: str | None
    unsupported_diagnostic: _UnsupportedTypeDiagnostic | None


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


@dataclass(frozen=True, slots=True)
class _ParseContext:
    """Shared parse context reused across headers in one parse run."""

    cindex: _CIndexModule
    index: _IndexLike
    clang_args: tuple[str, ...]
    macro_cursor_predicates: _MacroCursorPredicates
    type_mapping: TypeMappingOptions
