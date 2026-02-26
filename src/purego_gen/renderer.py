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
_GO_KEYWORDS: Final[frozenset[str]] = frozenset({
    "break",
    "default",
    "func",
    "interface",
    "select",
    "case",
    "defer",
    "go",
    "map",
    "struct",
    "chan",
    "else",
    "goto",
    "package",
    "switch",
    "const",
    "fallthrough",
    "if",
    "range",
    "type",
    "continue",
    "for",
    "import",
    "return",
    "var",
})
_TEMPLATE_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "templates"
_MAIN_TEMPLATE_NAME: Final[str] = "go_file.go.j2"
_OPAQUE_POINTER_TYPEDEF_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:const|volatile|restrict)\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*\*(?:\s*(?:const|volatile|restrict))*$"
)
_GO_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
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


class _FunctionParameterContext(TypedDict):
    name: str
    type: str


class _FunctionContext(TypedDict):
    identifier: str
    symbol: str
    parameters: tuple[_FunctionParameterContext, ...]
    result_type: str | None


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


def _sanitize_identifier(raw: str, *, fallback: str) -> str:
    """Sanitize source identifier into a Go-syntax-safe suffix.

    Returns:
        Safe identifier suffix that preserves source casing as much as possible.
    """
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", raw)
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"n_{normalized}"
    if normalized in _GO_KEYWORDS:
        normalized = f"{normalized}_"
    return normalized


def _allocate_unique_identifier(base_identifier: str, *, seen: set[str]) -> str:
    """Allocate deterministic unique identifier in one declaration category.

    Returns:
        Unique identifier string.
    """
    if base_identifier not in seen:
        seen.add(base_identifier)
        return base_identifier

    suffix = 2
    while f"{base_identifier}_{suffix}" in seen:
        suffix += 1
    resolved = f"{base_identifier}_{suffix}"
    seen.add(resolved)
    return resolved


def _build_unique_identifiers(
    raw_names: tuple[str, ...],
    *,
    fallback_prefix: str,
) -> tuple[str, ...]:
    """Build deterministic unique identifiers for one declaration category.

    Returns:
        Identifier tuple with stable ordering and deterministic dedupe suffixes.
    """
    seen: set[str] = set()
    resolved: list[str] = []
    for index, raw_name in enumerate(raw_names, start=1):
        base_identifier = _sanitize_identifier(raw_name, fallback=f"{fallback_prefix}_{index}")
        resolved_identifier = _allocate_unique_identifier(base_identifier, seen=seen)
        resolved.append(resolved_identifier)
    return tuple(resolved)


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


def _extract_typedef_name_from_pointer_c_type(c_type: str) -> str | None:
    """Extract typedef name from one single-pointer C type spelling.

    Returns:
        Typedef name when `c_type` is a supported single-pointer spelling.
    """
    normalized = " ".join(c_type.split())
    matched = _OPAQUE_POINTER_TYPEDEF_PATTERN.fullmatch(normalized)
    if matched is None:
        return None
    return matched.group(1)


def _build_opaque_alias_type_by_typedef_name(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
) -> dict[str, str]:
    """Build emitted opaque typedef alias lookup used by function signatures.

    Returns:
        Mapping of typedef name to generated alias type name.
    """
    if "type" not in emit_kinds:
        return {}

    emitted_typedef_by_name = {
        typedef.name: typedef for typedef in declarations.typedefs if typedef.go_type == "uintptr"
    }
    type_identifier_by_name = {
        typedef.name: identifier
        for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
    }
    opaque_alias_type_by_typedef_name: dict[str, str] = {}
    for record_typedef in declarations.record_typedefs:
        if record_typedef.record_kind != "STRUCT_DECL":
            continue
        if record_typedef.supported:
            continue
        if record_typedef.fields:
            continue
        emitted_typedef = emitted_typedef_by_name.get(record_typedef.name)
        if emitted_typedef is None:
            continue
        identifier = type_identifier_by_name.get(record_typedef.name)
        if identifier is None:
            continue
        opaque_alias_type_by_typedef_name[record_typedef.name] = f"purego_type_{identifier}"
    return opaque_alias_type_by_typedef_name


def _resolve_function_signature_type(
    *,
    go_type: str,
    c_type: str,
    opaque_alias_type_by_typedef_name: Mapping[str, str],
) -> str:
    """Resolve emitted function signature type with opaque-alias substitution.

    Returns:
        Resolved Go type preserving `uintptr` fallback behavior.
    """
    if go_type != "uintptr":
        return go_type
    typedef_name = _extract_typedef_name_from_pointer_c_type(c_type)
    if typedef_name is None:
        return go_type
    return opaque_alias_type_by_typedef_name.get(typedef_name, go_type)


