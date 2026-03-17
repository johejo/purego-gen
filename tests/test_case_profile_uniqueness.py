# Copyright (c) 2026 purego-gen contributors.

"""Guards for accidental duplicate case config signatures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from purego_gen.config_load import dump_signature_payload

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CASES_DIR = _REPO_ROOT / "tests" / "cases"
_ALLOWED_DUPLICATE_SIGNATURE_CASE_SETS: set[frozenset[str]] = set()

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | JsonArray | JsonObject
type JsonArray = list[JsonValue]
type JsonObject = dict[str, JsonValue]


def _normalize_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: _normalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _build_profile_signature(profile: JsonObject) -> str:
    generator = cast("JsonObject", profile.get("generator", {}))
    signature_payload: JsonObject = {
        "schema_version": profile.get("schema_version"),
        "generator": {
            "lib_id": generator.get("lib_id"),
            "emit": generator.get("emit"),
            "headers": generator.get("headers"),
            "filters": generator.get("filters"),
            "type_mapping": generator.get("type_mapping"),
            "clang_args": generator.get("clang_args"),
        },
    }
    normalized_payload = _normalize_value(signature_payload)
    return json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"))


def test_case_profiles_are_unique_by_dedup_signature() -> None:
    """Cases should not share the same signature unless allowlisted."""
    grouped_case_ids: dict[str, list[str]] = {}
    for config_path in sorted(_CASES_DIR.glob("*/config.json")):
        case_id = config_path.parent.name
        profile = cast(
            "JsonObject",
            dump_signature_payload(config_path),
        )
        signature = _build_profile_signature(profile)
        grouped_case_ids.setdefault(signature, []).append(case_id)

    duplicate_groups = [tuple(sorted(ids)) for ids in grouped_case_ids.values() if len(ids) > 1]
    duplicate_case_sets = {frozenset(case_ids) for case_ids in duplicate_groups}
    unexpected_duplicates = sorted(duplicate_groups)
    unexpected_duplicates = [
        group
        for group in unexpected_duplicates
        if frozenset(group) not in _ALLOWED_DUPLICATE_SIGNATURE_CASE_SETS
    ]

    stale_allowlist = sorted([
        tuple(sorted(case_set))
        for case_set in _ALLOWED_DUPLICATE_SIGNATURE_CASE_SETS
        if case_set not in duplicate_case_sets
    ])

    assert not stale_allowlist, (
        f"remove stale profile-duplicate allowlist entries: {stale_allowlist}"
    )
    assert not unexpected_duplicates, (
        "duplicate case config signatures detected; "
        "adjust config dimensions or allowlist intentionally: "
        f"{unexpected_duplicates}"
    )
