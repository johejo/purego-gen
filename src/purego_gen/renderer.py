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

from purego_gen.c_type_utils import (
    extract_enum_typedef_name,
    extract_pointer_typedef_name,
    normalize_c_type_for_lookup,
)
from purego_gen.emit_kinds import validate_emit_kinds
from purego_gen.identifier_utils import (
    GO_KEYWORDS,
    allocate_unique_identifier,
    build_unique_identifiers,
    is_go_identifier,
)
from purego_gen.model import TypeMappingOptions

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.model import ParsedDeclarations

_TEMPLATE_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "templates"
_MAIN_TEMPLATE_NAME: Final[str] = "go_file.go.j2"
_MAX_INT64: Final[int] = (1 << 63) - 1
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
    is_strict: bool
    comment_lines: tuple[str, ...]


class _ConstantContext(TypedDict):
    identifier: str
    value: int
    const_type: str | None
    comment_lines: tuple[str, ...]


class _FunctionParameterContext(TypedDict):
    name: str
    type: str


class _FunctionContext(TypedDict):
    identifier: str
    symbol: str
    parameters: tuple[_FunctionParameterContext, ...]
    result_type: str | None
    comment_lines: tuple[str, ...]


class _RuntimeVarContext(TypedDict):
    identifier: str
    symbol: str
    comment_lines: tuple[str, ...]


class _TemplateContext(TypedDict):
    package: str
    lib_id: str
    emit_kinds: tuple[str, ...]
    type_aliases: tuple[_TypeAliasContext, ...]
    constants: tuple[_ConstantContext, ...]
    functions: tuple[_FunctionContext, ...]
    runtime_vars: tuple[_RuntimeVarContext, ...]


def _build_emitted_opaque_struct_typedef_names(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    emitted_typedef_names: set[str],
) -> set[str]:
    """Build emitted opaque struct typedef-name set.

    Returns:
        Set of opaque typedef names emitted in this render.
    """
    if "type" not in emit_kinds:
        return set()

    opaque_typedef_names: set[str] = set()
    for record_typedef in declarations.record_typedefs:
        if record_typedef.record_kind != "STRUCT_DECL":
            continue
        if not record_typedef.is_opaque:
            continue
        if record_typedef.name not in emitted_typedef_names:
            continue
        opaque_typedef_names.add(record_typedef.name)
    return opaque_typedef_names


def _build_opaque_alias_type_by_typedef_name(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emitted_opaque_struct_typedef_names: set[str],
) -> dict[str, str]:
    """Build emitted opaque typedef alias lookup used by function signatures.

    Returns:
        Mapping of typedef name to generated alias type name.
    """
    type_identifier_by_name = {
        typedef.name: identifier
        for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
    }
    opaque_alias_type_by_typedef_name: dict[str, str] = {}
    for typedef_name in emitted_opaque_struct_typedef_names:
        identifier = type_identifier_by_name.get(typedef_name)
        if identifier is None:
            continue
        opaque_alias_type_by_typedef_name[typedef_name] = f"purego_type_{identifier}"
    return opaque_alias_type_by_typedef_name


def _build_emitted_strict_enum_typedef_names(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    type_mapping: TypeMappingOptions,
) -> set[str]:
    """Build emitted enum typedef-name set for strict enum-type mode.

    Returns:
        Set of enum typedef names emitted as strict types.
    """
    if "type" not in emit_kinds or not type_mapping.strict_enum_typedefs:
        return set()
    return {
        typedef.name
        for typedef in declarations.typedefs
        if extract_enum_typedef_name(typedef.c_type) is not None
    }


