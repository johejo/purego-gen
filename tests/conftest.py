# Copyright (c) 2026 purego-gen contributors.

"""Pytest session-level configuration."""

from __future__ import annotations

import os

import pytest


def pytest_sessionstart(session: pytest.Session) -> None:  # noqa: ARG001
    """Fail fast when libclang is not configured for tests.

    Raises:
        pytest.UsageError: `LIBCLANG_PATH` is not set.
    """
    if os.environ.get("LIBCLANG_PATH"):
        return
    message = "LIBCLANG_PATH must be set for tests."
    raise pytest.UsageError(message)
