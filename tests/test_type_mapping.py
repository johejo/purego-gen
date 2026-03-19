# Copyright (c) 2026 purego-gen contributors.

"""Unit tests for clang_type_mapping size-based type mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from purego_gen.clang_type_mapping import map_type_to_go_name

if TYPE_CHECKING:
    from purego_gen.clang_types import TypeLike


@dataclass
class _FakeTypeKind:
    name: str


@dataclass
class _FakeCursorKind:
    name: str


@dataclass
class _FakeCursor:
    kind: _FakeCursorKind
    spelling: str = ""
    raw_comment: str = ""
    _children: tuple[object, ...] = ()
    _is_definition: bool = False
    _is_bitfield: bool = False
    _bitfield_width: int = -1
    _field_offset: int = -1

    def get_children(self) -> list[object]:
        return list(self._children)

    def is_definition(self) -> bool:
        return self._is_definition

    def is_bitfield(self) -> bool:
        return self._is_bitfield

    def get_bitfield_width(self) -> int:
        return self._bitfield_width

    def get_field_offsetof(self) -> int:
        return self._field_offset


_NO_DECL_CURSOR_KIND: _FakeCursorKind = _FakeCursorKind(name="NO_DECL_FOUND")
_VOID_TYPE_KIND: _FakeTypeKind = _FakeTypeKind(name="VOID")


@dataclass
class _FakeType:
    """Minimal TypeLike implementation for unit tests."""

    kind: _FakeTypeKind
    spelling: str = ""
    _size: int | None = None
    _align: int = -1
    _const_qualified: bool = False
    _array_size: int = -1
    _pointee: _FakeType | None = field(default=None, repr=False)
    _declaration: _FakeCursor | None = field(default=None, repr=False)
    _array_element_type: _FakeType | None = field(default=None, repr=False)

    def get_canonical(self) -> _FakeType:
        return self

    def get_pointee(self) -> _FakeType:
        return self._pointee or _FakeType(kind=_VOID_TYPE_KIND)

    def get_declaration(self) -> _FakeCursor:
        return self._declaration or _FakeCursor(kind=_NO_DECL_CURSOR_KIND)

    def get_size(self) -> int:
        if self._size is None:
            return -1
        return self._size

    def get_align(self) -> int:
        return self._align

    def is_const_qualified(self) -> bool:
        return self._const_qualified

    def get_array_element_type(self) -> _FakeType:
        return self._array_element_type or _FakeType(kind=_VOID_TYPE_KIND)

    def get_array_size(self) -> int:
        return self._array_size


def _fake_type(kind_name: str, *, size: int | None = None) -> TypeLike:
    """Build a fake TypeLike for testing variable-size type mapping.

    Returns:
        Fake type satisfying the TypeLike protocol.
    """
    return cast("TypeLike", _FakeType(kind=_FakeTypeKind(name=kind_name), _size=size))


@pytest.mark.parametrize(
    ("kind_name", "size", "expected_go_type"),
    [
        pytest.param("LONG", 8, "int64", id="long-8-bytes"),
        pytest.param("LONG", 4, "int32", id="long-4-bytes"),
        pytest.param("ULONG", 8, "uint64", id="ulong-8-bytes"),
        pytest.param("ULONG", 4, "uint32", id="ulong-4-bytes"),
        pytest.param("ENUM", 4, "int32", id="enum-4-bytes"),
        pytest.param("ENUM", 2, "int16", id="enum-2-bytes"),
        pytest.param("ENUM", 1, "int8", id="enum-1-byte"),
    ],
)
def test_size_based_integer_mapping(kind_name: str, size: int, expected_go_type: str) -> None:
    """Variable-size integer kinds should map based on get_size() result."""
    assert map_type_to_go_name(_fake_type(kind_name, size=size)) == expected_go_type


@pytest.mark.parametrize(
    ("kind_name", "expected_go_type"),
    [
        pytest.param("LONG", "int64", id="long-fallback"),
        pytest.param("ULONG", "uint64", id="ulong-fallback"),
        pytest.param("ENUM", "int32", id="enum-fallback"),
    ],
)
def test_size_based_mapping_falls_back_to_static_when_size_unavailable(
    kind_name: str, expected_go_type: str
) -> None:
    """Variable-size kinds should fall back to static mapping when get_size() is unavailable."""
    assert map_type_to_go_name(_fake_type(kind_name)) == expected_go_type


def test_static_mapping_unaffected_for_fixed_size_kinds() -> None:
    """Fixed-size kinds should still use the static dictionary regardless of size."""
    for kind_name, expected in [("INT", "int32"), ("UINT", "uint32"), ("SHORT", "int16")]:
        assert map_type_to_go_name(_fake_type(kind_name, size=8)) == expected
