# Copyright (c) 2026 purego-gen contributors.

"""Jinja2-backed emit layer."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    UndefinedError,
    select_autoescape,
)

from purego_gen.config_model import GeneratorRenderSpec
from purego_gen.identifier_utils import validate_generated_names
from purego_gen.render_context import ContextBuildError, build_template_context

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.config_model import GeneratorNaming
    from purego_gen.model import ParsedDeclarations
    from purego_gen.render_context import TemplateContext

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
    "struct_accessors",
    "runtime_vars",
    "register_functions_name",
    "load_runtime_vars_name",
    "gostring_func_name",
})


class RendererError(RuntimeError):
    """Raised when template rendering fails."""


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
    context: TemplateContext,
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
    # Struct accessor methods are scoped to their receiver type in Go,
    # so we qualify names with the receiver to avoid false cross-type collisions.
    names.extend(
        entry
        for accessor in context["struct_accessors"]
        for entry in (
            (
                f"{accessor['receiver_type']}.{accessor['getter_name']}",
                "struct accessor getter",
                check_type,
            ),
            (
                f"{accessor['receiver_type']}.{accessor['setter_name']}",
                "struct accessor setter",
                check_type,
            ),
        )
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
    try:
        context = build_template_context(
            package=package,
            lib_id=lib_id,
            emit_kinds=emit_kinds,
            declarations=declarations,
            render=effective_render,
        )
    except ContextBuildError as error:
        raise RendererError(str(error)) from error
    if _has_empty_prefix(effective_render.naming):
        generated_names = _collect_generated_names(context, effective_render.naming)
        errors = validate_generated_names(generated_names)
        if errors:
            raise RendererError(
                "prefix-free naming produced invalid identifiers:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )
    return render_template(_MAIN_TEMPLATE_NAME, context)
