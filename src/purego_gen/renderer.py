# Copyright (c) 2026 purego-gen contributors.

"""Jinja2-backed emit layer."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    UndefinedError,
    select_autoescape,
)

from purego_gen.c_type_utils import (
    extract_enum_typedef_name,
    extract_pointer_typedef_name,
    is_function_pointer_c_type,
    normalize_c_type_for_lookup,
    normalize_function_pointer_c_type_for_lookup,
    parse_function_pointer_c_type,
)
from purego_gen.config_model import GeneratorHelpers
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

    from purego_gen.model import FunctionDecl, ParsedDeclarations

_MAIN_TEMPLATE_NAME: Final[str] = "go_file.go.j2"
_MAX_INT64: Final[int] = (1 << 63) - 1
_REQUIRED_CONTEXT_KEYS: Final[frozenset[str]] = frozenset({
    "package",
    "lib_id",
    "emit_kinds",
    "type_aliases",
    "constants",
    "functions",
    "helpers",
    "runtime_vars",
})
_BUFFER_HELPER_POINTER_C_TYPE: Final[str] = "void *"
_BUFFER_HELPER_LENGTH_GO_TYPES: Final[frozenset[str]] = frozenset({
    "int32",
    "uint32",
    "int64",
    "uint64",
    "uintptr",
})
_CALLBACK_PRIMITIVE_GO_TYPE_BY_C_TYPE: Final[dict[str, str | None]] = {
    "void": None,
    "bool": "bool",
    "_Bool": "bool",
    "char": "int8",
    "signed char": "int8",
    "unsigned char": "uint8",
    "short": "int16",
    "unsigned short": "uint16",
    "int": "int32",
    "unsigned int": "uint32",
    "long": "int64",
    "unsigned long": "uint64",
    "long long": "int64",
    "unsigned long long": "uint64",
    "float": "float32",
    "double": "float64",
}


class RendererError(RuntimeError):
    """Raised when template rendering fails."""


class _TypeAliasContext(TypedDict):
    identifier: str
    go_type: str
    is_strict: bool
    comment_lines: tuple[str, ...]


class _ConstantContext(TypedDict):
    identifier: str
    expression: str
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


class _HelperLocalContext(TypedDict):
    name: str
    value: str


class _FunctionHelperContext(TypedDict):
    identifier: str
    target_identifier: str
    parameters: tuple[_FunctionParameterContext, ...]
    result_type: str | None
    result_suffix: str
    locals: tuple[_HelperLocalContext, ...]
    slice_parameters: tuple[str, ...]
    callback_parameters: tuple[str, ...]
    call_arguments: tuple[str, ...]


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
    helpers: tuple[_FunctionHelperContext, ...]
    runtime_vars: tuple[_RuntimeVarContext, ...]


class _FunctionSignatureTypeAliases(TypedDict):
    record: Mapping[str, str]
    opaque: Mapping[str, str]
    enum: Mapping[str, str]
    function_pointer: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _ResolvedFunctionParameter:
    raw_name: str
    name: str
    type: str
    go_type: str
    c_type: str


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Renderer options that affect emitted helper and type-mapping behavior."""

    helpers: GeneratorHelpers
    type_mapping: TypeMappingOptions


@dataclass(frozen=True, slots=True)
class _CallbackTypeContext:
    """Shared lookup context for callback helper signature resolution."""

    type_aliases: _FunctionSignatureTypeAliases
    typedef_go_type_by_lookup: Mapping[str, str]
    typedef_c_type_by_lookup: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _HelperBuildContext:
    """Shared helper build context for renderer helper generation."""

    function_identifier_by_name: Mapping[str, str]
    declarations: ParsedDeclarations
    helpers: GeneratorHelpers
    callback_type_context: _CallbackTypeContext


def _resolve_template_dir() -> Path:
    """Resolve the template directory from environment or source layout.

    Returns:
        Template directory path used by the renderer.
    """
    configured_dir = os.getenv("PUREGO_GEN_TEMPLATE_DIR")
    if configured_dir:
        return Path(configured_dir)
    return Path(__file__).resolve().parents[2] / "templates"


