# Copyright (c) 2026 purego-gen contributors.

"""Shared helper rendering and function-signature resolution utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypedDict

from purego_gen.c_type_utils import (
    extract_double_pointer_typedef_name,
    extract_pointer_typedef_name,
    is_function_pointer_c_type,
    normalize_c_type_for_lookup,
    normalize_function_pointer_c_type_for_lookup,
    parse_function_pointer_c_type,
)
from purego_gen.identifier_utils import GO_KEYWORDS, allocate_unique_identifier, is_go_identifier

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.config_model import GeneratorHelpers
    from purego_gen.model import FunctionDecl, ParsedDeclarations

from purego_gen.config_model import CallbackInputHelper

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
    "int8_t": "int8",
    "uint8_t": "uint8",
    "int16_t": "int16",
    "uint16_t": "uint16",
    "int32_t": "int32",
    "uint32_t": "uint32",
    "int64_t": "int64",
    "uint64_t": "uint64",
    "uintptr_t": "uintptr",
    # Go has no signed pointer-width integer; uintptr is the only pointer-width type.
    "intptr_t": "uintptr",
}


class HelperRenderingError(RuntimeError):
    """Raised when helper rendering metadata is invalid."""


class FunctionParameterContext(TypedDict):
    """Rendered function parameter used by templates."""

    name: str
    type: str
    c_type_comment: str


class HelperLocalContext(TypedDict):
    """Rendered helper-local variable used by templates."""

    name: str
    value: str


class FunctionHelperContext(TypedDict):
    """Rendered helper wrapper context consumed by templates."""

    identifier: str
    target_identifier: str
    parameters: tuple[FunctionParameterContext, ...]
    result_type: str | None
    result_c_type_comment: str
    result_suffix: str
    locals: tuple[HelperLocalContext, ...]
    slice_parameters: tuple[str, ...]
    callback_parameters: tuple[str, ...]
    call_arguments: tuple[str, ...]


class OwnedStringReturnHelperContext(TypedDict):
    """Rendered owned-string-return helper context consumed by templates."""

    identifier: str
    target_identifier: str
    free_func_identifier: str
    parameters: tuple[FunctionParameterContext, ...]
    call_arguments: tuple[str, ...]


class FunctionSignatureTypeAliases(TypedDict):
    """Alias lookups used to rewrite rendered function signatures."""

    record: Mapping[str, str]
    opaque: Mapping[str, str]
    enum: Mapping[str, str]
    function_pointer: Mapping[str, str]
    opaque_pointer: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ResolvedFunctionParameter:
    """Resolved function parameter with both raw and rendered metadata."""

    raw_name: str
    name: str
    type: str
    go_type: str
    c_type: str


@dataclass(frozen=True, slots=True)
class HelperTypeResolver:
    """Resolve render-time Go types for helper generation and function signatures."""

    type_aliases: FunctionSignatureTypeAliases
    typedef_go_type_by_lookup: Mapping[str, str]
    typedef_c_type_by_lookup: Mapping[str, str]

    def resolve_parameter_type(self, *, go_type: str, c_type: str) -> str:
        """Resolve one function parameter/result type for rendering.

        Returns:
            Rendered Go type for the parameter or result slot.
        """
        alias = self._resolve_alias(go_type=go_type, c_type=c_type)
        if alias is not None:
            return alias

        if go_type != "uintptr":
            return go_type

        if is_function_pointer_c_type(c_type):
            try:
                return self.build_callback_func_type(c_type=c_type)
            except HelperRenderingError:
                return go_type

        return self._resolve_opaque_pointer_type(c_type=c_type, fallback=go_type)

    def _resolve_alias(self, *, go_type: str, c_type: str) -> str | None:
        """Look up a type alias for the given C type spelling.

        Returns:
            Matching Go alias or ``None`` when no alias applies.
        """
        normalized_c_type = normalize_c_type_for_lookup(c_type)
        if go_type == "int32":
            enum_alias = self.type_aliases["enum"].get(normalized_c_type)
            if enum_alias is not None:
                return enum_alias

        record_alias = self.type_aliases["record"].get(normalized_c_type)
        if record_alias is not None:
            return record_alias

        function_pointer_alias = self.type_aliases["function_pointer"].get(
            normalize_function_pointer_c_type_for_lookup(c_type)
        )
        if function_pointer_alias is not None:
            return function_pointer_alias

        return self.type_aliases["opaque_pointer"].get(normalized_c_type)

    def _resolve_opaque_pointer_type(self, *, c_type: str, fallback: str) -> str:
        """Resolve a pointer-to-typedef C type to its Go alias with prefix.

        Returns:
            Go type with ``*`` or ``**`` prefix, or *fallback* when unresolved.
        """
        double_pointer_name = extract_double_pointer_typedef_name(c_type)
        if double_pointer_name is not None:
            alias = (
                self.type_aliases["opaque"].get(double_pointer_name)
                or self.type_aliases["opaque_pointer"].get(double_pointer_name)
                or self.type_aliases["record"].get(double_pointer_name)
            )
            if alias is not None:
                return f"**{alias}"
            return fallback

        typedef_name = extract_pointer_typedef_name(c_type)
        if typedef_name is None:
            return fallback
        alias = (
            self.type_aliases["opaque"].get(typedef_name)
            or self.type_aliases["opaque_pointer"].get(typedef_name)
            or self.type_aliases["record"].get(typedef_name)
        )
        if alias is not None:
            return f"*{alias}"
        return fallback

    def build_callback_func_type(self, *, c_type: str) -> str:
        """Build one Go `func` type from a callback C type spelling.

        Returns:
            Rendered Go callback function type.

        Raises:
            HelperRenderingError: The callback C type is unsupported.
        """
        parsed = parse_function_pointer_c_type(c_type)
        if parsed is None:
            underlying_typedef_c_type = self.typedef_c_type_by_lookup.get(
                normalize_c_type_for_lookup(c_type)
            )
            if underlying_typedef_c_type is not None:
                parsed = parse_function_pointer_c_type(underlying_typedef_c_type)
        if parsed is None:
            message = f"callback helper parameter must be a function pointer, got `{c_type}`"
            raise HelperRenderingError(message)

        result_c_type, _, parameter_c_types = parsed
        parameter_types: list[str] = []
        for parameter_c_type in parameter_c_types:
            parameter_go_type = self._resolve_callback_go_type(c_type=parameter_c_type)
            if parameter_go_type is None:
                message = (
                    "callback helper parameter has unsupported callback parameter type "
                    f"`{parameter_c_type}`"
                )
                raise HelperRenderingError(message)
            parameter_types.append(parameter_go_type)

        result_go_type = self._resolve_callback_go_type(c_type=result_c_type)
        parameter_list = ", ".join(parameter_types)
        if result_go_type is None:
            return f"func({parameter_list})"
        return f"func({parameter_list}) {result_go_type}"

    def _resolve_callback_go_type(self, *, c_type: str) -> str | None:
        parsed_function_pointer = parse_function_pointer_c_type(c_type)
        if parsed_function_pointer is not None:
            return "uintptr"

        normalized_c_type = normalize_c_type_for_lookup(c_type)
        underlying_typedef_c_type = self.typedef_c_type_by_lookup.get(normalized_c_type)
        if underlying_typedef_c_type is not None:
            resolved = self._resolve_underlying_typedef_go_type(underlying_typedef_c_type)
            if resolved is not None:
                return resolved

        primitive_type = _CALLBACK_PRIMITIVE_GO_TYPE_BY_C_TYPE.get(normalized_c_type)
        if primitive_type is not None or normalized_c_type in _CALLBACK_PRIMITIVE_GO_TYPE_BY_C_TYPE:
            return primitive_type

        typedef_go_type = self.typedef_go_type_by_lookup.get(c_type)
        if typedef_go_type is None:
            typedef_go_type = self.typedef_go_type_by_lookup.get(normalized_c_type)
        if typedef_go_type is not None:
            return typedef_go_type
        return self._resolve_opaque_pointer_type(c_type=c_type, fallback="uintptr")

    def _resolve_underlying_typedef_go_type(self, underlying_c_type: str) -> str | None:
        """Resolve an underlying typedef C type to its Go type for callbacks.

        Returns:
            Go type string, or ``None`` when unresolved.
        """
        parsed_underlying_callback = parse_function_pointer_c_type(underlying_c_type)
        if parsed_underlying_callback is not None:
            return "uintptr"
        normalized = normalize_c_type_for_lookup(underlying_c_type)
        primitive = _CALLBACK_PRIMITIVE_GO_TYPE_BY_C_TYPE.get(normalized)
        if primitive is not None or normalized in _CALLBACK_PRIMITIVE_GO_TYPE_BY_C_TYPE:
            return primitive
        go_type = self.typedef_go_type_by_lookup.get(underlying_c_type)
        if go_type is None:
            go_type = self.typedef_go_type_by_lookup.get(normalized)
        return go_type


def build_typedef_c_type_by_lookup(declarations: ParsedDeclarations) -> dict[str, str]:
    """Build typedef C-type lookup keyed by typedef name and normalized spelling.

    Returns:
        Mapping from typedef names and normalized spellings to underlying C types.
    """
    c_type_by_lookup: dict[str, str] = {}
    for typedef in declarations.typedefs:
        c_type_by_lookup[typedef.name] = typedef.c_type
        c_type_by_lookup[normalize_c_type_for_lookup(typedef.name)] = typedef.c_type
        c_type_by_lookup[normalize_c_type_for_lookup(typedef.c_type)] = typedef.c_type
    return c_type_by_lookup


def build_function_parameters_context(
    *,
    parameter_names: tuple[str, ...],
    go_parameter_types: tuple[str, ...],
    parameter_c_types: tuple[str, ...],
    type_resolver: HelperTypeResolver,
) -> tuple[FunctionParameterContext, ...]:
    """Build resolved parameter context for one function signature.

    Returns:
        Rendered parameter contexts in declaration order.

    Raises:
        HelperRenderingError: Function parameter metadata is inconsistent.
    """
    if not (len(parameter_names) == len(go_parameter_types) == len(parameter_c_types)):
        message = (
            "function parameter metadata length mismatch: "
            f"names={len(parameter_names)}, "
            f"go_types={len(go_parameter_types)}, c_types={len(parameter_c_types)}"
        )
        raise HelperRenderingError(message)

    seen_names: set[str] = set()
    parameters: list[FunctionParameterContext] = []
    for index, (parameter_name, go_parameter_type, parameter_c_type) in enumerate(
        zip(parameter_names, go_parameter_types, parameter_c_types, strict=True),
        start=1,
    ):
        resolved_name = sanitize_function_parameter_name(parameter_name, index=index)
        resolved_name = allocate_unique_identifier(resolved_name, seen=seen_names)
        resolved_type = type_resolver.resolve_parameter_type(
            go_type=go_parameter_type,
            c_type=parameter_c_type,
        )
        parameters.append({
            "name": resolved_name,
            "type": resolved_type,
            "c_type_comment": parameter_c_type if resolved_type == "uintptr" else "",
        })
    return tuple(parameters)


def sanitize_function_parameter_name(raw_name: str, *, index: int) -> str:
    """Sanitize one C parameter name into a stable Go identifier.

    Returns:
        Stable Go identifier with deterministic fallback naming.
    """
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", raw_name)
    if not normalized or normalized == "_" or normalized[0].isdigit():
        normalized = f"arg{index}"
    if not is_go_identifier(normalized):
        normalized = f"arg{index}"
    if normalized in GO_KEYWORDS:
        normalized = f"{normalized}_"
    return normalized


def build_function_helpers(
    *,
    function_identifier_by_name: Mapping[str, str],
    declarations: ParsedDeclarations,
    helpers: GeneratorHelpers,
    type_resolver: HelperTypeResolver,
    callback_param_type_overrides: Mapping[tuple[str, str], str] | None = None,
) -> tuple[FunctionHelperContext, ...]:
    """Build rendered helper contexts after validating configured helper specs.

    Returns:
        Rendered helper wrapper contexts in emission order.

    Raises:
        HelperRenderingError: Helper targets or parameter mappings are invalid.
    """
    if not helpers.buffer_inputs and not helpers.callback_inputs:
        return ()

    functions_by_name = {function.name: function for function in declarations.functions}
    helper_contexts: list[FunctionHelperContext] = []

    for helper in helpers.buffer_inputs:
        function = functions_by_name.get(helper.function)
        if function is None:
            message = f"buffer helper target function not found: {helper.function}"
            raise HelperRenderingError(message)
        helper_contexts.append(
            _build_buffer_helper_context(
                function_identifier=function_identifier_by_name[function.name],
                function=function,
                pointer_length_pairs=tuple((pair.pointer, pair.length) for pair in helper.pairs),
                type_resolver=type_resolver,
            )
        )

    effective_overrides: Mapping[tuple[str, str], str] = callback_param_type_overrides or {}
    for helper in helpers.callback_inputs:
        function = functions_by_name.get(helper.function)
        if function is None:
            message = f"callback helper target function not found: {helper.function}"
            raise HelperRenderingError(message)
        helper_contexts.append(
            _build_callback_helper_context(
                function_identifier=function_identifier_by_name[function.name],
                function=function,
                callback_parameters=helper.parameters,
                type_resolver=type_resolver,
                callback_param_type_overrides=effective_overrides,
            )
        )

    return tuple(helper_contexts)


def _resolve_function_parameters(
    *,
    parameter_names: tuple[str, ...],
    go_parameter_types: tuple[str, ...],
    parameter_c_types: tuple[str, ...],
    type_resolver: HelperTypeResolver,
) -> tuple[ResolvedFunctionParameter, ...]:
    parameters = build_function_parameters_context(
        parameter_names=parameter_names,
        go_parameter_types=go_parameter_types,
        parameter_c_types=parameter_c_types,
        type_resolver=type_resolver,
    )
    return tuple(
        ResolvedFunctionParameter(
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


def _is_buffer_helper_pointer_type(c_type: str) -> bool:
    return normalize_c_type_for_lookup(c_type) == _BUFFER_HELPER_POINTER_C_TYPE


def _get_required_buffer_parameter(
    *,
    helper_name: str,
    parameter_role: str,
    parameter_name: str,
    parameter_by_raw_name: Mapping[str, ResolvedFunctionParameter],
) -> ResolvedFunctionParameter:
    parameter = parameter_by_raw_name.get(parameter_name)
    if parameter is not None:
        return parameter
    message = f"buffer helper {helper_name} {parameter_role} parameter not found: {parameter_name}"
    raise HelperRenderingError(message)


def _validate_buffer_helper_pair(
    *,
    helper_name: str,
    pair_names: tuple[str, str],
    pointer_parameter: ResolvedFunctionParameter,
    length_parameter: ResolvedFunctionParameter,
    seen_targeted_pointers: set[str],
) -> None:
    pointer_name, length_name = pair_names
    if pointer_parameter.raw_name in seen_targeted_pointers:
        message = (
            f"buffer helper {helper_name} pointer parameter configured more than once: "
            f"{pointer_name}"
        )
        raise HelperRenderingError(message)
    seen_targeted_pointers.add(pointer_parameter.raw_name)
    if not _is_buffer_helper_pointer_type(pointer_parameter.c_type):
        message = (
            f"buffer helper {helper_name} parameter {pointer_name} "
            f"must be `const void *`, got `{pointer_parameter.c_type}`"
        )
        raise HelperRenderingError(message)
    if pointer_parameter.go_type != "uintptr":
        message = (
            f"buffer helper {helper_name} parameter {pointer_name} "
            f"must map to uintptr, got `{pointer_parameter.go_type}`"
        )
        raise HelperRenderingError(message)
    if length_parameter.go_type not in _BUFFER_HELPER_LENGTH_GO_TYPES:
        message = (
            f"buffer helper {helper_name} parameter {length_name} "
            f"has unsupported length type `{length_parameter.go_type}`"
        )
        raise HelperRenderingError(message)


def _validate_buffer_helper_pairs(
    *,
    helper_name: str,
    pairs: tuple[tuple[str, str], ...],
    parameter_by_raw_name: Mapping[str, ResolvedFunctionParameter],
) -> None:
    seen_targeted_pointers: set[str] = set()
    for pointer_name, length_name in pairs:
        pointer_parameter = _get_required_buffer_parameter(
            helper_name=helper_name,
            parameter_role="pointer",
            parameter_name=pointer_name,
            parameter_by_raw_name=parameter_by_raw_name,
        )
        length_parameter = _get_required_buffer_parameter(
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
    resolved_parameters: tuple[ResolvedFunctionParameter, ...],
    pair_by_pointer: Mapping[str, tuple[str, str]],
    pointer_by_length: Mapping[str, str],
    parameter_by_raw_name: Mapping[str, ResolvedFunctionParameter],
) -> tuple[
    tuple[FunctionParameterContext, ...],
    tuple[HelperLocalContext, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    wrapper_parameters: list[FunctionParameterContext] = []
    locals_context: list[HelperLocalContext] = []
    slice_parameter_names: list[str] = []
    call_arguments: list[str] = []

    for parameter in resolved_parameters:
        pair = pair_by_pointer.get(parameter.raw_name)
        if pair is not None:
            wrapper_parameters.append({
                "name": parameter.name,
                "type": "[]byte",
                "c_type_comment": "",
            })
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

        wrapper_parameters.append({
            "name": parameter.name,
            "type": parameter.type,
            "c_type_comment": "",
        })
        call_arguments.append(parameter.name)

    return (
        tuple(wrapper_parameters),
        tuple(locals_context),
        tuple(slice_parameter_names),
        tuple(call_arguments),
    )


def _build_buffer_helper_context(
    *,
    function_identifier: str,
    function: FunctionDecl,
    pointer_length_pairs: tuple[tuple[str, str], ...],
    type_resolver: HelperTypeResolver,
) -> FunctionHelperContext:
    resolved_parameters = _resolve_function_parameters(
        parameter_names=function.parameter_names,
        go_parameter_types=function.go_parameter_types,
        parameter_c_types=function.parameter_c_types,
        type_resolver=type_resolver,
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
        type_resolver.resolve_parameter_type(
            go_type=function.go_result_type,
            c_type=function.result_c_type,
        )
        if function.go_result_type is not None
        else None
    )
    result_c_type_comment = function.result_c_type if result_type == "uintptr" else ""
    result_suffix = "" if result_type is None else f" {result_type}"
    return {
        "identifier": f"{function_identifier}_bytes",
        "target_identifier": function_identifier,
        "parameters": wrapper_parameters,
        "result_type": result_type,
        "result_c_type_comment": result_c_type_comment,
        "result_suffix": result_suffix,
        "locals": locals_context,
        "slice_parameters": slice_parameter_names,
        "callback_parameters": (),
        "call_arguments": call_arguments,
    }


def _get_required_callback_parameter(
    *,
    helper_name: str,
    parameter_name: str,
    parameter_by_raw_name: Mapping[str, ResolvedFunctionParameter],
) -> ResolvedFunctionParameter:
    parameter = parameter_by_raw_name.get(parameter_name)
    if parameter is not None:
        return parameter
    message = f"callback helper {helper_name} parameter not found: {parameter_name}"
    raise HelperRenderingError(message)


def _validate_callback_helper_parameters(
    *,
    helper_name: str,
    parameter_names: tuple[str, ...],
    parameter_by_raw_name: Mapping[str, ResolvedFunctionParameter],
    typedef_c_type_by_lookup: Mapping[str, str],
) -> None:
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
            raise HelperRenderingError(message)
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
            raise HelperRenderingError(message)


def _build_callback_helper_context(
    *,
    function_identifier: str,
    function: FunctionDecl,
    callback_parameters: tuple[str, ...],
    type_resolver: HelperTypeResolver,
    callback_param_type_overrides: Mapping[tuple[str, str], str],
) -> FunctionHelperContext:
    resolved_parameters = _resolve_function_parameters(
        parameter_names=function.parameter_names,
        go_parameter_types=function.go_parameter_types,
        parameter_c_types=function.parameter_c_types,
        type_resolver=type_resolver,
    )
    parameter_by_raw_name = {parameter.raw_name: parameter for parameter in resolved_parameters}
    _validate_callback_helper_parameters(
        helper_name=function.name,
        parameter_names=callback_parameters,
        parameter_by_raw_name=parameter_by_raw_name,
        typedef_c_type_by_lookup=type_resolver.typedef_c_type_by_lookup,
    )
    targeted_callbacks = set(callback_parameters)

    wrapper_parameters: list[FunctionParameterContext] = []
    locals_context: list[HelperLocalContext] = []
    call_arguments: list[str] = []
    for parameter in resolved_parameters:
        if parameter.raw_name not in targeted_callbacks:
            wrapper_parameters.append({
                "name": parameter.name,
                "type": parameter.type,
                "c_type_comment": "",
            })
            call_arguments.append(parameter.name)
            continue
        override_type = callback_param_type_overrides.get((function.name, parameter.raw_name))
        wrapper_type = (
            override_type
            if override_type is not None
            else type_resolver.build_callback_func_type(c_type=parameter.c_type)
        )
        wrapper_parameters.append({
            "name": parameter.name,
            "type": wrapper_type,
            "c_type_comment": "",
        })
        locals_context.append({
            "name": f"{parameter.name}_callback",
            "value": "uintptr(0)",
        })
        call_arguments.append(f"{parameter.name}_callback")

    result_type = (
        type_resolver.resolve_parameter_type(
            go_type=function.go_result_type,
            c_type=function.result_c_type,
        )
        if function.go_result_type is not None
        else None
    )
    result_c_type_comment = function.result_c_type if result_type == "uintptr" else ""
    result_suffix = "" if result_type is None else f" {result_type}"
    return {
        "identifier": f"{function_identifier}_callbacks",
        "target_identifier": function_identifier,
        "parameters": tuple(wrapper_parameters),
        "result_type": result_type,
        "result_c_type_comment": result_c_type_comment,
        "result_suffix": result_suffix,
        "locals": tuple(locals_context),
        "slice_parameters": (),
        "callback_parameters": callback_parameters,
        "call_arguments": tuple(call_arguments),
    }


def find_callback_candidates(
    declarations: ParsedDeclarations,
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Find functions with function-pointer parameters.

    Returns:
        List of (func_name, [(param_name, param_c_type), ...]) for functions
        that have at least one function-pointer parameter.
    """
    typedef_lookup = build_typedef_c_type_by_lookup(declarations)
    candidates: list[tuple[str, list[tuple[str, str]]]] = []
    for func in declarations.functions:
        matching_params: list[tuple[str, str]] = []
        for param_name, param_c_type in zip(
            func.parameter_names, func.parameter_c_types, strict=True
        ):
            if is_function_pointer_c_type(param_c_type):
                matching_params.append((param_name, param_c_type))
            else:
                resolved = typedef_lookup.get(normalize_c_type_for_lookup(param_c_type))
                if resolved is not None and is_function_pointer_c_type(resolved):
                    matching_params.append((param_name, param_c_type))
        if matching_params:
            candidates.append((func.name, matching_params))
    return candidates


