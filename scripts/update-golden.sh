#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYTHONPATH=src uv run python -m purego_gen \
  --lib-id sample_lib \
  --header tests/fixtures/sample.h \
  --pkg sample \
  --emit func,type \
  -- \
  -I./include > tests/golden/sample_func_type.go

PYTHONPATH=src uv run python -m purego_gen \
  --lib-id sample_lib \
  --header tests/fixtures/sample_categories.h \
  --pkg sample \
  --emit const > tests/golden/sample_const.go
