set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

agent_nix_prefix := "nix develop .#coding-agent -c"
python_src_prefix := "scripts/uv-run-python-src.sh"

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
  just silence-check
  actionlint
  uv run ruff check .
  uv run ruff format --check .
  uv run djlint --check --extension=j2 --preserve-leading-space --preserve-blank-lines templates/
  shellcheck scripts/*.sh
  shfmt -d scripts/*.sh

silence-check:
  if rg -n '# ruff: noqa|# noqa:|# pyright:|pyright: ignore' src tests scripts; then \
    echo "inline/static-analysis silencing comments are not allowed"; \
    exit 1; \
  fi

typecheck:
  uv run basedpyright
  unset PYTHONPATH; uv run pyrefly check .

test:
  uv run pytest

inspect-libzstd:
  {{python_src_prefix}} scripts/inspect_target_library.py --pkg-config-package libzstd --header zstd.h

golden-update:
  {{python_src_prefix}} scripts/golden_cases.py --mode update

golden-check:
  {{python_src_prefix}} scripts/golden_cases.py --mode check

golden-check-ci:
  {{python_src_prefix}} scripts/golden_cases.py --mode check --strict-head

tool-version-check:
  scripts/check-tool-versions.sh

check: nix-flake-check lint typecheck golden-check test

ci: nix-flake-check tool-version-check lint typecheck golden-check-ci test

# Codex sandbox helper tasks

agent-check:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just check

agent-ci:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just ci
