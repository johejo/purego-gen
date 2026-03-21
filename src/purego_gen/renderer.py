# Copyright (c) 2026 purego-gen contributors.

"""Jinja2-backed emit layer."""

from __future__ import annotations

import os
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

from purego_gen.c_type_utils import is_function_pointer_c_type
from purego_gen.config_model import GeneratorHelpers, GeneratorNaming, GeneratorRenderSpec
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
)
from purego_gen.identifier_utils import build_unique_identifiers, validate_generated_names
from purego_gen.typedef_lookups import build_typedef_render_helpers

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.model import FunctionDecl, ParsedDeclarations

_MAIN_TEMPLATE_NAME: Final[str] = "go_file.go.j2"
_REQUIRED_CONTEXT_KEYS: Final[frozenset[str]] = frozenset({
    "package",
    "emit_kinds",
    "has_func_or_var",
    "has_purego_import",
    "has_type_block",
    "has_gostring_util",
    "type_aliases",
    "func_type_aliases",
    "newcallback_helpers",
    "constants",
    "functions",
    "helpers",
    "owned_string_helpers",
    "runtime_vars",
    "register_functions_name",
    "load_runtime_vars_name",
    "gostring_func_name",
})


class RendererError(RuntimeError):
    """Raised when template rendering fails."""


class _TypeAliasContext(TypedDict):
    name: str
    go_type: str
    is_strict: bool
    comment_lines: tuple[str, ...]
    c_type_comment: str


class _ConstantContext(TypedDict):
    name: str
    expression: str
    const_type: str | None
    comment_lines: tuple[str, ...]


class _FunctionContext(TypedDict):
    name: str
    symbol: str
    parameters: tuple[FunctionParameterContext, ...]
    result_type: str | None
    result_c_type_comment: str
    comment_lines: tuple[str, ...]


class _RuntimeVarContext(TypedDict):
    name: str
    symbol: str
    comment_lines: tuple[str, ...]


class _HelperContext(TypedDict):
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


class _FuncTypeAliasContext(TypedDict):
    name: str
    go_type: str
    c_type_comment: str


class _NewCallbackHelperContext(TypedDict):
    name: str
    param_type: str
    return_type: str


class _OwnedStringHelperContext(TypedDict):
    name: str
    target_name: str
    free_func_name: str
    parameters: tuple[FunctionParameterContext, ...]
    call_arguments: tuple[str, ...]


class _TemplateContext(TypedDict):
    package: str
    emit_kinds: tuple[str, ...]
    has_func_or_var: bool
    has_purego_import: bool
    has_type_block: bool
    has_gostring_util: bool
    type_aliases: tuple[_TypeAliasContext, ...]
    func_type_aliases: tuple[_FuncTypeAliasContext, ...]
    newcallback_helpers: tuple[_NewCallbackHelperContext, ...]
    constants: tuple[_ConstantContext, ...]
    functions: tuple[_FunctionContext, ...]
    helpers: tuple[_HelperContext, ...]
    owned_string_helpers: tuple[_OwnedStringHelperContext, ...]
    runtime_vars: tuple[_RuntimeVarContext, ...]
    register_functions_name: str
    load_runtime_vars_name: str
    gostring_func_name: str


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


def _build_function_context(
    *,
    function: FunctionDecl,
    identifier: str,
    render: GeneratorRenderSpec,
    type_resolver: HelperTypeResolver,
) -> _FunctionContext:
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


def _build_func_type_and_newcallback_contexts(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emit_kinds: tuple[str, ...],
    naming: GeneratorNaming,
    type_resolver: HelperTypeResolver,
) -> tuple[tuple[_FuncTypeAliasContext, ...], tuple[_NewCallbackHelperContext, ...]]:
    """Build func-type alias and NewCallback helper contexts for function-pointer typedefs.

    Returns:
        Tuple of func-type alias contexts and NewCallback helper contexts.
    """
    if "type" not in emit_kinds:
        return (), ()

    func_type_aliases: list[_FuncTypeAliasContext] = []
    newcallback_helpers: list[_NewCallbackHelperContext] = []
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
        # Resolve parameter contexts to obtain effective names via the same
        # path used by _resolve_function_parameters (raw_name or sanitized).
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
            if context["type"] != "uintptr":
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
) -> tuple[_FuncTypeAliasContext, _NewCallbackHelperContext]:
    """Build one func-type alias and NewCallback helper entry pair.

    Returns:
        Tuple of func-type alias context and NewCallback helper context.
    """
    return (
        {"name": type_name, "go_type": go_func_type, "c_type_comment": c_type},
        {"name": helper_name, "param_type": type_name, "return_type": "uintptr"},
    )