@lru_cache(maxsize=1)
def _get_environment() -> Environment:
    """Build and cache the Jinja2 environment.

    Returns:
        Configured Jinja2 environment.
    """
    return Environment(
        loader=FileSystemLoader(str(_resolve_template_dir())),
        autoescape=select_autoescape(default_for_string=False, default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def _build_emitted_record_typedef_names(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
) -> set[str]:
    """Build emitted record typedef-name set.

    Returns:
        Set of record typedef names emitted in this render.
    """
    if "type" not in emit_kinds:
        return set()

    emitted_typedef_names = {typedef.name for typedef in declarations.typedefs}
    record_typedef_names: set[str] = set()
    for record_typedef in declarations.record_typedefs:
        if record_typedef.name not in emitted_typedef_names:
            continue
        record_typedef_names.add(record_typedef.name)
    return record_typedef_names


def _build_record_alias_type_by_typedef_name(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emitted_record_typedef_names: set[str],
) -> dict[str, str]:
    """Build emitted record typedef alias lookup used by function signatures.

    Returns:
        Mapping of record typedef spellings to generated alias type names.
    """
    type_identifier_by_name = {
        typedef.name: identifier
        for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
    }
    typedef_by_name = {typedef.name: typedef for typedef in declarations.typedefs}
    record_alias_type_by_typedef_name: dict[str, str] = {}
    for typedef_name in emitted_record_typedef_names:
        identifier = type_identifier_by_name.get(typedef_name)
        if identifier is None:
            continue
        alias_name = f"purego_type_{identifier}"
        record_alias_type_by_typedef_name[typedef_name] = alias_name
        typedef = typedef_by_name.get(typedef_name)
        if typedef is None:
            continue
        normalized_c_type = normalize_c_type_for_lookup(typedef.c_type)
        record_alias_type_by_typedef_name[normalized_c_type] = alias_name
    return record_alias_type_by_typedef_name


def _build_emitted_opaque_struct_typedef_names(
    *,
    declarations: ParsedDeclarations,
    emitted_record_typedef_names: set[str],
) -> set[str]:
    """Build emitted opaque struct typedef-name subset.

    Returns:
        Set of opaque typedef names emitted in this render.
    """
    opaque_typedef_names: set[str] = set()
    for record_typedef in declarations.record_typedefs:
        if record_typedef.record_kind != "STRUCT_DECL":
            continue
        if not record_typedef.is_opaque:
            continue
        if record_typedef.name not in emitted_record_typedef_names:
            continue
        opaque_typedef_names.add(record_typedef.name)
    return opaque_typedef_names


def _build_opaque_alias_type_by_typedef_name(
    *,
    emitted_opaque_struct_typedef_names: set[str],
    record_alias_type_by_typedef_name: Mapping[str, str],
) -> dict[str, str]:
    """Build emitted opaque typedef alias lookup used by pointer signatures.

    Returns:
        Mapping of opaque typedef name to generated alias type name.
    """
    return {
        typedef_name: record_alias_type_by_typedef_name[typedef_name]
        for typedef_name in emitted_opaque_struct_typedef_names
        if typedef_name in record_alias_type_by_typedef_name
    }


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


def _build_typedef_alias_type_by_lookup(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emit_kinds: tuple[str, ...],
) -> dict[str, str]:
    """Build emitted typedef alias lookup keyed by typedef name and C spelling.

    Returns:
        Alias lookup for emitted typedefs, keyed by typedef name and normalized
        C type spelling.
    """
    if "type" not in emit_kinds:
        return {}

    alias_type_by_lookup: dict[str, str] = {}
    for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True):
        alias_name = f"purego_type_{identifier}"
        alias_type_by_lookup[typedef.name] = alias_name
        alias_type_by_lookup[normalize_c_type_for_lookup(typedef.c_type)] = alias_name
    return alias_type_by_lookup


def _build_function_pointer_alias_type_by_lookup(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emit_kinds: tuple[str, ...],
) -> dict[str, str]:
    """Build emitted function-pointer typedef alias lookup.

    Returns:
        Alias lookup for emitted function-pointer typedefs.
    """
    if "type" not in emit_kinds:
        return {}

    alias_type_by_lookup: dict[str, str] = {}
    for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True):
        if typedef.go_type != "uintptr" or not is_function_pointer_c_type(typedef.c_type):
            continue
        alias_name = f"purego_type_{identifier}"
        alias_type_by_lookup[typedef.name] = alias_name
        alias_type_by_lookup[normalize_function_pointer_c_type_for_lookup(typedef.c_type)] = (
            alias_name
        )
    return alias_type_by_lookup


def _build_typedef_go_type_by_lookup(
    declarations: ParsedDeclarations,
) -> dict[str, str]:
    """Build typedef Go-type lookup keyed by typedef name and C spelling.

    Returns:
        Go-type lookup for typedef names and normalized C spellings.
    """
    go_type_by_lookup: dict[str, str] = {}
    for typedef in declarations.typedefs:
        go_type_by_lookup[typedef.name] = typedef.go_type
        go_type_by_lookup[normalize_c_type_for_lookup(typedef.c_type)] = typedef.go_type
    return go_type_by_lookup


