# Copyright (c) 2026 purego-gen contributors.

"""Shared stdout/stderr assertion helpers for tests."""

from __future__ import annotations


def collapse_whitespace(text: str) -> str:
    """Normalize arbitrary whitespace into single ASCII spaces.

    Returns:
        Whitespace-collapsed string.
    """
    return " ".join(text.split())


def assert_text_contains_fragments(
    text: str,
    fragments: tuple[str, ...],
    *,
    normalize_whitespace: bool = False,
    label: str = "stdout",
) -> None:
    """Assert that all fragments are present in text.

    Args:
        text: Raw text to inspect.
        fragments: Required fragments.
        normalize_whitespace: Collapse whitespace before matching when `True`.
        label: Human-readable name used in error messages.

    Raises:
        AssertionError: One or more fragments are missing.
    """
    inspected = collapse_whitespace(text) if normalize_whitespace else text
    missing = tuple(fragment for fragment in fragments if fragment not in inspected)
    if not missing:
        return

    quoted_missing = ", ".join(repr(fragment) for fragment in missing)
    message = f"missing {label} fragments ({len(missing)}): {quoted_missing}"
    raise AssertionError(message)


def combined_output(stdout: str, stderr: str) -> str:
    """Concatenate stdout/stderr for failure-path assertions.

    Returns:
        `stdout` and `stderr` concatenated in order.
    """
    return stdout + stderr