def _build_callback_param_func_type_contexts(
    *,
    declarations: ParsedDeclarations,
    helpers: GeneratorHelpers,
    type_resolver: HelperTypeResolver,
    naming: GeneratorNaming,
) -> tuple[
    tuple[_FuncTypeAliasContext, ...],
    tuple[_NewCallbackHelperContext, ...],
    dict[tuple[str, str], str],
]:
    """Build func-type alias and NewCallback helper contexts for callback parameters.

    Returns:
        Tuple of func-type alias contexts, NewCallback helper contexts,
        and callback parameter type override mapping.  Override keys are
        ``(raw_c_function_name, effective_param_name)`` where the effective
        param name uses the same fallback logic as
        ``ResolvedFunctionParameter.raw_name`` (sanitized name when the
        original C name is empty).
    """
    if not helpers.callback_inputs:
        return (), (), {}

    param_entries = _collect_callback_param_entries(
        declarations=declarations,
        helpers=helpers,
        type_resolver=type_resolver,
    )

    func_type_aliases: list[_FuncTypeAliasContext] = []
    newcallback_helpers: list[_NewCallbackHelperContext] = []
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

    return tuple(func_type_aliases), tuple(newcallback_helpers), overrides


def _build_owned_string_contexts(
    *,
    function_identifier_by_name: Mapping[str, str],
    declarations: ParsedDeclarations,
    render: GeneratorRenderSpec,
    function_identifiers: tuple[str, ...],
    type_resolver: HelperTypeResolver,
) -> tuple[tuple[_FunctionContext, ...], tuple[_OwnedStringHelperContext, ...]]:
    """Build function contexts with owned-string overrides and helper contexts.

    Returns:
        Tuple of (function contexts, owned-string helper contexts).

    Raises:
        RendererError: Helper targets or configuration are invalid.
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
        raise RendererError(str(error)) from error

    function_contexts: list[_FunctionContext] = []
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
        _OwnedStringHelperContext(
            name=render.naming.func_name(helper["identifier"]),
            target_name=render.naming.func_name(helper["target_identifier"]),
            free_func_name=render.naming.func_name(helper["free_func_identifier"]),
            parameters=helper["parameters"],
            call_arguments=helper["call_arguments"],
        )
        for helper in owned_string_helper_contexts
    )

    return tuple(function_contexts), owned_string_helpers


def _build_context(
    *,
    package: str,
    lib_id: str,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    render: GeneratorRenderSpec,
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
    typedef_render_helpers_result = build_typedef_render_helpers(
        emit_kinds=emit_kinds,
        declarations=declarations,
        type_identifiers=type_identifiers,
        type_mapping=render.type_mapping,
        naming=render.naming,
    )
    typedef_alias_type_by_lookup = typedef_render_helpers_result[1]
    typedef_go_type_by_lookup = typedef_render_helpers_result[2]
    emitted_strict_typedef_names = (
        typedef_render_helpers_result[3]
        | typedef_render_helpers_result[4]
        | typedef_render_helpers_result[5]
        | typedef_render_helpers_result[6]
    )
    function_identifier_by_name = {
        function.name: identifier
        for function, identifier in zip(declarations.functions, function_identifiers, strict=True)
    }
    type_resolver = HelperTypeResolver(
        type_aliases=typedef_render_helpers_result[0],
        typedef_go_type_by_lookup=typedef_go_type_by_lookup,
        typedef_c_type_by_lookup=build_typedef_c_type_by_lookup(declarations),
    )

    callback_param_contexts = _build_callback_param_func_type_contexts(
        declarations=declarations,
        helpers=render.helpers,
        type_resolver=type_resolver,
        naming=render.naming,
    )
    try:
        helper_contexts = build_function_helpers(
            function_identifier_by_name=function_identifier_by_name,
            declarations=declarations,
            helpers=render.helpers,
            type_resolver=type_resolver,
            callback_param_type_overrides=callback_param_contexts[2],
        )
    except HelperRenderingError as error:
        raise RendererError(str(error)) from error
    func_type_aliases, newcallback_helpers = _build_func_type_and_newcallback_contexts(
        declarations=declarations,
        type_identifiers=type_identifiers,
        emit_kinds=emit_kinds,
        naming=render.naming,
        type_resolver=type_resolver,
    )
    func_type_aliases += callback_param_contexts[0]
    newcallback_helpers += callback_param_contexts[1]

    owned_string_result = _build_owned_string_contexts(
        function_identifier_by_name=function_identifier_by_name,
        declarations=declarations,
        render=render,
        function_identifiers=function_identifiers,
        type_resolver=type_resolver,
    )

    return {
        "package": package,
        "emit_kinds": emit_kinds,
        "has_func_or_var": "func" in emit_kinds or "var" in emit_kinds,
        "has_purego_import": "func" in emit_kinds
        or "var" in emit_kinds
        or bool(newcallback_helpers),
        "has_type_block": ("type" in emit_kinds and bool(declarations.typedefs))
        or bool(func_type_aliases),
        "has_gostring_util": bool(owned_string_result[1]),
        "type_aliases": tuple(
            {
                "name": render.naming.type_name(identifier),
                "go_type": typedef.go_type,
                "is_strict": typedef.name in emitted_strict_typedef_names,
                "comment_lines": normalize_comment_lines(typedef.comment),
                "c_type_comment": typedef.c_type if "\n" not in typedef.go_type else "",
            }
            for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
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
                        typedef_alias_type_by_lookup=typedef_alias_type_by_lookup,
                        typedef_go_type_by_lookup=typedef_go_type_by_lookup,
                    ),
                ),
                "const_type": resolve_typed_constant_type(
                    constant_c_type=constant.c_type,
                    value=constant.value,
                    type_mapping=render.type_mapping,
                    typedef_alias_type_by_lookup=typedef_alias_type_by_lookup,
                    typedef_go_type_by_lookup=typedef_go_type_by_lookup,
                ),
                "comment_lines": normalize_comment_lines(constant.comment),
            }
            for constant, identifier in zip(
                declarations.constants, constant_identifiers, strict=True
            )
        ),
        "functions": owned_string_result[0],
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
        "owned_string_helpers": owned_string_result[1],
        "runtime_vars": tuple(
            {
                "name": render.naming.runtime_var_name(identifier),
                "symbol": runtime_var.name,
                "comment_lines": normalize_comment_lines(runtime_var.comment),
            }
            for runtime_var, identifier in zip(
                declarations.runtime_vars, runtime_var_identifiers, strict=True
            )
        ),
        "register_functions_name": render.naming.register_functions_name(lib_id),
        "load_runtime_vars_name": render.naming.load_runtime_vars_name(lib_id),
        "gostring_func_name": render.naming.gostring_func_name(),
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


def _has_empty_prefix(naming: GeneratorNaming) -> bool:
    # Only trigger validation when a newly-relaxed category (type, func, var)
    # has an empty prefix.  const_prefix="" was supported before this feature
    # and should not by itself gate into the validation path.
    return not (naming.type_prefix and naming.func_prefix and naming.var_prefix)


def _collect_generated_names(
    context: _TemplateContext,
    naming: GeneratorNaming,
) -> list[tuple[str, str, bool]]:
    """Collect all generated names from a template context for validation.

    Returns:
        List of ``(name, origin, check_reserved)`` triples.
        *check_reserved* is ``True`` for names from categories whose
        prefix is empty.
    """
    check_type = not naming.type_prefix
    check_const = not naming.const_prefix
    check_func = not naming.func_prefix
    check_var = not naming.var_prefix

    names: list[tuple[str, str, bool]] = [
        (alias["name"], "type from C typedef", check_type) for alias in context["type_aliases"]
    ]
    names.extend(
        (alias["name"], "func type alias", check_type) for alias in context["func_type_aliases"]
    )
    names.extend(
        (helper["name"], "NewCallback helper", check_func)
        for helper in context["newcallback_helpers"]
    )
    names.extend((const["name"], "constant", check_const) for const in context["constants"])
    names.extend(
        (func["name"], f"function from C symbol '{func['symbol']}'", check_func)
        for func in context["functions"]
    )
    names.extend(
        (helper["name"], "buffer/callback helper", check_func) for helper in context["helpers"]
    )
    names.extend(
        (helper["name"], "owned-string helper", check_func)
        for helper in context["owned_string_helpers"]
    )
    names.extend(
        (var["name"], f"runtime var from C symbol '{var['symbol']}'", check_var)
        for var in context["runtime_vars"]
    )
    names.extend([
        (context["register_functions_name"], "register_functions helper", check_func),
        (context["load_runtime_vars_name"], "load_runtime_vars helper", check_func),
        (context["gostring_func_name"], "gostring utility", check_func),
    ])
    return names


def render_go_source(
    *,
    package: str,
    lib_id: str,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    render: GeneratorRenderSpec | None = None,
) -> str:
    """Render generated Go source for one CLI invocation.

    Returns:
        Unformatted Go source rendered from templates.

    Raises:
        RendererError: Prefix-free naming produces invalid identifiers.
    """
    effective_render = render if render is not None else GeneratorRenderSpec()
    context = _build_context(
        package=package,
        lib_id=lib_id,
        emit_kinds=emit_kinds,
        declarations=declarations,
        render=effective_render,
    )
    if _has_empty_prefix(effective_render.naming):
        generated_names = _collect_generated_names(context, effective_render.naming)
        errors = validate_generated_names(generated_names)
        if errors:
            raise RendererError(
                "prefix-free naming produced invalid identifiers:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )
    return render_template(_MAIN_TEMPLATE_NAME, context)