def _build_typedef_c_type_by_lookup(
    declarations: ParsedDeclarations,
) -> dict[str, str]:
    """Build typedef C-type lookup keyed by typedef name and normalized spelling.

    Returns:
        Mapping from typedef spellings and normalized keys to underlying C types.
    """
    c_type_by_lookup: dict[str, str] = {}
    for typedef in declarations.typedefs:
        c_type_by_lookup[typedef.name] = typedef.c_type
        c_type_by_lookup[normalize_c_type_for_lookup(typedef.name)] = typedef.c_type
        c_type_by_lookup[normalize_c_type_for_lookup(typedef.c_type)] = typedef.c_type
    return c_type_by_lookup


def _resolve_function_signature_type(
    *,
    go_type: str,
    c_type: str,
    type_aliases: _FunctionSignatureTypeAliases,
) -> str:
    """Resolve emitted function signature type with opaque-alias substitution.

    Returns:
        Resolved Go type preserving `uintptr` fallback behavior.
    """
    if go_type == "int32":
        normalized_c_type = normalize_c_type_for_lookup(c_type)
        strict_enum_alias = type_aliases["enum"].get(normalized_c_type)
        if strict_enum_alias is not None:
            return strict_enum_alias
    normalized_c_type = normalize_c_type_for_lookup(c_type)
    record_alias_type = type_aliases["record"].get(normalized_c_type)
    if record_alias_type is not None:
        return record_alias_type
    function_pointer_alias = type_aliases["function_pointer"].get(
        normalize_function_pointer_c_type_for_lookup(c_type)
    )
    if function_pointer_alias is not None:
        return function_pointer_alias
    if go_type != "uintptr":
        return go_type
    typedef_name = extract_pointer_typedef_name(c_type)
    if typedef_name is None:
        return go_type
    return type_aliases["opaque"].get(typedef_name, go_type)


def _resolve_constant_expression(
    *,
    constant_expression: str | None,
    value: int,
    const_type: str | None,
) -> str:
    """Resolve emitted Go expression for one constant declaration.

    Returns:
        Go expression text used in the generated constant declaration.
    """
    if const_type is not None and constant_expression is not None:
        return constant_expression
    return str(value)


def _resolve_typed_constant_type(
    *,
    constant_c_type: str | None,
    value: int,
    type_mapping: TypeMappingOptions,
    typedef_alias_type_by_lookup: Mapping[str, str],
    typedef_go_type_by_lookup: Mapping[str, str],
) -> str | None:
    """Resolve optional Go type annotation for one constant declaration.

    Returns:
        Go type text for typed constant emission, or `None` when the constant
        should stay untyped.
    """
    if type_mapping.typed_sentinel_constants and constant_c_type is not None:
        alias_type = typedef_alias_type_by_lookup.get(constant_c_type)
        if alias_type is not None:
            return alias_type
        normalized_c_type = normalize_c_type_for_lookup(constant_c_type)
        alias_type = typedef_alias_type_by_lookup.get(normalized_c_type)
        if alias_type is not None:
            return alias_type
        go_type = typedef_go_type_by_lookup.get(constant_c_type)
        if go_type is not None:
            return go_type
        go_type = typedef_go_type_by_lookup.get(normalized_c_type)
        if go_type is not None:
            return go_type
    return _resolve_constant_type(value=value, type_mapping=type_mapping)


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
    type_aliases: _FunctionSignatureTypeAliases,
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
                type_aliases=type_aliases,
            ),
        })
    return tuple(parameters)


def _resolve_function_parameters(
    *,
    parameter_names: tuple[str, ...],
    go_parameter_types: tuple[str, ...],
    parameter_c_types: tuple[str, ...],
    type_aliases: _FunctionSignatureTypeAliases,
) -> tuple[_ResolvedFunctionParameter, ...]:
    """Resolve function parameters into sanitized names and rendered types.

    Returns:
        Resolved parameters with both raw metadata and rendered signature types.
    """
    parameters = _build_function_parameters_context(
        parameter_names=parameter_names,
        go_parameter_types=go_parameter_types,
        parameter_c_types=parameter_c_types,
        type_aliases=type_aliases,
    )
    return tuple(
        _ResolvedFunctionParameter(
            raw_name=raw_name or context["name"],
            name=context["name"],
            type=context["type"],
            go_type=go_type,
            c_type=c_type,
        )
        for raw_name, go_type, c_type, context in zip(
            parameter_names,
            go_parameter_types,
            parameter_c_types,
            parameters,
            strict=True,
        )
    )


