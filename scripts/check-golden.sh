#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

tmp_func_type="$(mktemp)"
tmp_const="$(mktemp)"
head_func_type="$(mktemp)"
head_const="$(mktemp)"
trap 'rm -f "$tmp_func_type" "$tmp_const" "$head_func_type" "$head_const"' EXIT

PYTHONPATH=src uv run python -m purego_gen \
  --lib-id sample_lib \
  --header tests/fixtures/sample.h \
  --pkg sample \
  --emit func,type \
  -- \
  -I./include > "$tmp_func_type"

PYTHONPATH=src uv run python -m purego_gen \
  --lib-id sample_lib \
  --header tests/fixtures/sample_categories.h \
  --pkg sample \
  --emit const > "$tmp_const"

git show HEAD:tests/golden/sample_func_type.go > "$head_func_type"
git show HEAD:tests/golden/sample_const.go > "$head_const"

if ! diff -u "$head_func_type" "$tmp_func_type"; then
  echo "golden drift detected against HEAD: run 'nix develop -c just golden-update' and commit golden changes." >&2
  exit 1
fi

if ! diff -u "$head_const" "$tmp_const"; then
  echo "golden drift detected against HEAD: run 'nix develop -c just golden-update' and commit golden changes." >&2
  exit 1
fi
