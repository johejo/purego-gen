# Copyright (c) 2026 purego-gen contributors.

"""Template context construction for the Go source renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from purego_gen.c_type_utils import is_function_pointer_c_type
from purego_gen.constant_resolution import (
    normalize_comment_lines,
    resolve_constant_expression,
    resolve_typed_constant_type,
)
from purego_gen.emit_kinds import validate_emit_kinds
from purego_gen.helper_rendering import (
    FunctionParameterContext,
    HelperLocalContext,
    HelperRenderingError,
    HelperTypeResolver,
    build_function_helpers,
    build_function_parameters_context,
    build_owned_string_return_helpers,
    build_typedef_c_type_by_lookup,
    discover_callback_inputs,
)
from purego_gen.identifier_utils import (
    accessor_getter_name,
    accessor_setter_name,
    build_unique_identifiers,
    snake_to_go_camel_case,
)
from purego_gen.typedef_lookups import build_typedef_render_helpers

if TYPE_CHECKING:
    import re
    from collections.abc import Mapping

    from purego_gen.config_model import GeneratorNaming, GeneratorRenderSpec
    from purego_gen.model import FunctionDecl, ParsedDeclarations

from purego_gen.config_model import GeneratorHelpers, PublicApiSpec


class TypeAliasContext(TypedDict):
    """Template context for one typedef alias."""

    name: str
    go_type: str
    is_strict: bool
    comment_lines: tuple[str, ...]
    c_type_comment: str


class ConstantContext(TypedDict):
    """Template context for one constant."""

    name: str
    expression: str
    const_type: str | None
    comment_lines: tuple[str, ...]


class FunctionContext(TypedDict):
    """Template context for one function variable."""

    name: str
    symbol: str
    parameters: tuple[FunctionParameterContext, ...]
    result_type: str | None
    result_c_type_comment: str
    comment_lines: tuple[str, ...]


class RuntimeVarContext(TypedDict):
    """Template context for one runtime variable."""

    name: str
    symbol: str
    comment_lines: tuple[str, ...]


class HelperContext(TypedDict):
    """Template context for one generated helper function."""

    name: str
    target_name: str
    parameters: tuple[FunctionParameterContext, ...]
    result_type: str | None
    result_c_type_comment: str
    result_suffix: str
    locals: tuple[HelperLocalContext, ...]
    slice_parameters: tuple[str, ...]
    callback_parameters: tuple[str, ...]
    call_arguments: tuple[str, ...]


class FuncTypeAliasContext(TypedDict):
    """Template context for one func-type alias."""

    name: str
    go_type: str
    c_type_comment: str


class NewCallbackHelperContext(TypedDict):
    """Template context for one NewCallback helper."""

    name: str
    param_type: str
    return_type: str


class OwnedStringHelperContext(TypedDict):
    """Template context for one owned-string helper."""

    name: str
    target_name: str
    free_func_name: str
    parameters: tuple[FunctionParameterContext, ...]
    call_arguments: tuple[str, ...]


class StructAccessorContext(TypedDict):
    """Template context for one struct accessor getter/setter pair."""

    receiver_type: str
    field_name: str
    getter_name: str
    setter_name: str
    go_type: str


class UnionAccessorContext(TypedDict):
    """Template context for one union accessor getter/setter pair."""

    receiver_type: str
    getter_name: str
    setter_name: str
    go_type: str


class PublicTypeAliasContext(TypedDict):
    """Template context for one public type alias."""

    public_name: str
    internal_name: str


class PublicWrapperParamContext(TypedDict):
    """Template context for one parameter in a public wrapper function."""

    name: str
    type: str


class PublicWrapperContext(TypedDict):
    """Template context for one public wrapper function."""

    public_name: str
    internal_func_name: str
    parameters: tuple[PublicWrapperParamContext, ...]
    result_type: str | None


class TemplateContext(TypedDict):
    """Full template context for the main Go output template."""

    package: str
    emit_kinds: tuple[str, ...]
    has_func_or_var: bool
    has_purego_import: bool
    has_type_block: bool
    has_gostring_util: bool
    type_aliases: tuple[TypeAliasContext, ...]
    func_type_aliases: tuple[FuncTypeAliasContext, ...]
    newcallback_helpers: tuple[NewCallbackHelperContext, ...]
    constants: tuple[ConstantContext, ...]
    functions: tuple[FunctionContext, ...]
    helpers: tuple[HelperContext, ...]
    owned_string_helpers: tuple[OwnedStringHelperContext, ...]
    struct_accessors: tuple[StructAccessorContext, ...]
    union_accessors: tuple[UnionAccessorContext, ...]
    runtime_vars: tuple[RuntimeVarContext, ...]
    has_union_helpers: bool
    union_get_func_name: str
    union_set_func_name: str
    register_functions_name: str
    load_runtime_vars_name: str
    gostring_func_name: str
    public_type_aliases: tuple[PublicTypeAliasContext, ...]
    public_wrappers: tuple[PublicWrapperContext, ...]


class ContextBuildError(RuntimeError):
    """Raised when template context construction fails."""


@dataclass(frozen=True, slots=True)
class _RenderIdentifiers:
    """Deterministic unique identifiers for each rendered declaration category."""

    types: tuple[str, ...]
    constants: tuple[str, ...]
    functions: tuple[str, ...]
    runtime_vars: tuple[str, ...]


def _build_render_identifiers(
    declarations: ParsedDeclarations,
) -> _RenderIdentifiers:
    """Build deterministic identifiers for each rendered declaration category.

    Returns:
        Grouped identifier tuples for all declaration categories.
    """
    return _RenderIdentifiers(
        types=build_unique_identifiers(
            tuple(typedef.name for typedef in declarations.typedefs),
            fallback_prefix="type",
        ),
        constants=build_unique_identifiers(
            tuple(constant.name for constant in declarations.constants),
            fallback_prefix="const",
        ),
        functions=build_unique_identifiers(
            tuple(function.name for function in declarations.functions),
            fallback_prefix="func",
        ),
        runtime_vars=build_unique_identifiers(
            tuple(runtime_var.name for runtime_var in declarations.runtime_vars),
            fallback_prefix="var",
        ),
    )


def _build_function_context(
    *,
    function: FunctionDecl,
    identifier: str,
    render: GeneratorRenderSpec,
    type_resolver: HelperTypeResolver,
) -> FunctionContext:
    resolved_result_type = (
        type_resolver.resolve_parameter_type(
            go_type=function.go_result_type,
            c_type=function.result_c_type,
        )
        if function.go_result_type is not None
        else None
    )
    return {
        "name": render.naming.func_name(identifier),
        "symbol": function.name,
        "parameters": build_function_parameters_context(
            parameter_names=function.parameter_names,
            go_parameter_types=function.go_parameter_types,
            parameter_c_types=function.parameter_c_types,
            type_resolver=type_resolver,
        ),
        "result_type": resolved_result_type,
        "result_c_type_comment": (
            function.result_c_type if resolved_result_type == "uintptr" else ""
        ),
        "comment_lines": normalize_comment_lines(function.comment),
    }


def _revert_callback_targeted_func_params(
    *,
    parameters: tuple[FunctionParameterContext, ...],
    function: FunctionDecl,
    callback_targeted_params: frozenset[tuple[str, str]],
) -> tuple[FunctionParameterContext, ...]:
    """Revert callback-targeted inline function pointer params back to ``uintptr``.

    Purego panics when ``nil`` is passed as a ``func(...)``-typed argument.
    Parameters targeted by callback helpers are reverted so the helper wrapper
    can guard nil before calling ``purego.NewCallback``.

    Returns:
        Parameter contexts with callback-targeted func params reverted to uintptr.
    """
    if not callback_targeted_params:
        return parameters
    result: list[FunctionParameterContext] = []
    for param, raw_name, c_type in zip(
        parameters,
        function.parameter_names,
        function.parameter_c_types,
        strict=True,
    ):
        effective_name = raw_name or param["name"]
        if (
            param["type"].startswith("func(")
            # Defensive: confirm the C type is actually a function pointer, not a
            # Go type that happens to start with ``func(`` for some other reason.
            and is_function_pointer_c_type(c_type)
            and (function.name, effective_name) in callback_targeted_params
        ):
            result.append({
                "name": param["name"],
                "type": "uintptr",
                "c_type_comment": c_type,
            })
        else:
            result.append(param)
    return tuple(result)


def _apply_callback_param_reverts(
    *,
    function_contexts: tuple[FunctionContext, ...],
    declarations: ParsedDeclarations,
    helpers: GeneratorHelpers,
) -> tuple[FunctionContext, ...]:
    """Revert callback-targeted params in function contexts back to ``uintptr``.

    Returns:
        Function contexts with callback-targeted func params reverted to uintptr.
    """
    callback_targeted: frozenset[tuple[str, str]] = frozenset(
        (helper.function, param)
        for helper in helpers.callback_inputs
        for param in helper.parameters
    )
    if not callback_targeted:
        return function_contexts
    return tuple(
        {
            **ctx,
            "parameters": _revert_callback_targeted_func_params(
                parameters=ctx["parameters"],
                function=function,
                callback_targeted_params=callback_targeted,
            ),
        }
        for ctx, function in zip(function_contexts, declarations.functions, strict=True)
    )


def _build_func_type_and_newcallback_contexts(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emit_kinds: tuple[str, ...],
    naming: GeneratorNaming,
    type_resolver: HelperTypeResolver,
) -> tuple[tuple[FuncTypeAliasContext, ...], tuple[NewCallbackHelperContext, ...]]:
    """Build func-type alias and NewCallback helper contexts for function-pointer typedefs.

    Returns:
        Tuple of func-type alias contexts and NewCallback helper contexts.
    """
    if "type" not in emit_kinds:
        return (), ()

    func_type_aliases: list[FuncTypeAliasContext] = []
    newcallback_helpers: list[NewCallbackHelperContext] = []
    for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True):
        if typedef.go_type != "uintptr" or not is_function_pointer_c_type(typedef.c_type):
            continue
        try:
            go_func_type = type_resolver.build_callback_func_type(c_type=typedef.c_type)
        except HelperRenderingError:
            continue
        func_type_name = naming.func_type_name(identifier)
        return_type = naming.type_name(identifier)
        func_type_aliases.append({
            "name": func_type_name,
            "go_type": go_func_type,
            "c_type_comment": typedef.c_type,
        })
        newcallback_helpers.append({
            "name": naming.newcallback_name(identifier),
            "param_type": func_type_name,
            "return_type": return_type,
        })
    return tuple(func_type_aliases), tuple(newcallback_helpers)


def _collect_callback_param_entries(
    *,
    declarations: ParsedDeclarations,
    helpers: GeneratorHelpers,
    type_resolver: HelperTypeResolver,
) -> dict[str, list[tuple[str, str, str]]]:
    """Collect non-typedef-backed callback parameters grouped by effective name.

    Returns:
        Mapping from effective parameter name to list of
        ``(function_name, go_func_type, c_type)`` tuples.
    """
    functions_by_name = {function.name: function for function in declarations.functions}
    param_entries: dict[str, list[tuple[str, str, str]]] = {}

    for helper in helpers.callback_inputs:
        function = functions_by_name.get(helper.function)
        if function is None:
            continue
        targeted = set(helper.parameters)
        resolved_params = build_function_parameters_context(
            parameter_names=function.parameter_names,
            go_parameter_types=function.go_parameter_types,
            parameter_c_types=function.parameter_c_types,
            type_resolver=type_resolver,
        )
        for raw_name, c_type, context in zip(
            function.parameter_names,
            function.parameter_c_types,
            resolved_params,
            strict=True,
        ):
            effective_name = raw_name or context["name"]
            if effective_name not in targeted:
                continue
            # Inline function pointers now resolve to ``func(...)`` instead of
            # ``uintptr``, so also admit params whose C type is a function pointer.
            if not is_function_pointer_c_type(c_type) and context["type"] != "uintptr":
                continue
            try:
                go_func_type = type_resolver.build_callback_func_type(c_type=c_type)
            except HelperRenderingError:
                continue
            if effective_name not in param_entries:
                param_entries[effective_name] = []
            param_entries[effective_name].append((helper.function, go_func_type, c_type))

    return param_entries


def _make_callback_param_type_entry(
    *,
    type_name: str,
    helper_name: str,
    go_func_type: str,
    c_type: str,
) -> tuple[FuncTypeAliasContext, NewCallbackHelperContext]:
    """Build one func-type alias and NewCallback helper entry pair.

    Returns:
        Tuple of func-type alias context and NewCallback helper context.
    """
    return (
        {"name": type_name, "go_type": go_func_type, "c_type_comment": c_type},
        {"name": helper_name, "param_type": type_name, "return_type": "uintptr"},
    )


@dataclass(frozen=True, slots=True)
class CallbackParamContexts:
    """Callback parameter func-type alias and NewCallback helper contexts."""

    func_type_aliases: tuple[FuncTypeAliasContext, ...]
    newcallback_helpers: tuple[NewCallbackHelperContext, ...]
    overrides: dict[tuple[str, str], str]


_EMPTY_CALLBACK_PARAM_CONTEXTS = CallbackParamContexts(
    func_type_aliases=(),
    newcallback_helpers=(),
    overrides={},
)


def _build_callback_param_func_type_contexts(
    *,
    declarations: ParsedDeclarations,
    helpers: GeneratorHelpers,
    type_resolver: HelperTypeResolver,
    naming: GeneratorNaming,
) -> CallbackParamContexts:
    """Build func-type alias and NewCallback helper contexts for callback parameters.

    Returns:
        Callback parameter contexts with func-type aliases, helpers, and overrides.
    """
    if not helpers.callback_inputs:
        return _EMPTY_CALLBACK_PARAM_CONTEXTS

    param_entries = _collect_callback_param_entries(
        declarations=declarations,
        helpers=helpers,
        type_resolver=type_resolver,
    )

    func_type_aliases: list[FuncTypeAliasContext] = []
    newcallback_helpers: list[NewCallbackHelperContext] = []
    overrides: dict[tuple[str, str], str] = {}

    for param_name, entries in param_entries.items():
        unique_signatures = {sig for _, sig, _ in entries}
        if len(unique_signatures) == 1:
            type_name = naming.callback_func_type_name(param_name)
            alias, helper = _make_callback_param_type_entry(
                type_name=type_name,
                helper_name=naming.callback_newcallback_name(param_name),
                go_func_type=entries[0][1],
                c_type=entries[0][2],
            )
            func_type_aliases.append(alias)
            newcallback_helpers.append(helper)
            for function_name, _, _ in entries:
                overrides[function_name, param_name] = type_name
        else:
            sig_to_type: dict[str, str] = {}
            for function_name, go_func_type, c_type in entries:
                if go_func_type in sig_to_type:
                    overrides[function_name, param_name] = sig_to_type[go_func_type]
                    continue
                type_name = naming.callback_func_type_name_qualified(function_name, param_name)
                alias, helper = _make_callback_param_type_entry(
                    type_name=type_name,
                    helper_name=naming.callback_newcallback_name_qualified(
                        function_name, param_name
                    ),
                    go_func_type=go_func_type,
                    c_type=c_type,
                )
                func_type_aliases.append(alias)
                newcallback_helpers.append(helper)
                sig_to_type[go_func_type] = type_name
                overrides[function_name, param_name] = type_name

    return CallbackParamContexts(
        func_type_aliases=tuple(func_type_aliases),
        newcallback_helpers=tuple(newcallback_helpers),
        overrides=overrides,
    )


def _build_owned_string_contexts(
    *,
    function_identifier_by_name: Mapping[str, str],
    declarations: ParsedDeclarations,
    render: GeneratorRenderSpec,
    function_identifiers: tuple[str, ...],
    type_resolver: HelperTypeResolver,
) -> tuple[tuple[FunctionContext, ...], tuple[OwnedStringHelperContext, ...]]:
    """Build function contexts with owned-string overrides and helper contexts.

    Returns:
        Tuple of (function contexts, owned-string helper contexts).

    Raises:
        ContextBuildError: Helper targets or configuration are invalid.
    """
    try:
        owned_string_helper_contexts, owned_string_override_names = (
            build_owned_string_return_helpers(
                function_identifier_by_name=function_identifier_by_name,
                declarations=declarations,
                helpers=render.helpers,
                type_resolver=type_resolver,
            )
        )
    except HelperRenderingError as error:
        raise ContextBuildError(str(error)) from error

    function_contexts: list[FunctionContext] = []
    for function, identifier in zip(declarations.functions, function_identifiers, strict=True):
        ctx = _build_function_context(
            function=function,
            identifier=identifier,
            render=render,
            type_resolver=type_resolver,
        )
        if function.name in owned_string_override_names:
            ctx["result_type"] = "uintptr"
            ctx["result_c_type_comment"] = function.result_c_type
        function_contexts.append(ctx)

    owned_string_helpers = tuple(
        OwnedStringHelperContext(
            name=render.naming.func_name(helper["identifier"]),
            target_name=render.naming.func_name(helper["target_identifier"]),
            free_func_name=render.naming.func_name(helper["free_func_identifier"]),
            parameters=helper["parameters"],
            call_arguments=helper["call_arguments"],
        )
        for helper in owned_string_helper_contexts
    )

    return tuple(function_contexts), owned_string_helpers


def _build_struct_accessor_contexts(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    naming: GeneratorNaming,
) -> tuple[StructAccessorContext, ...]:
    """Build struct accessor getter/setter contexts for record typedefs.

    Returns:
        Tuple of struct accessor contexts for each supported field.
    """
    emitted_typedef_names = {
        naming.type_name(identifier): typedef.name
        for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
    }
    record_typedef_by_name = {rt.name: rt for rt in declarations.record_typedefs}

    accessors: list[StructAccessorContext] = []
    for go_type_name, c_typedef_name in emitted_typedef_names.items():
        record_typedef = record_typedef_by_name.get(c_typedef_name)
        if record_typedef is None:
            continue
        if record_typedef.record_kind == "UNION_DECL":
            continue
        for field in record_typedef.fields:
            if field.go_name is None or field.go_type is None:
                continue
            if "\n" in field.go_type:
                continue
            accessors.append({
                "receiver_type": go_type_name,
                "field_name": field.go_name,
                "getter_name": accessor_getter_name(field.name),
                "setter_name": accessor_setter_name(field.name),
                "go_type": field.go_type,
            })
    return tuple(accessors)


def _build_union_accessor_contexts(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    naming: GeneratorNaming,
) -> tuple[UnionAccessorContext, ...]:
    """Build union accessor getter/setter contexts for union typedefs.

    Returns:
        Tuple of union accessor contexts for each supported field.
    """
    emitted_typedef_names = {
        naming.type_name(identifier): typedef.name
        for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
    }
    record_typedef_by_name = {rt.name: rt for rt in declarations.record_typedefs}

    accessors: list[UnionAccessorContext] = []
    for go_type_name, c_typedef_name in emitted_typedef_names.items():
        record_typedef = record_typedef_by_name.get(c_typedef_name)
        if record_typedef is None:
            continue
        if record_typedef.record_kind != "UNION_DECL":
            continue
        for field in record_typedef.fields:
            if field.go_name is None or field.go_type is None:
                continue
            if "\n" in field.go_type:
                continue
            accessors.append({
                "receiver_type": go_type_name,
                "getter_name": accessor_getter_name(field.name),
                "setter_name": accessor_setter_name(field.name),
                "go_type": field.go_type,
            })
    return tuple(accessors)


def _has_emitted_union_typedefs(
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
) -> bool:
    """Check whether any supported union typedefs will be emitted.

    Returns:
        `True` when at least one supported union typedef is emitted.
    """
    if "type" not in emit_kinds:
        return False
    emitted_names = {td.name for td in declarations.typedefs}
    return any(
        rt.record_kind == "UNION_DECL" and rt.supported
        for rt in declarations.record_typedefs
        if rt.name in emitted_names
    )


def _resolve_effective_helpers(
    helpers: GeneratorHelpers,
    declarations: ParsedDeclarations,
) -> GeneratorHelpers:
    """Resolve effective helpers with auto-discovered callbacks merged in.

    Returns:
        Helpers with auto-discovered callback inputs when enabled.
    """
    if not helpers.auto_callback_inputs:
        return helpers
    merged_callback_inputs = discover_callback_inputs(
        declarations,
        explicit_callback_inputs=helpers.callback_inputs,
    )
    return GeneratorHelpers(
        auto_callback_inputs=helpers.auto_callback_inputs,
        buffer_inputs=helpers.buffer_inputs,
        callback_inputs=merged_callback_inputs,
        owned_string_returns=helpers.owned_string_returns,
    )


def _public_api_name(
    c_name: str,
    *,
    strip_prefix: str,
    overrides: dict[str, str],
) -> str:
    """Derive a Go public name from a C name.

    Returns:
        Go public API name.
    """
    if c_name in overrides:
        return overrides[c_name]
    stripped = c_name
    if strip_prefix and stripped.startswith(strip_prefix):
        stripped = stripped[len(strip_prefix) :]
    if not stripped:
        return c_name
    return snake_to_go_camel_case(stripped)


def _matches_filter(
    name: str,
    *,
    include: re.Pattern[str],
    exclude: re.Pattern[str] | None,
) -> bool:
    """Check if a name matches include but not exclude filter.

    Returns:
        True if name passes the filter.
    """
    if not include.search(name):
        return False
    return not (exclude is not None and exclude.search(name))


def _build_public_type_alias_contexts(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    naming: GeneratorNaming,
    public_api: PublicApiSpec | None,
) -> tuple[PublicTypeAliasContext, ...]:
    """Build public type alias contexts by matching declarations against filters.

    Returns:
        Tuple of public type alias contexts.

    Raises:
        ContextBuildError: Configured filters match no declarations.
    """
    if public_api is None or public_api.type_aliases_config is None:
        return ()

    config = public_api.type_aliases_config
    result: list[PublicTypeAliasContext] = []

    for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True):
        c_name = typedef.name
        if not _matches_filter(
            c_name,
            include=config.include,
            exclude=config.exclude,
        ):
            continue
        internal_name = naming.type_name(identifier)
        public_name = _public_api_name(
            c_name,
            strip_prefix=public_api.strip_prefix,
            overrides=config.overrides,
        )
        result.append({
            "public_name": public_name,
            "internal_name": internal_name,
        })

    if not result:
        message = "public_api.type_aliases.include matched no emitted typedefs"
        raise ContextBuildError(message)
    return tuple(result)


def _build_public_wrapper_contexts(
    *,
    declarations: ParsedDeclarations,
    function_identifiers: tuple[str, ...],
    render: GeneratorRenderSpec,
    type_resolver: HelperTypeResolver,
    public_type_alias_map: dict[str, str],
) -> tuple[PublicWrapperContext, ...]:
    """Build public wrapper function contexts by matching declarations against filters.

    Returns:
        Tuple of public wrapper function contexts.

    Raises:
        ContextBuildError: Configured filters match no declarations.
    """
    public_api = render.public_api
    if public_api is None or public_api.wrappers_config is None:
        return ()

    config = public_api.wrappers_config
    result: list[PublicWrapperContext] = []

    for function, identifier in zip(declarations.functions, function_identifiers, strict=True):
        c_name = function.name
        if not _matches_filter(
            c_name,
            include=config.include,
            exclude=config.exclude,
        ):
            continue
        internal_func_name = render.naming.func_name(identifier)
        public_name = _public_api_name(
            c_name,
            strip_prefix=public_api.strip_prefix,
            overrides=config.overrides,
        )

        # Build parameter list with public type substitution
        params: list[PublicWrapperParamContext] = []
        raw_params = build_function_parameters_context(
            parameter_names=function.parameter_names,
            go_parameter_types=function.go_parameter_types,
            parameter_c_types=function.parameter_c_types,
            type_resolver=type_resolver,
        )
        for param in raw_params:
            param_type = _substitute_public_type(param["type"], public_type_alias_map)
            params.append({"name": param["name"], "type": param_type})

        # Resolve result type with public type substitution
        result_type: str | None = None
        if function.go_result_type is not None:
            resolved = type_resolver.resolve_parameter_type(
                go_type=function.go_result_type,
                c_type=function.result_c_type,
            )
            result_type = _substitute_public_type(resolved, public_type_alias_map)

        result.append({
            "public_name": public_name,
            "internal_func_name": internal_func_name,
            "parameters": tuple(params),
            "result_type": result_type,
        })

    if not result:
        message = "public_api.wrappers.include matched no emitted functions"
        raise ContextBuildError(message)
    return tuple(result)


def _build_public_api_contexts(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    function_identifiers: tuple[str, ...],
    render: GeneratorRenderSpec,
    type_resolver: HelperTypeResolver,
) -> tuple[tuple[PublicTypeAliasContext, ...], tuple[PublicWrapperContext, ...]]:
    """Build all public API contexts (type aliases and wrappers).

    Returns:
        Tuple of (public type alias contexts, public wrapper contexts).
    """
    public_type_aliases = _build_public_type_alias_contexts(
        declarations=declarations,
        type_identifiers=type_identifiers,
        naming=render.naming,
        public_api=render.public_api,
    )
    public_type_alias_map: dict[str, str] = {
        pta["internal_name"]: pta["public_name"] for pta in public_type_aliases
    }
    public_wrappers = _build_public_wrapper_contexts(
        declarations=declarations,
        function_identifiers=function_identifiers,
        render=render,
        type_resolver=type_resolver,
        public_type_alias_map=public_type_alias_map,
    )
    return public_type_aliases, public_wrappers


def _substitute_public_type(go_type: str, type_map: dict[str, str]) -> str:
    """Substitute internal type names with public type aliases in a Go type string.

    Returns:
        Type string with public aliases applied.
    """
    for internal, public in type_map.items():
        if go_type == internal:
            return public
        # Handle pointer types like *internal_name
        if go_type == f"*{internal}":
            return f"*{public}"
    return go_type


def build_template_context(
    *,
    package: str,
    lib_id: str,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    render: GeneratorRenderSpec,
) -> TemplateContext:
    """Build render context for the main Go output template.

    Returns:
        Context dictionary passed to Jinja2 template rendering.

    Raises:
        ContextBuildError: Emit kinds are invalid or helper config is broken.
    """
    try:
        validate_emit_kinds(emit_kinds, context="renderer")
    except ValueError as error:
        raise ContextBuildError(str(error)) from error
    ids = _build_render_identifiers(declarations)
    typedef_helpers = build_typedef_render_helpers(
        emit_kinds=emit_kinds,
        declarations=declarations,
        type_identifiers=ids.types,
        type_mapping=render.type_mapping,
        naming=render.naming,
    )
    function_identifier_by_name = {
        function.name: identifier
        for function, identifier in zip(declarations.functions, ids.functions, strict=True)
    }
    type_resolver = HelperTypeResolver(
        type_aliases=typedef_helpers.func_sig_type_aliases,
        typedef_go_type_by_lookup=typedef_helpers.typedef_go_type_by_lookup,
        typedef_c_type_by_lookup=build_typedef_c_type_by_lookup(declarations),
    )

    effective_helpers = _resolve_effective_helpers(render.helpers, declarations)

    callback_param_contexts = _build_callback_param_func_type_contexts(
        declarations=declarations,
        helpers=effective_helpers,
        type_resolver=type_resolver,
        naming=render.naming,
    )
    try:
        helper_contexts = build_function_helpers(
            function_identifier_by_name=function_identifier_by_name,
            declarations=declarations,
            helpers=effective_helpers,
            type_resolver=type_resolver,
            callback_param_type_overrides=callback_param_contexts.overrides,
        )
    except HelperRenderingError as error:
        raise ContextBuildError(str(error)) from error
    func_type_aliases, newcallback_helpers = _build_func_type_and_newcallback_contexts(
        declarations=declarations,
        type_identifiers=ids.types,
        emit_kinds=emit_kinds,
        naming=render.naming,
        type_resolver=type_resolver,
    )
    func_type_aliases += callback_param_contexts.func_type_aliases
    newcallback_helpers += callback_param_contexts.newcallback_helpers

    owned_string_function_contexts, owned_string_helpers = _build_owned_string_contexts(
        function_identifier_by_name=function_identifier_by_name,
        declarations=declarations,
        render=render,
        function_identifiers=ids.functions,
        type_resolver=type_resolver,
    )
    has_union_helpers = _has_emitted_union_typedefs(emit_kinds, declarations)
    public_type_aliases, public_wrappers = _build_public_api_contexts(
        declarations=declarations,
        type_identifiers=ids.types,
        function_identifiers=ids.functions,
        render=render,
        type_resolver=type_resolver,
    )

    return {
        "package": package,
        "emit_kinds": emit_kinds,
        "has_func_or_var": "func" in emit_kinds or "var" in emit_kinds,
        "has_purego_import": "func" in emit_kinds
        or "var" in emit_kinds
        or bool(newcallback_helpers)
        or has_union_helpers,
        "has_type_block": ("type" in emit_kinds and bool(declarations.typedefs))
        or bool(func_type_aliases),
        "has_gostring_util": bool(owned_string_helpers),
        "type_aliases": tuple(
            {
                "name": render.naming.type_name(identifier),
                "go_type": typedef.go_type,
                "is_strict": typedef.name in typedef_helpers.emitted_strict_typedef_names,
                "comment_lines": normalize_comment_lines(typedef.comment),
                "c_type_comment": typedef.c_type if "\n" not in typedef.go_type else "",
            }
            for typedef, identifier in zip(declarations.typedefs, ids.types, strict=True)
        ),
        "func_type_aliases": func_type_aliases,
        "newcallback_helpers": newcallback_helpers,
        "constants": tuple(
            {
                "name": render.naming.const_name(identifier),
                "expression": resolve_constant_expression(
                    constant_expression=constant.go_expression,
                    value=constant.value,
                    const_type=resolve_typed_constant_type(
                        constant_c_type=constant.c_type,
                        value=constant.value,
                        type_mapping=render.type_mapping,
                        typedef_alias_type_by_lookup=typedef_helpers.typedef_alias_type_by_lookup,
                        typedef_go_type_by_lookup=typedef_helpers.typedef_go_type_by_lookup,
                    ),
                ),
                "const_type": resolve_typed_constant_type(
                    constant_c_type=constant.c_type,
                    value=constant.value,
                    type_mapping=render.type_mapping,
                    typedef_alias_type_by_lookup=typedef_helpers.typedef_alias_type_by_lookup,
                    typedef_go_type_by_lookup=typedef_helpers.typedef_go_type_by_lookup,
                ),
                "comment_lines": normalize_comment_lines(constant.comment),
            }
            for constant, identifier in zip(declarations.constants, ids.constants, strict=True)
        ),
        "functions": _apply_callback_param_reverts(
            function_contexts=owned_string_function_contexts,
            declarations=declarations,
            helpers=effective_helpers,
        ),
        "helpers": tuple(
            {
                "name": render.naming.func_name(helper["identifier"]),
                "target_name": render.naming.func_name(helper["target_identifier"]),
                "parameters": helper["parameters"],
                "result_type": helper["result_type"],
                "result_c_type_comment": helper["result_c_type_comment"],
                "result_suffix": helper["result_suffix"],
                "locals": helper["locals"],
                "slice_parameters": helper["slice_parameters"],
                "callback_parameters": helper["callback_parameters"],
                "call_arguments": helper["call_arguments"],
            }
            for helper in helper_contexts
        ),
        "owned_string_helpers": owned_string_helpers,
        "struct_accessors": (
            _build_struct_accessor_contexts(
                declarations=declarations,
                type_identifiers=ids.types,
                naming=render.naming,
            )
            if render.struct_accessors and "type" in emit_kinds
            else ()
        ),
        "union_accessors": (
            _build_union_accessor_contexts(
                declarations=declarations,
                type_identifiers=ids.types,
                naming=render.naming,
            )
            if render.struct_accessors and "type" in emit_kinds
            else ()
        ),
        "runtime_vars": tuple(
            {
                "name": render.naming.runtime_var_name(identifier),
                "symbol": runtime_var.name,
                "comment_lines": normalize_comment_lines(runtime_var.comment),
            }
            for runtime_var, identifier in zip(
                declarations.runtime_vars, ids.runtime_vars, strict=True
            )
        ),
        "has_union_helpers": has_union_helpers,
        "union_get_func_name": render.naming.func_name("union_get"),
        "union_set_func_name": render.naming.func_name("union_set"),
        "register_functions_name": render.naming.register_functions_name(lib_id),
        "load_runtime_vars_name": render.naming.load_runtime_vars_name(lib_id),
        "gostring_func_name": render.naming.gostring_func_name(),
        "public_type_aliases": public_type_aliases,
        "public_wrappers": public_wrappers,
    }


__all__ = [
    "ConstantContext",
    "ContextBuildError",  # internal; caught only by renderer.py
    "FuncTypeAliasContext",
    "FunctionContext",
    "HelperContext",
    "NewCallbackHelperContext",
    "OwnedStringHelperContext",
    "PublicTypeAliasContext",
    "PublicWrapperContext",
    "RuntimeVarContext",
    "StructAccessorContext",
    "TemplateContext",
    "TypeAliasContext",
    "UnionAccessorContext",
    "build_template_context",
]
