# Copyright (c) 2026 purego-gen contributors.

"""Jinja2-backed emit layer."""

from __future__ import annotations

import os
import re
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
    is_function_pointer_c_type,
    normalize_c_type_for_lookup,
    normalize_function_pointer_c_type_for_lookup,
)
from purego_gen.config_model import GeneratorNaming, GeneratorRenderSpec
from purego_gen.emit_kinds import validate_emit_kinds
from purego_gen.helper_rendering import (
    FunctionParameterContext,
    FunctionSignatureTypeAliases,
    HelperLocalContext,
    HelperRenderingError,
    HelperTypeResolver,
    build_function_helpers,
    build_function_parameters_context,
    build_typedef_c_type_by_lookup,
)
from purego_gen.identifier_utils import build_unique_identifiers

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.model import ParsedDeclarations, TypeMappingOptions

_MAIN_TEMPLATE_NAME: Final[str] = "go_file.go.j2"
_MAX_INT64: Final[int] = (1 << 63) - 1
_REQUIRED_CONTEXT_KEYS: Final[frozenset[str]] = frozenset({
    "package",
    "emit_kinds",
    "type_aliases",
    "constants",
    "functions",
    "helpers",
    "runtime_vars",
    "register_functions_name",
    "load_runtime_vars_name",
})


class RendererError(RuntimeError):
    """Raised when template rendering fails."""


class _TypeAliasContext(TypedDict):
    name: str
    go_type: str
    is_strict: bool
    comment_lines: tuple[str, ...]


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
    result_suffix: str
    locals: tuple[HelperLocalContext, ...]
    slice_parameters: tuple[str, ...]
    callback_parameters: tuple[str, ...]
    call_arguments: tuple[str, ...]


class _TemplateContext(TypedDict):
    package: str
    emit_kinds: tuple[str, ...]
    type_aliases: tuple[_TypeAliasContext, ...]
    constants: tuple[_ConstantContext, ...]
    functions: tuple[_FunctionContext, ...]
    helpers: tuple[_HelperContext, ...]
    runtime_vars: tuple[_RuntimeVarContext, ...]
    register_functions_name: str
    load_runtime_vars_name: str


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
    naming: GeneratorNaming,
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
        alias_name = naming.type_name(identifier)
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
    naming: GeneratorNaming,
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
        alias_name = naming.type_name(identifier)
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
    naming: GeneratorNaming,
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
        alias_name = naming.type_name(identifier)
        alias_type_by_lookup[typedef.name] = alias_name
        alias_type_by_lookup[normalize_c_type_for_lookup(typedef.c_type)] = alias_name
    return alias_type_by_lookup


def _build_function_pointer_alias_type_by_lookup(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emit_kinds: tuple[str, ...],
    naming: GeneratorNaming,
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
        alias_name = naming.type_name(identifier)
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
    naming: GeneratorNaming,
) -> FunctionSignatureTypeAliases:
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
        naming=naming,
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
            naming=naming,
        ),
        "function_pointer": _build_function_pointer_alias_type_by_lookup(
            declarations=declarations,
            type_identifiers=type_identifiers,
            emit_kinds=emit_kinds,
            naming=naming,
        ),
    }


def _build_typedef_render_helpers(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    type_mapping: TypeMappingOptions,
    naming: GeneratorNaming,
) -> tuple[
    FunctionSignatureTypeAliases,
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
            naming=naming,
        ),
        _build_typedef_alias_type_by_lookup(
            declarations=declarations,
            type_identifiers=type_identifiers,
            emit_kinds=emit_kinds,
            naming=naming,
        ),
        _build_typedef_go_type_by_lookup(declarations),
        emitted_opaque_struct_typedef_names,
        emitted_strict_enum_typedef_names,
    )


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
        type_mapping=render.type_mapping,
        naming=render.naming,
    )
    function_identifier_by_name = {
        function.name: identifier
        for function, identifier in zip(declarations.functions, function_identifiers, strict=True)
    }
    type_resolver = HelperTypeResolver(
        type_aliases=function_signature_type_aliases,
        typedef_go_type_by_lookup=typedef_go_type_by_lookup,
        typedef_c_type_by_lookup=build_typedef_c_type_by_lookup(declarations),
    )
    try:
        helper_contexts = build_function_helpers(
            function_identifier_by_name=function_identifier_by_name,
            declarations=declarations,
            helpers=render.helpers,
            type_resolver=type_resolver,
        )
    except HelperRenderingError as error:
        raise RendererError(str(error)) from error

    return {
        "package": package,
        "emit_kinds": emit_kinds,
        "type_aliases": tuple(
            {
                "name": render.naming.type_name(identifier),
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
                "name": render.naming.const_name(identifier),
                "expression": _resolve_constant_expression(
                    constant_expression=constant.go_expression,
                    value=constant.value,
                    const_type=_resolve_typed_constant_type(
                        constant_c_type=constant.c_type,
                        value=constant.value,
                        type_mapping=render.type_mapping,
                        typedef_alias_type_by_lookup=typedef_alias_type_by_lookup,
                        typedef_go_type_by_lookup=typedef_go_type_by_lookup,
                    ),
                ),
                "const_type": _resolve_typed_constant_type(
                    constant_c_type=constant.c_type,
                    value=constant.value,
                    type_mapping=render.type_mapping,
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
                "name": render.naming.func_name(identifier),
                "symbol": function.name,
                "parameters": build_function_parameters_context(
                    parameter_names=function.parameter_names,
                    go_parameter_types=function.go_parameter_types,
                    parameter_c_types=function.parameter_c_types,
                    type_resolver=type_resolver,
                ),
                "result_type": type_resolver.resolve_parameter_type(
                    go_type=function.go_result_type,
                    c_type=function.result_c_type,
                )
                if function.go_result_type is not None
                else None,
                "comment_lines": _normalize_comment_lines(function.comment),
            }
            for function, identifier in zip(
                declarations.functions, function_identifiers, strict=True
            )
        ),
        "helpers": tuple(
            {
                "name": render.naming.func_name(helper["identifier"]),
                "target_name": render.naming.func_name(helper["target_identifier"]),
                "parameters": helper["parameters"],
                "result_type": helper["result_type"],
                "result_suffix": helper["result_suffix"],
                "locals": helper["locals"],
                "slice_parameters": helper["slice_parameters"],
                "callback_parameters": helper["callback_parameters"],
                "call_arguments": helper["call_arguments"],
            }
            for helper in helper_contexts
        ),
        "runtime_vars": tuple(
            {
                "name": render.naming.runtime_var_name(identifier),
                "symbol": runtime_var.name,
                "comment_lines": _normalize_comment_lines(runtime_var.comment),
            }
            for runtime_var, identifier in zip(
                declarations.runtime_vars, runtime_var_identifiers, strict=True
            )
        ),
        "register_functions_name": render.naming.register_functions_name(lib_id),
        "load_runtime_vars_name": render.naming.load_runtime_vars_name(lib_id),
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
    render: GeneratorRenderSpec | None = None,
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
        render=render if render is not None else GeneratorRenderSpec(),
    )
    return render_template(_MAIN_TEMPLATE_NAME, context)