def _resolve_callback_go_type(
    *,
    c_type: str,
    callback_type_context: _CallbackTypeContext,
) -> str | None:
    """Resolve one callback parameter or result C type to a Go type.

    Returns:
        Go type used in callback helper signatures, or `None` for `void`.
    """
    parsed_function_pointer = parse_function_pointer_c_type(c_type)
    if parsed_function_pointer is not None:
        return "uintptr"

    normalized_c_type = normalize_c_type_for_lookup(c_type)
    underlying_typedef_c_type = callback_type_context.typedef_c_type_by_lookup.get(
        normalized_c_type
    )
    if underlying_typedef_c_type is not None:
        parsed_underlying_callback = parse_function_pointer_c_type(underlying_typedef_c_type)
        if parsed_underlying_callback is not None:
            return "uintptr"
    primitive_type = _CALLBACK_PRIMITIVE_GO_TYPE_BY_C_TYPE.get(normalized_c_type)
    if primitive_type is not None or normalized_c_type in _CALLBACK_PRIMITIVE_GO_TYPE_BY_C_TYPE:
        return primitive_type
    typedef_go_type = callback_type_context.typedef_go_type_by_lookup.get(c_type)
    if typedef_go_type is None:
        typedef_go_type = callback_type_context.typedef_go_type_by_lookup.get(normalized_c_type)
    if typedef_go_type is not None:
        return typedef_go_type

    typedef_name = extract_pointer_typedef_name(c_type)
    if typedef_name is not None:
        opaque_alias = callback_type_context.type_aliases["opaque"].get(typedef_name)
        return opaque_alias or "uintptr"

    return _resolve_function_signature_type(
        go_type="uintptr",
        c_type=c_type,
        type_aliases=callback_type_context.type_aliases,
    )


def _build_callback_function_type(
    *,
    c_type: str,
    callback_type_context: _CallbackTypeContext,
) -> str:
    """Build one Go `func` type from a callback C type spelling.

    Returns:
        Rendered Go function type string for the callback parameter.

    Raises:
        RendererError: The callback signature contains unsupported parameter types.
    """
    parsed = parse_function_pointer_c_type(c_type)
    if parsed is None:
        underlying_typedef_c_type = callback_type_context.typedef_c_type_by_lookup.get(
            normalize_c_type_for_lookup(c_type)
        )
        if underlying_typedef_c_type is not None:
            parsed = parse_function_pointer_c_type(underlying_typedef_c_type)
    if parsed is None:
        message = f"callback helper parameter must be a function pointer, got `{c_type}`"
        raise RendererError(message)
    result_c_type, _, parameter_c_types = parsed
    parameter_types: list[str] = []
    for parameter_c_type in parameter_c_types:
        parameter_go_type = _resolve_callback_go_type(
            c_type=parameter_c_type,
            callback_type_context=callback_type_context,
        )
        if parameter_go_type is None:
            message = (
                "callback helper parameter has unsupported callback parameter type "
                f"`{parameter_c_type}`"
            )
            raise RendererError(message)
        parameter_types.append(parameter_go_type)

    result_go_type = _resolve_callback_go_type(
        c_type=result_c_type,
        callback_type_context=callback_type_context,
    )
    parameter_list = ", ".join(parameter_types)
    if result_go_type is None:
        return f"func({parameter_list})"
    return f"func({parameter_list}) {result_go_type}"


def _is_buffer_helper_pointer_type(c_type: str) -> bool:
    """Check whether one parameter type is a supported `const void*` input.

    Returns:
        `True` when the parameter should be eligible for `[]byte` helper wrapping.
    """
    return normalize_c_type_for_lookup(c_type) == _BUFFER_HELPER_POINTER_C_TYPE


def _get_required_parameter(
    *,
    helper_name: str,
    parameter_role: str,
    parameter_name: str,
    parameter_by_raw_name: Mapping[str, _ResolvedFunctionParameter],
) -> _ResolvedFunctionParameter:
    """Fetch one helper-targeted parameter or raise a stable renderer error.

    Returns:
        Matching resolved function parameter.

    Raises:
        RendererError: The named parameter does not exist on the function.
    """
    parameter = parameter_by_raw_name.get(parameter_name)
    if parameter is not None:
        return parameter
    message = f"buffer helper {helper_name} {parameter_role} parameter not found: {parameter_name}"
    raise RendererError(message)


