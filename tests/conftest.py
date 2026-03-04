# Copyright (c) 2026 purego-gen contributors.

"""Pytest session-level configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def pytest_sessionstart(session: pytest.Session) -> None:
    """Fail fast when libclang is not configured for tests.

    Raises:
        pytest.UsageError: `LIBCLANG_PATH` is not set.
    """
    _ = session
    if os.environ.get("LIBCLANG_PATH"):
        return
    message = "LIBCLANG_PATH must be set for tests."
    raise pytest.UsageError(message)