@dataclass(frozen=True, slots=True)
class CallbackRegistrationPattern:
    """Detected (callback, userdata, destructor) triple in a function signature."""

    function: str
    callback_param: str
    userdata_param: str | None
    destructor_param: str | None


_USERDATA_NAMES: frozenset[str] = frozenset({
    "user_data",
    "userdata",
    "userData",
    "data",
    "ctx",
    "context",
    "arg",
    "closure",
    "extra",
    "info",
    "pCtx",
    "pArg",
})
_DESTRUCTOR_NAMES: frozenset[str] = frozenset({
    "destroy",
    "destructor",
    "free",
    "release",
    "cleanup",
    "dtor",
    "dispose",
    "finalize",
    "xDestroy",
    "xDelete",
})


def detect_callback_registration_patterns(
    declarations: ParsedDeclarations,
) -> list[CallbackRegistrationPattern]:
    """Detect (callback, userdata, destructor) triples in function signatures.

    Returns:
        List of detected registration patterns.
    """
    candidates = find_callback_candidates(declarations)
    functions_by_name = {func.name: func for func in declarations.functions}
    typedef_lookup = build_typedef_c_type_by_lookup(declarations)
    patterns: list[CallbackRegistrationPattern] = []

    for func_name, matching_params in candidates:
        func = functions_by_name[func_name]
        callback_param_names = {name for name, _ in matching_params}
        all_param_names = list(func.parameter_names)
        all_param_c_types = list(func.parameter_c_types)
        param_c_type_by_name = dict(zip(all_param_names, all_param_c_types, strict=True))

        for cb_name in callback_param_names:
            userdata = _find_userdata_neighbor(cb_name, all_param_names, param_c_type_by_name)
            destructor = _find_destructor_neighbor(
                cb_name,
                all_param_names,
                param_c_type_by_name,
                callback_param_names,
                typedef_lookup,
            )
            if userdata is not None or destructor is not None:
                patterns.append(
                    CallbackRegistrationPattern(
                        function=func_name,
                        callback_param=cb_name,
                        userdata_param=userdata,
                        destructor_param=destructor,
                    )
                )

    return patterns