def _validate_buffer_helper_pair(
    *,
    helper_name: str,
    pair_names: tuple[str, str],
    pointer_parameter: _ResolvedFunctionParameter,
    length_parameter: _ResolvedFunctionParameter,
    seen_targeted_pointers: set[str],
) -> None:
    """Validate one configured pointer/length pair for buffer helper generation.

    Raises:
        RendererError: The configured pair is invalid for helper generation.
    """
    pointer_name, length_name = pair_names
    if pointer_parameter.raw_name in seen_targeted_pointers:
        message = (
            f"buffer helper {helper_name} pointer parameter configured more than once: "
            f"{pointer_name}"
        )
        raise RendererError(message)
    seen_targeted_pointers.add(pointer_parameter.raw_name)
    if not _is_buffer_helper_pointer_type(pointer_parameter.c_type):
        message = (
            f"buffer helper {helper_name} parameter {pointer_name} "
            f"must be `const void *`, got `{pointer_parameter.c_type}`"
        )
        raise RendererError(message)
    if pointer_parameter.go_type != "uintptr":
        message = (
            f"buffer helper {helper_name} parameter {pointer_name} "
            f"must map to uintptr, got `{pointer_parameter.go_type}`"
        )
        raise RendererError(message)
    if length_parameter.go_type not in _BUFFER_HELPER_LENGTH_GO_TYPES:
        message = (
            f"buffer helper {helper_name} parameter {length_name} "
            f"has unsupported length type `{length_parameter.go_type}`"
        )
        raise RendererError(message)


def _validate_buffer_helper_pairs(
    *,
    helper_name: str,
    pairs: tuple[tuple[str, str], ...],
    parameter_by_raw_name: Mapping[str, _ResolvedFunctionParameter],
) -> None:
    """Validate all configured pointer/length pairs for one helper."""
    seen_targeted_pointers: set[str] = set()
    for pointer_name, length_name in pairs:
        pointer_parameter = _get_required_parameter(
            helper_name=helper_name,
            parameter_role="pointer",
            parameter_name=pointer_name,
            parameter_by_raw_name=parameter_by_raw_name,
        )
        length_parameter = _get_required_parameter(
            helper_name=helper_name,
            parameter_role="length",
            parameter_name=length_name,
            parameter_by_raw_name=parameter_by_raw_name,
        )
        _validate_buffer_helper_pair(
            helper_name=helper_name,
            pair_names=(pointer_name, length_name),
            pointer_parameter=pointer_parameter,
            length_parameter=length_parameter,
            seen_targeted_pointers=seen_targeted_pointers,
        )


