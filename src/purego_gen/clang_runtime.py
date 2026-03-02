# Copyright (c) 2026 purego-gen contributors.

"""libclang runtime loading and ctypes probe helpers."""

from __future__ import annotations

import os
from ctypes import c_uint
from typing import TYPE_CHECKING, cast

from clang import cindex
from purego_gen.clang_types import (
    CIndexModule,
    CursorBoolProbeLike,
    CursorLike,
    MacroCursorPredicates,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class ClangParserError(RuntimeError):
    """Raised when libclang parsing cannot complete."""


def load_cindex() -> CIndexModule:
    """Return statically imported `clang.cindex` module."""
    return cast("CIndexModule", cindex)


def configure_libclang(cindex: CIndexModule) -> None:
    """Configure libclang shared library lookup from environment."""
    library_path = os.getenv("LIBCLANG_PATH")
    if library_path and not cindex.Config.loaded:
        cindex.Config.set_library_path(library_path)


def _bind_cursor_bool_probe(
    *,
    cindex: CIndexModule,
    symbol_name: str,
) -> Callable[[CursorLike], bool] | None:
    """Bind one libclang cursor predicate via ctypes.

    Returns:
        Callable probe when symbol exists and binding succeeds, otherwise `None`.
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

    probe = cast("CursorBoolProbeLike", raw_probe)
    try:
        probe.argtypes = [cindex.Cursor]
        probe.restype = c_uint
    except AttributeError, TypeError:
        return None

    def _predicate(cursor: CursorLike) -> bool:
        try:
            return bool(probe(cast("object", cursor)))
        except TypeError, ValueError:
            return False

    return _predicate


def build_macro_cursor_predicates(cindex: CIndexModule) -> MacroCursorPredicates:
    """Build macro-related cursor predicates from libclang when available.

    Returns:
        Builtin and function-like macro cursor predicates.

    Raises:
        ClangParserError: Required libclang predicate symbol is unavailable.
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
    return MacroCursorPredicates(
        is_function_like=function_like_probe,
        is_builtin=builtin_probe,
    )


__all__ = [
    "ClangParserError",
    "build_macro_cursor_predicates",
    "configure_libclang",
    "load_cindex",
]
