set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

agent_nix_prefix := "nix develop .#coding-agent -c"
python_src_prefix := "env PYTHONPATH=src uv run python"

default:
  @just --list

# Day-to-day development tasks

format:
  nix fmt

format-check:
  nix fmt -- --fail-on-change

nix-flake-check:
  nix flake check

lint:
  actionlint
  uv run ruff check .
  uv run ruff format --check .
  uv run djlint --check --extension=j2 --preserve-leading-space --preserve-blank-lines templates/
  shellcheck scripts/*.sh
  shfmt -d scripts/*.sh

typecheck:
  uv run basedpyright
  env -u PYTHONPATH uv run pyrefly check .

test:
  uv run pytest

inspect-libzstd:
  {{python_src_prefix}} scripts/inspect-target-library.py --pkg-config-package libzstd --header zstd.h

go-fixture-update:
  {{python_src_prefix}} scripts/update-go-fixture-placeholders.py

go-fixture-check:
  {{python_src_prefix}} scripts/update-go-fixture-placeholders.py --check

golden-update:
  scripts/update-golden.sh

golden-check:
  scripts/check-golden.sh

golden-check-ci:
  GOLDEN_CHECK_STRICT_HEAD=1 scripts/check-golden.sh

tool-version-check:
  scripts/check-tool-versions.sh

check: lint typecheck golden-check test

ci: format-check nix-flake-check tool-version-check lint typecheck golden-check-ci test

# Codex sandbox helper tasks

agent-check:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just check

agent-ci:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just ci