def _build_buffer_helper_call_context(
    *,
    resolved_parameters: tuple[_ResolvedFunctionParameter, ...],
    pair_by_pointer: Mapping[str, tuple[str, str]],
    pointer_by_length: Mapping[str, str],
    parameter_by_raw_name: Mapping[str, _ResolvedFunctionParameter],
) -> tuple[
    tuple[_FunctionParameterContext, ...],
    tuple[_HelperLocalContext, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    """Build rendered parameter/call context for one helper wrapper.

    Returns:
        Wrapper parameters, local variable declarations, slice parameter names,
        and low-level call arguments.
    """
    wrapper_parameters: list[_FunctionParameterContext] = []
    locals_context: list[_HelperLocalContext] = []
    slice_parameter_names: list[str] = []
    call_arguments: list[str] = []

    for parameter in resolved_parameters:
        pair = pair_by_pointer.get(parameter.raw_name)
        if pair is not None:
            wrapper_parameters.append({"name": parameter.name, "type": "[]byte"})
            locals_context.extend((
                {"name": f"{parameter.name}_ptr", "value": "uintptr(0)"},
                {"name": f"{parameter.name}_len", "value": parameter.name},
            ))
            slice_parameter_names.append(parameter.name)
            call_arguments.append(f"{parameter.name}_ptr")
            continue

        pointer_name = pointer_by_length.get(parameter.raw_name)
        if pointer_name is not None:
            pointer_parameter = parameter_by_raw_name[pointer_name]
            call_arguments.append(f"{parameter.type}(len({pointer_parameter.name}_len))")
            continue

        wrapper_parameters.append({"name": parameter.name, "type": parameter.type})
        call_arguments.append(parameter.name)

    return (
        tuple(wrapper_parameters),
        tuple(locals_context),
        tuple(slice_parameter_names),
        tuple(call_arguments),
    )


def _build_function_helper_context(
    *,
    function_identifier: str,
    function: FunctionDecl,
    pointer_length_pairs: tuple[tuple[str, str], ...],
    type_aliases: _FunctionSignatureTypeAliases,
) -> _FunctionHelperContext:
    """Build one rendered helper context for a low-level function.

    Returns:
        Rendered helper context for the template.
    """
    resolved_parameters = _resolve_function_parameters(
        parameter_names=function.parameter_names,
        go_parameter_types=function.go_parameter_types,
        parameter_c_types=function.parameter_c_types,
        type_aliases=type_aliases,
    )
    parameter_by_raw_name = {parameter.raw_name: parameter for parameter in resolved_parameters}
    _validate_buffer_helper_pairs(
        helper_name=function.name,
        pairs=pointer_length_pairs,
        parameter_by_raw_name=parameter_by_raw_name,
    )
    pair_by_pointer = {
        pointer_name: (pointer_name, length_name)
        for pointer_name, length_name in pointer_length_pairs
    }
    pointer_by_length = {
        length_name: pointer_name for pointer_name, length_name in pointer_length_pairs
    }
    wrapper_parameters, locals_context, slice_parameter_names, call_arguments = (
        _build_buffer_helper_call_context(
            resolved_parameters=resolved_parameters,
            pair_by_pointer=pair_by_pointer,
            pointer_by_length=pointer_by_length,
            parameter_by_raw_name=parameter_by_raw_name,
        )
    )
    result_type = (
        _resolve_function_signature_type(
            go_type=function.go_result_type,
            c_type=function.result_c_type,
            type_aliases=type_aliases,
        )
        if function.go_result_type is not None
        else None
    )
    return {
        "identifier": f"{function_identifier}_bytes",
        "target_identifier": function_identifier,
        "parameters": wrapper_parameters,
        "result_type": result_type,
        "result_suffix": "" if result_type is None else f" {result_type}",
        "locals": locals_context,
        "slice_parameters": slice_parameter_names,
        "callback_parameters": (),
        "call_arguments": call_arguments,
    }


def _get_required_callback_parameter(
    *,
    helper_name: str,
    parameter_name: str,
    parameter_by_raw_name: Mapping[str, _ResolvedFunctionParameter],
) -> _ResolvedFunctionParameter:
    """Fetch one callback helper target parameter or raise a stable error.

    Returns:
        Matching resolved function parameter.

    Raises:
        RendererError: The named parameter does not exist on the function.
    """
    parameter = parameter_by_raw_name.get(parameter_name)
    if parameter is not None:
        return parameter
    message = f"callback helper {helper_name} parameter not found: {parameter_name}"
    raise RendererError(message)


def _validate_callback_helper_parameters(
    *,
    helper_name: str,
    parameter_names: tuple[str, ...],
    parameter_by_raw_name: Mapping[str, _ResolvedFunctionParameter],
    typedef_c_type_by_lookup: Mapping[str, str],
) -> None:
    """Validate callback helper target parameters for one helper.

    Raises:
        RendererError: A targeted parameter is missing, duplicated, or not a callback.
    """
    seen_parameters: set[str] = set()
    for parameter_name in parameter_names:
        parameter = _get_required_callback_parameter(
            helper_name=helper_name,
            parameter_name=parameter_name,
            parameter_by_raw_name=parameter_by_raw_name,
        )
        if parameter.raw_name in seen_parameters:
            message = (
                f"callback helper {helper_name} parameter configured more than once: "
                f"{parameter_name}"
            )
            raise RendererError(message)
        seen_parameters.add(parameter.raw_name)
        parameter_callback_c_type = parameter.c_type
        if not is_function_pointer_c_type(parameter_callback_c_type):
            parameter_callback_c_type = typedef_c_type_by_lookup.get(
                normalize_c_type_for_lookup(parameter.c_type),
                parameter.c_type,
            )
        if not is_function_pointer_c_type(parameter_callback_c_type):
            message = (
                f"callback helper {helper_name} parameter {parameter_name} "
                f"must be a function pointer, got `{parameter.c_type}`"
            )
            raise RendererError(message)


def _build_callback_helper_context(
    *,
    function_identifier: str,
    function: FunctionDecl,
    callback_parameters: tuple[str, ...],
    callback_type_context: _CallbackTypeContext,
) -> _FunctionHelperContext:
    """Build one rendered helper context for callback-handle conversion.

    Returns:
        Rendered helper context for the template.
    """
    resolved_parameters = _resolve_function_parameters(
        parameter_names=function.parameter_names,
        go_parameter_types=function.go_parameter_types,
        parameter_c_types=function.parameter_c_types,
        type_aliases=callback_type_context.type_aliases,
    )
    parameter_by_raw_name = {parameter.raw_name: parameter for parameter in resolved_parameters}
    _validate_callback_helper_parameters(
        helper_name=function.name,
        parameter_names=callback_parameters,
        parameter_by_raw_name=parameter_by_raw_name,
        typedef_c_type_by_lookup=callback_type_context.typedef_c_type_by_lookup,
    )
    targeted_callbacks = set(callback_parameters)

    wrapper_parameters: list[_FunctionParameterContext] = []
    locals_context: list[_HelperLocalContext] = []
    call_arguments: list[str] = []
    for parameter in resolved_parameters:
        if parameter.raw_name not in targeted_callbacks:
            wrapper_parameters.append({"name": parameter.name, "type": parameter.type})
            call_arguments.append(parameter.name)
            continue
        wrapper_parameters.append({
            "name": parameter.name,
            "type": _build_callback_function_type(
                c_type=parameter.c_type,
                callback_type_context=callback_type_context,
            ),
        })
        locals_context.append({
            "name": f"{parameter.name}_callback",
            "value": "uintptr(0)",
        })
        call_arguments.append(f"{parameter.name}_callback")

    result_type = (
        _resolve_function_signature_type(
            go_type=function.go_result_type,
            c_type=function.result_c_type,
            type_aliases=callback_type_context.type_aliases,
        )
        if function.go_result_type is not None
        else None
    )
    return {
        "identifier": f"{function_identifier}_callbacks",
        "target_identifier": function_identifier,
        "parameters": tuple(wrapper_parameters),
        "result_type": result_type,
        "result_suffix": "" if result_type is None else f" {result_type}",
        "locals": tuple(locals_context),
        "slice_parameters": (),
        "callback_parameters": callback_parameters,
        "call_arguments": tuple(call_arguments),
    }


def _build_render_identifiers(
    declarations: ParsedDeclarations,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Build deterministic identifiers for each rendered declaration category.

    Returns:
        Type, constant, function, and runtime-var identifier tuples.
    """
    return (
        build_unique_identifiers(
            tuple(typedef.name for typedef in declarations.typedefs),
            fallback_prefix="type",
        ),
        build_unique_identifiers(
            tuple(constant.name for constant in declarations.constants),
            fallback_prefix="const",
        ),
        build_unique_identifiers(
            tuple(function.name for function in declarations.functions),
            fallback_prefix="func",
        ),
        build_unique_identifiers(
            tuple(runtime_var.name for runtime_var in declarations.runtime_vars),
            fallback_prefix="var",
        ),
    )


def _build_function_signature_type_aliases(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    type_mapping: TypeMappingOptions,
) -> _FunctionSignatureTypeAliases:
    """Build render-time alias lookups used to rewrite function signatures.

    Returns:
        Alias lookup tables for record, opaque, enum, and function-pointer slots.
    """
    emitted_record_typedef_names = _build_emitted_record_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
    )
    emitted_opaque_struct_typedef_names = _build_emitted_opaque_struct_typedef_names(
        declarations=declarations,
        emitted_record_typedef_names=emitted_record_typedef_names,
    )
    emitted_strict_enum_typedef_names = _build_emitted_strict_enum_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
        type_mapping=type_mapping,
    )
    record_alias_type_by_typedef_name = _build_record_alias_type_by_typedef_name(
        declarations=declarations,
        type_identifiers=type_identifiers,
        emitted_record_typedef_names=emitted_record_typedef_names,
    )
    return {
        "record": record_alias_type_by_typedef_name,
        "opaque": _build_opaque_alias_type_by_typedef_name(
            emitted_opaque_struct_typedef_names=emitted_opaque_struct_typedef_names,
            record_alias_type_by_typedef_name=record_alias_type_by_typedef_name,
        ),
        "enum": _build_enum_alias_type_by_typedef_name(
            declarations=declarations,
            type_identifiers=type_identifiers,
            emitted_strict_enum_typedef_names=emitted_strict_enum_typedef_names,
        ),
        "function_pointer": _build_function_pointer_alias_type_by_lookup(
            declarations=declarations,
            type_identifiers=type_identifiers,
            emit_kinds=emit_kinds,
        ),
    }


def _build_typedef_render_helpers(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    type_mapping: TypeMappingOptions,
) -> tuple[
    _FunctionSignatureTypeAliases,
    dict[str, str],
    dict[str, str],
    set[str],
    set[str],
]:
    """Build typedef-related lookups and emitted-name sets used during rendering.

    Returns:
        Function-signature alias lookups, typedef alias lookup, typedef Go-type
        lookup, opaque typedef names, and strict enum typedef names.
    """
    emitted_record_typedef_names = _build_emitted_record_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
    )
    emitted_opaque_struct_typedef_names = _build_emitted_opaque_struct_typedef_names(
        declarations=declarations,
        emitted_record_typedef_names=emitted_record_typedef_names,
    )
    emitted_strict_enum_typedef_names = _build_emitted_strict_enum_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
        type_mapping=type_mapping,
    )
    return (
        _build_function_signature_type_aliases(
            emit_kinds=emit_kinds,
            declarations=declarations,
            type_identifiers=type_identifiers,
            type_mapping=type_mapping,
        ),
        _build_typedef_alias_type_by_lookup(
            declarations=declarations,
            type_identifiers=type_identifiers,
            emit_kinds=emit_kinds,
        ),
        _build_typedef_go_type_by_lookup(declarations),
        emitted_opaque_struct_typedef_names,
        emitted_strict_enum_typedef_names,
    )


def _build_function_helpers(
    *,
    helper_build_context: _HelperBuildContext,
) -> tuple[_FunctionHelperContext, ...]:
    """Build rendered helper contexts after validating configured helper specs.

    Returns:
        Helper contexts consumed by the main Go template.

    Raises:
        RendererError: A helper target or parameter mapping is invalid.
    """
    helpers = helper_build_context.helpers
    if not helpers.buffer_inputs and not helpers.callback_inputs:
        return ()

    functions_by_name = {
        function.name: function for function in helper_build_context.declarations.functions
    }
    helper_contexts: list[_FunctionHelperContext] = []
    for helper in helpers.buffer_inputs:
        function = functions_by_name.get(helper.function)
        if function is None:
            message = f"buffer helper target function not found: {helper.function}"
            raise RendererError(message)
        helper_contexts.append(
            _build_function_helper_context(
                function_identifier=helper_build_context.function_identifier_by_name[function.name],
                function=function,
                pointer_length_pairs=tuple((pair.pointer, pair.length) for pair in helper.pairs),
                type_aliases=helper_build_context.callback_type_context.type_aliases,
            )
        )
    for helper in helpers.callback_inputs:
        function = functions_by_name.get(helper.function)
        if function is None:
            message = f"callback helper target function not found: {helper.function}"
            raise RendererError(message)
        helper_contexts.append(
            _build_callback_helper_context(
                function_identifier=helper_build_context.function_identifier_by_name[function.name],
                function=function,
                callback_parameters=helper.parameters,
                callback_type_context=helper_build_context.callback_type_context,
            )
        )
    return tuple(helper_contexts)


def _build_context(
    *,
    package: str,
    lib_id: str,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    options: RenderOptions,
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
    type_identifiers, constant_identifiers, function_identifiers, runtime_var_identifiers = (
        _build_render_identifiers(declarations)
    )
    (
        function_signature_type_aliases,
        typedef_alias_type_by_lookup,
        typedef_go_type_by_lookup,
        emitted_opaque_struct_typedef_names,
        emitted_strict_enum_typedef_names,
    ) = _build_typedef_render_helpers(
        emit_kinds=emit_kinds,
        declarations=declarations,
        type_identifiers=type_identifiers,
        type_mapping=options.type_mapping,
    )
    function_identifier_by_name = {
        function.name: identifier
        for function, identifier in zip(declarations.functions, function_identifiers, strict=True)
    }
    helper_contexts = _build_function_helpers(
        helper_build_context=_HelperBuildContext(
            function_identifier_by_name=function_identifier_by_name,
            declarations=declarations,
            helpers=options.helpers,
            callback_type_context=_CallbackTypeContext(
                type_aliases=function_signature_type_aliases,
                typedef_go_type_by_lookup=typedef_go_type_by_lookup,
                typedef_c_type_by_lookup=_build_typedef_c_type_by_lookup(declarations),
            ),
        ),
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
                "expression": _resolve_constant_expression(
                    constant_expression=constant.go_expression,
                    value=constant.value,
                    const_type=_resolve_typed_constant_type(
                        constant_c_type=constant.c_type,
                        value=constant.value,
                        type_mapping=options.type_mapping,
                        typedef_alias_type_by_lookup=typedef_alias_type_by_lookup,
                        typedef_go_type_by_lookup=typedef_go_type_by_lookup,
                    ),
                ),
                "const_type": _resolve_typed_constant_type(
                    constant_c_type=constant.c_type,
                    value=constant.value,
                    type_mapping=options.type_mapping,
                    typedef_alias_type_by_lookup=typedef_alias_type_by_lookup,
                    typedef_go_type_by_lookup=typedef_go_type_by_lookup,
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
                    type_aliases=function_signature_type_aliases,
                ),
                "result_type": _resolve_function_signature_type(
                    go_type=function.go_result_type,
                    c_type=function.result_c_type,
                    type_aliases=function_signature_type_aliases,
                )
                if function.go_result_type is not None
                else None,
                "comment_lines": _normalize_comment_lines(function.comment),
            }
            for function, identifier in zip(
                declarations.functions, function_identifiers, strict=True
            )
        ),
        "helpers": helper_contexts,
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
        template = _get_environment().get_template(template_name)
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
    options: RenderOptions | None = None,
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
        options=options
        if options is not None
        else RenderOptions(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(),
        ),
    )
    return render_template(_MAIN_TEMPLATE_NAME, context)