def _build_enum_alias_type_by_typedef_name(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emitted_strict_enum_typedef_names: set[str],
) -> dict[str, str]:
    """Build emitted strict-enum typedef alias lookup for function signatures.

    Returns:
        Mapping of enum typedef spellings to generated strict alias type names.
    """
    type_identifier_by_name = {
        typedef.name: identifier
        for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
    }
    typedef_by_name = {typedef.name: typedef for typedef in declarations.typedefs}
    enum_alias_type_by_typedef_name: dict[str, str] = {}
    for typedef_name in emitted_strict_enum_typedef_names:
        identifier = type_identifier_by_name.get(typedef_name)
        if identifier is None:
            continue
        alias_name = f"purego_type_{identifier}"
        enum_alias_type_by_typedef_name[typedef_name] = alias_name
        enum_alias_type_by_typedef_name[f"enum {typedef_name}"] = alias_name
        typedef = typedef_by_name.get(typedef_name)
        if typedef is None:
            continue
        enum_target_name = extract_enum_typedef_name(typedef.c_type)
        if enum_target_name is None:
            continue
        enum_alias_type_by_typedef_name[enum_target_name] = alias_name
        enum_alias_type_by_typedef_name[f"enum {enum_target_name}"] = alias_name
    return enum_alias_type_by_typedef_name


def _resolve_constant_type(*, value: int, type_mapping: TypeMappingOptions) -> str | None:
    """Resolve optional Go type annotation for one constant declaration.

    Returns:
        Go type name when strict sentinel typing applies, otherwise `None`.
    """
    if type_mapping.typed_sentinel_constants and value > _MAX_INT64:
        return "uint64"
    return None


def _resolve_function_signature_type(
    *,
    go_type: str,
    c_type: str,
    opaque_alias_type_by_typedef_name: Mapping[str, str],
    enum_alias_type_by_typedef_name: Mapping[str, str],
) -> str:
    """Resolve emitted function signature type with opaque-alias substitution.

    Returns:
        Resolved Go type preserving `uintptr` fallback behavior.
    """
    if go_type == "int32":
        normalized_c_type = normalize_c_type_for_lookup(c_type)
        strict_enum_alias = enum_alias_type_by_typedef_name.get(normalized_c_type)
        if strict_enum_alias is not None:
            return strict_enum_alias
    if go_type != "uintptr":
        return go_type
    typedef_name = extract_pointer_typedef_name(c_type)
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
    if not is_go_identifier(normalized):
        normalized = f"arg{index}"
    if normalized in GO_KEYWORDS:
        normalized = f"{normalized}_"
    return normalized