def _sanitize_function_parameter_name(raw_name: str, *, index: int) -> str:
    """Sanitize one C parameter name into a stable Go identifier.

    Returns:
        Sanitized Go parameter name with deterministic fallback.
    """
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", raw_name)
    if not normalized or normalized == "_" or normalized[0].isdigit():
        normalized = f"arg{index}"
    if _GO_IDENTIFIER_PATTERN.fullmatch(normalized) is None:
        normalized = f"arg{index}"
    if normalized in _GO_KEYWORDS:
        normalized = f"{normalized}_"
    return normalized


def _build_function_parameters_context(
    *,
    function_name: str,
    parameter_names: tuple[str, ...],
    go_parameter_types: tuple[str, ...],
    parameter_c_types: tuple[str, ...],
    opaque_alias_type_by_typedef_name: Mapping[str, str],
) -> tuple[_FunctionParameterContext, ...]:
    """Build resolved parameter context for one function signature.

    Returns:
        Function parameter context tuple with resolved names and types.

    Raises:
        RendererError: Parameter metadata lengths are inconsistent.
    """
    if not (len(parameter_names) == len(go_parameter_types) == len(parameter_c_types)):
        message = (
            "function parameter metadata length mismatch for "
            f"{function_name}: names={len(parameter_names)}, "
            f"go_types={len(go_parameter_types)}, c_types={len(parameter_c_types)}"
        )
        raise RendererError(message)

    seen_names: set[str] = set()
    parameters: list[_FunctionParameterContext] = []
    for index, (parameter_name, go_parameter_type, parameter_c_type) in enumerate(
        zip(parameter_names, go_parameter_types, parameter_c_types, strict=True),
        start=1,
    ):
        resolved_name = _sanitize_function_parameter_name(parameter_name, index=index)
        resolved_name = _allocate_unique_identifier(resolved_name, seen=seen_names)
        parameters.append({
            "name": resolved_name,
            "type": _resolve_function_signature_type(
                go_type=go_parameter_type,
                c_type=parameter_c_type,
                opaque_alias_type_by_typedef_name=opaque_alias_type_by_typedef_name,
            ),
        })
    return tuple(parameters)


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
    type_identifiers = _build_unique_identifiers(
        tuple(typedef.name for typedef in declarations.typedefs),
        fallback_prefix="type",
    )
    constant_identifiers = _build_unique_identifiers(
        tuple(constant.name for constant in declarations.constants),
        fallback_prefix="const",
    )
    function_identifiers = _build_unique_identifiers(
        tuple(function.name for function in declarations.functions),
        fallback_prefix="func",
    )
    runtime_var_identifiers = _build_unique_identifiers(
        tuple(runtime_var.name for runtime_var in declarations.runtime_vars),
        fallback_prefix="var",
    )
    opaque_alias_type_by_typedef_name = _build_opaque_alias_type_by_typedef_name(
        emit_kinds=emit_kinds,
        declarations=declarations,
        type_identifiers=type_identifiers,
    )

    return {
        "package": package,
        "lib_id": lib_id,
        "emit_kinds": emit_kinds,
        "type_aliases": tuple(
            {
                "identifier": identifier,
                "go_type": typedef.go_type,
            }
            for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
        ),
        "constants": tuple(
            {
                "identifier": identifier,
                "value": constant.value,
            }
            for constant, identifier in zip(
                declarations.constants, constant_identifiers, strict=True
            )
        ),
        "functions": tuple(
            {
                "identifier": identifier,
                "symbol": function.name,
                "parameters": _build_function_parameters_context(
                    function_name=function.name,
                    parameter_names=function.parameter_names,
                    go_parameter_types=function.go_parameter_types,
                    parameter_c_types=function.parameter_c_types,
                    opaque_alias_type_by_typedef_name=opaque_alias_type_by_typedef_name,
                ),
                "result_type": _resolve_function_signature_type(
                    go_type=function.go_result_type,
                    c_type=function.result_c_type,
                    opaque_alias_type_by_typedef_name=opaque_alias_type_by_typedef_name,
                )
                if function.go_result_type is not None
                else None,
            }
            for function, identifier in zip(
                declarations.functions, function_identifiers, strict=True
            )
        ),
        "runtime_vars": tuple(
            {
                "identifier": identifier,
                "symbol": runtime_var.name,
            }
            for runtime_var, identifier in zip(
                declarations.runtime_vars, runtime_var_identifiers, strict=True
            )
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
