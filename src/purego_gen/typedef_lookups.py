# Copyright (c) 2026 purego-gen contributors.

"""Typedef lookup construction for the renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from purego_gen.c_type_utils import (
    extract_enum_typedef_name,
    is_function_pointer_c_type,
    normalize_c_type_for_lookup,
    normalize_function_pointer_c_type_for_lookup,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.config_model import GeneratorNaming
    from purego_gen.helper_rendering import FunctionSignatureTypeAliases
    from purego_gen.model import ParsedDeclarations, TypeMappingOptions


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


def _build_emitted_opaque_pointer_typedef_names(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
) -> set[str]:
    """Build emitted opaque pointer typedef-name set.

    Returns:
        Set of opaque pointer typedef names emitted in this render.
    """
    if "type" not in emit_kinds:
        return set()

    emitted_typedef_names = {typedef.name for typedef in declarations.typedefs}
    return set(declarations.opaque_pointer_typedef_names & emitted_typedef_names)


def _build_opaque_pointer_alias_type_by_typedef_name(
    *,
    declarations: ParsedDeclarations,
    type_identifiers: tuple[str, ...],
    emitted_opaque_pointer_typedef_names: set[str],
    naming: GeneratorNaming,
) -> dict[str, str]:
    """Build emitted opaque pointer typedef alias lookup for function signatures.

    Returns:
        Mapping of opaque pointer typedef spellings to generated alias type names.
    """
    type_identifier_by_name = {
        typedef.name: identifier
        for typedef, identifier in zip(declarations.typedefs, type_identifiers, strict=True)
    }
    alias_type_by_typedef_name: dict[str, str] = {}
    for typedef_name in emitted_opaque_pointer_typedef_names:
        identifier = type_identifier_by_name.get(typedef_name)
        if identifier is None:
            continue
        alias_name = naming.type_name(identifier)
        alias_type_by_typedef_name[typedef_name] = alias_name
        typedef_by_name = {typedef.name: typedef for typedef in declarations.typedefs}
        typedef = typedef_by_name.get(typedef_name)
        if typedef is None:
            continue
        normalized_c_type = normalize_c_type_for_lookup(typedef.c_type)
        alias_type_by_typedef_name[normalized_c_type] = alias_name
    return alias_type_by_typedef_name


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


def build_typedef_render_helpers(
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
    set[str],
    set[str],
]:
    """Build typedef-related lookups and emitted-name sets used during rendering.

    Returns:
        Function-signature alias lookups, typedef alias lookup, typedef Go-type
        lookup, opaque typedef names, strict enum typedef names, opaque
        pointer typedef names, and record typedef names.
    """
    emitted_record_typedef_names = _build_emitted_record_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
    )
    emitted_opaque_struct_typedef_names = _build_emitted_opaque_struct_typedef_names(
        declarations=declarations,
        emitted_record_typedef_names=emitted_record_typedef_names,
    )
    emitted_opaque_pointer_typedef_names = _build_emitted_opaque_pointer_typedef_names(
        emit_kinds=emit_kinds,
        declarations=declarations,
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
    func_sig_type_aliases: FunctionSignatureTypeAliases = {
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
        "opaque_pointer": _build_opaque_pointer_alias_type_by_typedef_name(
            declarations=declarations,
            type_identifiers=type_identifiers,
            emitted_opaque_pointer_typedef_names=emitted_opaque_pointer_typedef_names,
            naming=naming,
        ),
    }
    return (
        func_sig_type_aliases,
        _build_typedef_alias_type_by_lookup(
            declarations=declarations,
            type_identifiers=type_identifiers,
            emit_kinds=emit_kinds,
            naming=naming,
        ),
        _build_typedef_go_type_by_lookup(declarations),
        emitted_opaque_struct_typedef_names,
        emitted_strict_enum_typedef_names,
        emitted_opaque_pointer_typedef_names,
        emitted_record_typedef_names,
    )
