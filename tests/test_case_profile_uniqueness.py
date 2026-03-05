# Copyright (c) 2026 purego-gen contributors.

"""Guards for accidental duplicate case profile signatures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CASES_DIR = _REPO_ROOT / "tests" / "cases"
_SIGNATURE_KEYS = (
    "schema_version",
    "lib_id",
    "emit",
    "headers",
    "filters",
    "type_mapping",
    "clang_args",
)
_ALLOWED_DUPLICATE_SIGNATURE_CASE_SETS: set[frozenset[str]] = set()

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def _normalize_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: _normalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _build_profile_signature(profile: dict[str, JsonValue]) -> str:
    signature_payload = {key: profile.get(key) for key in _SIGNATURE_KEYS}
    normalized_payload = _normalize_value(signature_payload)
    return json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"))


def test_case_profiles_are_unique_by_dedup_signature() -> None:
    """Cases should not share the same signature unless allowlisted."""
    grouped_case_ids: dict[str, list[str]] = {}
    for profile_path in sorted(_CASES_DIR.glob("*/profile.json")):
        case_id = profile_path.parent.name
        profile = cast(
            "dict[str, JsonValue]",
            json.loads(profile_path.read_text(encoding="utf-8")),
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
        "duplicate case profile signatures detected; "
        "adjust profile dimensions or allowlist intentionally: "
        f"{unexpected_duplicates}"
    )