def _find_userdata_neighbor(
    callback_name: str,
    all_param_names: list[str],
    param_c_type_by_name: dict[str, str],
) -> str | None:
    """Find a likely userdata parameter near the callback parameter.

    Returns:
        Parameter name of the userdata candidate, or ``None``.
    """
    for name in all_param_names:
        if name == callback_name:
            continue
        normalized = normalize_c_type_for_lookup(param_c_type_by_name[name])
        if normalized in {"void *", "void*"} and name in _USERDATA_NAMES:
            return name
    return None


def _is_destructor_name(name: str) -> bool:
    """Check if a parameter name looks like a destructor.

    Returns:
        ``True`` when the name matches a known destructor pattern.
    """
    lower = name.lower()
    return any(d in lower for d in _DESTRUCTOR_NAMES)


def _find_destructor_neighbor(
    callback_name: str,
    all_param_names: list[str],
    param_c_type_by_name: dict[str, str],
    callback_param_names: set[str],
    typedef_lookup: dict[str, str],
) -> str | None:
    """Find a likely destructor parameter near the callback parameter.

    Returns:
        Parameter name of the destructor candidate, or ``None``.
    """
    for name in all_param_names:
        if name == callback_name or name not in callback_param_names:
            continue
        if _is_destructor_name(name):
            return name
    for name in all_param_names:
        if name == callback_name or name in callback_param_names:
            continue
        if not _is_destructor_name(name):
            continue
        c_type = param_c_type_by_name[name]
        if is_function_pointer_c_type(c_type):
            return name
        resolved = typedef_lookup.get(normalize_c_type_for_lookup(c_type))
        if resolved is not None and is_function_pointer_c_type(resolved):
            return name
    return None


