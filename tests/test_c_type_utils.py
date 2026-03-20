# Copyright (c) 2026 purego-gen contributors.

"""Unit tests for c_type_utils extraction helpers."""

from __future__ import annotations

import pytest

from purego_gen.c_type_utils import (
    extract_double_pointer_typedef_name,
    extract_pointer_typedef_name,
)


@pytest.mark.parametrize(
    ("c_type", "expected"),
    [
        ("sqlite3 *", "sqlite3"),
        ("fixture_ctx_t *", "fixture_ctx_t"),
        ("const sqlite3 *", "sqlite3"),
        ("volatile sqlite3 *", "sqlite3"),
        ("restrict sqlite3 *", "sqlite3"),
        ("const volatile sqlite3 *", "sqlite3"),
        ("sqlite3 * const", "sqlite3"),
        ("sqlite3  *", "sqlite3"),
        ("  sqlite3 *  ", "sqlite3"),
        ("sqlite3 **", None),
        ("void *", "void"),
        ("int", None),
        ("sqlite3", None),
        ("int (*)(void *, int)", None),
    ],
)
def test_extract_pointer_typedef_name(c_type: str, expected: str | None) -> None:
    """Single-pointer extraction should match typedef names and reject non-pointers."""
    assert extract_pointer_typedef_name(c_type) == expected


@pytest.mark.parametrize(
    ("c_type", "expected"),
    [
        ("sqlite3 **", "sqlite3"),
        ("sqlite3_stmt **", "sqlite3_stmt"),
        ("const sqlite3 **", "sqlite3"),
        ("volatile sqlite3 **", "sqlite3"),
        ("restrict sqlite3 **", "sqlite3"),
        ("const volatile sqlite3 **", "sqlite3"),
        ("sqlite3 ** const", "sqlite3"),
        ("sqlite3 * *", "sqlite3"),
        ("sqlite3  **", "sqlite3"),
        ("  sqlite3 **  ", "sqlite3"),
        ("sqlite3 *", None),
        ("void **", "void"),
        ("int", None),
        ("sqlite3", None),
        ("sqlite3 ***", None),
    ],
)
def test_extract_double_pointer_typedef_name(c_type: str, expected: str | None) -> None:
    """Double-pointer extraction should match typedef names and reject single/non-pointers."""
    assert extract_double_pointer_typedef_name(c_type) == expected
