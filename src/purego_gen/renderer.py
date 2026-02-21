# Copyright (c) 2026 purego-gen contributors.

"""Jinja2-backed emit layer."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    UndefinedError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.model import ParsedDeclarations

_ALLOWED_EMIT_KINDS: Final[frozenset[str]] = frozenset({"func", "type", "const", "var"})
_TEMPLATE_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "templates"
_MAIN_TEMPLATE_NAME: Final[str] = "go_file.go.j2"
_REQUIRED_CONTEXT_KEYS: Final[frozenset[str]] = frozenset({
    "package",
    "lib_id",
    "emit_kinds",
    "type_aliases",
    "constants",
    "functions",
    "runtime_vars",
})
_ENVIRONMENT: Final[Environment] = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,  # noqa: S701
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


class RendererError(RuntimeError):
    """Raised when template rendering fails."""


class _TypeAliasContext(TypedDict):
    identifier: str
    go_type: str


class _ConstantContext(TypedDict):
    identifier: str
    value: int


class _FunctionContext(TypedDict):
    identifier: str
    symbol: str


class _RuntimeVarContext(TypedDict):
    identifier: str
    symbol: str


class _TemplateContext(TypedDict):
    package: str
    lib_id: str
    emit_kinds: tuple[str, ...]
    type_aliases: tuple[_TypeAliasContext, ...]
    constants: tuple[_ConstantContext, ...]
    functions: tuple[_FunctionContext, ...]
    runtime_vars: tuple[_RuntimeVarContext, ...]


def _sanitize_identifier(raw: str) -> str:
    """Sanitize source identifier into a Go-syntax-safe suffix.

    Returns:
        Safe lowercase identifier suffix.
    """
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", raw).strip("_").lower()
    if not normalized:
        return "decl"
    if normalized[0].isdigit():
        return f"n_{normalized}"
    return normalized


def _validate_emit_kinds(emit_kinds: tuple[str, ...]) -> None:
    """Validate emit categories used by the renderer.

    Raises:
        RendererError: One or more categories are unsupported.
    """
    invalid = [kind for kind in emit_kinds if kind not in _ALLOWED_EMIT_KINDS]
    if invalid:
        message = (
            f"renderer received unsupported emit categories: {', '.join(invalid)}. "
            "Supported values: func,type,const,var."
        )
        raise RendererError(message)


def _build_context(
    *,
    package: str,
    lib_id: str,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
) -> _TemplateContext:
    """Build render context for the main Go output template.

    Returns:
        Context dictionary passed to Jinja2 template rendering.
    """
    _validate_emit_kinds(emit_kinds)
    return {
        "package": package,
        "lib_id": lib_id,
        "emit_kinds": emit_kinds,
        "type_aliases": tuple(
            {
                "identifier": _sanitize_identifier(typedef.name),
                "go_type": typedef.go_type,
            }
            for typedef in declarations.typedefs
        ),
        "constants": tuple(
            {
                "identifier": _sanitize_identifier(constant.name),
                "value": constant.value,
            }
            for constant in declarations.constants
        ),
        "functions": tuple(
            {
                "identifier": _sanitize_identifier(function.name),
                "symbol": function.name,
            }
            for function in declarations.functions
        ),
        "runtime_vars": tuple(
            {
                "identifier": _sanitize_identifier(runtime_var.name),
                "symbol": runtime_var.name,
            }
            for runtime_var in declarations.runtime_vars
        ),
    }


def _validate_template_context(context: Mapping[str, object]) -> None:
    """Validate presence of required top-level context keys.

    Raises:
        RendererError: One or more required top-level keys are missing.
    """
    missing = sorted(_REQUIRED_CONTEXT_KEYS.difference(context))
    if missing:
        message = f"template context missing required keys: {', '.join(missing)}"
        raise RendererError(message)


def render_template(template_name: str, context: Mapping[str, object]) -> str:
    """Render one template with strict undefined checks.

    Returns:
        Rendered template text.

    Raises:
        RendererError: Template is missing, required context keys are missing,
            or undefined variables are accessed during rendering.
    """
    _validate_template_context(context)

    try:
        template = _ENVIRONMENT.get_template(template_name)
    except TemplateNotFound as error:
        message = f"template not found: {template_name}"
        raise RendererError(message) from error

    try:
        return template.render(**dict(context))
    except UndefinedError as error:
        message = f"template rendering failed due to undefined variable: {error}"
        raise RendererError(message) from error


def render_go_source(
    *,
    package: str,
    lib_id: str,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
) -> str:
    """Render generated Go source for one CLI invocation.

    Returns:
        Unformatted Go source rendered from templates.
    """
    context = _build_context(
        package=package,
        lib_id=lib_id,
        emit_kinds=emit_kinds,
        declarations=declarations,
    )
    return render_template(_MAIN_TEMPLATE_NAME, context)