def _trim_comment_blank_edges(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Trim leading/trailing empty lines from normalized comment lines.

    Returns:
        Comment lines without outer blank lines.
    """
    start = 0
    end = len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return lines[start:end]


def _normalize_comment_lines(comment: str | None) -> tuple[str, ...]:
    """Normalize libclang raw comment text into Go `//` body lines.

    Returns:
        Comment lines suitable for rendering as `// {line}`.
    """
    if comment is None:
        return ()

    normalized = comment.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ()

    is_block = normalized.startswith("/*") and normalized.endswith("*/")
    raw_lines = tuple(normalized.split("\n"))
    processed: list[str] = []

    if is_block:
        block_body = normalized[2:-2]
        for line in block_body.split("\n"):
            stripped_line = re.sub(r"^\s*\* ?", "", line)
            processed.append(stripped_line.strip())
        return _trim_comment_blank_edges(tuple(processed))

    for line in raw_lines:
        stripped_line = re.sub(r"^\s*/// ?", "", line)
        stripped_line = re.sub(r"^\s*// ?", "", stripped_line)
        processed.append(stripped_line.strip())
    return _trim_comment_blank_edges(tuple(processed))


def _build_function_parameters_context(
    *,
    parameter_names: tuple[str, ...],
    go_parameter_types: tuple[str, ...],
    parameter_c_types: tuple[str, ...],
    opaque_alias_type_by_typedef_name: Mapping[str, str],
    enum_alias_type_by_typedef_name: Mapping[str, str],
) -> tuple[_FunctionParameterContext, ...]:
    """Build resolved parameter context for one function signature.

    Returns:
        Function parameter context tuple with resolved names and types.

    Raises:
        RendererError: Parameter metadata lengths are inconsistent.
    """
    if not (len(parameter_names) == len(go_parameter_types) == len(parameter_c_types)):
        message = (
            "function parameter metadata length mismatch: "
            f"names={len(parameter_names)}, "
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
        resolved_name = allocate_unique_identifier(resolved_name, seen=seen_names)
        parameters.append({
            "name": resolved_name,
            "type": _resolve_function_signature_type(
                go_type=go_parameter_type,
                c_type=parameter_c_type,
                opaque_alias_type_by_typedef_name=opaque_alias_type_by_typedef_name,
                enum_alias_type_by_typedef_name=enum_alias_type_by_typedef_name,
            ),
        })
    return tuple(parameters)


def _build_context(
    *,
    package: str,
    lib_id: str,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    type_mapping: TypeMappingOptions,
) -> _TemplateContext:
    """Build render context for the main Go output template.

    Returns:
        Context dictionary passed to Jinja2 template rendering.

    Raises:
        RendererError: Emit kinds are invalid for renderer context building.
    """
    try:
        validate_emit_kinds(emit_kinds, context="renderer")
    except ValueError as error:
        raise RendererError(str(error)) from error
    type_identifiers = build_unique_identifiers(
        tuple(typedef.name for typedef in declarations.typedefs),
        fallback_prefix="type",
    )
    constant_identifiers = build_unique_identifiers(
        tuple(constant.name for constant in declarations.constants),
        fallback_prefix="const",
    )
    function_identifiers = build_unique_identifiers(
        tuple(function.name for function in declarations.functions),
        fallback_prefix="func",
    )
    runtime_var_identifiers = build_unique_identifiers(
        tuple(runtime_var.name for runtime_var in declarations.runtime_vars),
        fallback_prefix="var",
    )
    emitted_typedef_names = {
        typedef.name for typedef in declarations.typedefs if typedef.go_type == "uintptr"
    }
    emitted_opaque_struct_typedef_names = _build_emitted_opaque_struct_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
        emitted_typedef_names=emitted_typedef_names,
    )
    emitted_strict_enum_typedef_names = _build_emitted_strict_enum_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
        type_mapping=type_mapping,
    )
    opaque_alias_type_by_typedef_name = _build_opaque_alias_type_by_typedef_name(
        declarations=declarations,
        type_identifiers=type_identifiers,
        emitted_opaque_struct_typedef_names=emitted_opaque_struct_typedef_names,
    )
    enum_alias_type_by_typedef_name = _build_enum_alias_type_by_typedef_name(
        declarations=declarations,
        type_identifiers=type_identifiers,
        emitted_strict_enum_typedef_names=emitted_strict_enum_typedef_names,
    )

    return {
        "package": package,
        "lib_id": lib_id,
        "emit_kinds": emit_kinds,
        "type_aliases": tuple(
            {
                "identifier": identifier,
                "go_type": typedef.go_type,
                "is_strict": (
                    typedef.name in emitted_opaque_struct_typedef_names
                    or typedef.name in emitted_strict_enum_typedef_names
                ),
                "comment_lines": _normalize_comment_lines(typedef.comment),
            }
            for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
        ),
        "constants": tuple(
            {
                "identifier": identifier,
                "value": constant.value,
                "const_type": _resolve_constant_type(
                    value=constant.value,
                    type_mapping=type_mapping,
                ),
                "comment_lines": _normalize_comment_lines(constant.comment),
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
                    parameter_names=function.parameter_names,
                    go_parameter_types=function.go_parameter_types,
                    parameter_c_types=function.parameter_c_types,
                    opaque_alias_type_by_typedef_name=opaque_alias_type_by_typedef_name,
                    enum_alias_type_by_typedef_name=enum_alias_type_by_typedef_name,
                ),
                "result_type": _resolve_function_signature_type(
                    go_type=function.go_result_type,
                    c_type=function.result_c_type,
                    opaque_alias_type_by_typedef_name=opaque_alias_type_by_typedef_name,
                    enum_alias_type_by_typedef_name=enum_alias_type_by_typedef_name,
                )
                if function.go_result_type is not None
                else None,
                "comment_lines": _normalize_comment_lines(function.comment),
            }
            for function, identifier in zip(
                declarations.functions, function_identifiers, strict=True
            )
        ),
        "runtime_vars": tuple(
            {
                "identifier": identifier,
                "symbol": runtime_var.name,
                "comment_lines": _normalize_comment_lines(runtime_var.comment),
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
    type_mapping: TypeMappingOptions | None = None,
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
        type_mapping=type_mapping if type_mapping is not None else TypeMappingOptions(),
    )
    return render_template(_MAIN_TEMPLATE_NAME, context)