def discover_callback_inputs(
    declarations: ParsedDeclarations,
    *,
    explicit_callback_inputs: tuple[CallbackInputHelper, ...],
) -> tuple[CallbackInputHelper, ...]:
    """Auto-discover callback input helpers for functions with function-pointer params.

    Merges with explicit ``callback_inputs``: explicit entries take priority
    for the same function name.

    Returns:
        Merged tuple of callback input helpers.
    """
    explicit_functions = {h.function for h in explicit_callback_inputs}
    candidates = find_callback_candidates(declarations)
    discovered: list[CallbackInputHelper] = []
    for func_name, matching_params in candidates:
        if func_name in explicit_functions:
            continue
        param_names = tuple(name for name, _ in matching_params)
        discovered.append(CallbackInputHelper(function=func_name, parameters=param_names))
    return (*explicit_callback_inputs, *discovered)


def build_owned_string_return_helpers(
    *,
    function_identifier_by_name: Mapping[str, str],
    declarations: ParsedDeclarations,
    helpers: GeneratorHelpers,
    type_resolver: HelperTypeResolver,
) -> tuple[tuple[OwnedStringReturnHelperContext, ...], frozenset[str]]:
    """Build rendered owned-string-return helper contexts.

    Returns:
        Tuple of (helper contexts, set of function names whose raw return type
        should be overridden to ``uintptr``).

    Raises:
        HelperRenderingError: Helper targets or configuration are invalid.
    """
    if not helpers.owned_string_returns:
        return (), frozenset()

    functions_by_name = {function.name: function for function in declarations.functions}
    helper_contexts: list[OwnedStringReturnHelperContext] = []
    override_names: set[str] = set()

    for helper in helpers.owned_string_returns:
        function = functions_by_name.get(helper.function)
        if function is None:
            message = f"owned_string_returns helper target function not found: {helper.function}"
            raise HelperRenderingError(message)

        if function.go_result_type != "string":
            message = (
                f"owned_string_returns helper target function {helper.function} "
                f"must return string, got `{function.go_result_type}`"
            )
            raise HelperRenderingError(message)

        free_function = functions_by_name.get(helper.free_func)
        if free_function is None:
            message = f"owned_string_returns helper free function not found: {helper.free_func}"
            raise HelperRenderingError(message)

        function_identifier = function_identifier_by_name[function.name]
        free_func_identifier = function_identifier_by_name[helper.free_func]

        resolved_parameters = _resolve_function_parameters(
            parameter_names=function.parameter_names,
            go_parameter_types=function.go_parameter_types,
            parameter_c_types=function.parameter_c_types,
            type_resolver=type_resolver,
        )

        parameters = tuple(
            FunctionParameterContext(
                name=param.name,
                type=param.type,
                c_type_comment=param.c_type if param.type == "uintptr" else "",
            )
            for param in resolved_parameters
        )
        call_arguments = tuple(param.name for param in resolved_parameters)

        helper_contexts.append({
            "identifier": f"{function_identifier}_string",
            "target_identifier": function_identifier,
            "free_func_identifier": free_func_identifier,
            "parameters": parameters,
            "call_arguments": call_arguments,
        })
        override_names.add(function.name)

    return tuple(helper_contexts), frozenset(override_names)
