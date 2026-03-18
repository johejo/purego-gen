set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

agent_nix_prefix := "nix develop .#coding-agent -c"
python_src_prefix := "scripts/uv-run-python-src.sh"
go_cache_env := "XDG_CACHE_HOME=$PWD/.cache GOMODCACHE=$PWD/.cache/gomod GOCACHE=$PWD/.cache/go-build STATICCHECK_CACHE=$PWD/.cache/staticcheck"

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
  if grep -RInE '# ruff: noqa|# noqa:|# pyright:|pyright: ignore' src tests scripts; then \
    echo "inline/static-analysis silencing comments are not allowed"; \
    exit 1; \
  fi

typecheck:
  uv run basedpyright
  unset PYTHONPATH; uv run pyrefly check .

test:
  uv run pytest

go-vet:
  mkdir -p .cache/gomod .cache/go-build .cache/staticcheck
  env {{go_cache_env}} go vet ./...

go-staticcheck:
  mkdir -p .cache/gomod .cache/go-build .cache/staticcheck
  env {{go_cache_env}} staticcheck ./...

go-test:
  mkdir -p .cache/gomod .cache/go-build .cache/staticcheck
  env {{go_cache_env}} go test ./...

inspect-libzstd:
  {{python_src_prefix}} scripts/inspect_target_library.py --header-path "$PUREGO_GEN_TEST_LIBZSTD_INCLUDE_DIR/zstd.h"

golden-update:
  {{python_src_prefix}} scripts/golden_cases.py --mode update

golden-check:
  {{python_src_prefix}} scripts/golden_cases.py --mode check

golden-check-nix:
  golden_cases_runner="$(nix build .#golden-cases --print-out-paths --no-link)/bin/golden-cases"; \
  "$golden_cases_runner" --mode check

golden-check-ci:
  {{python_src_prefix}} scripts/golden_cases.py --mode check --strict-head

golden-check-ci-nix:
  golden_cases_runner="$(nix build .#golden-cases --print-out-paths --no-link)/bin/golden-cases"; \
  "$golden_cases_runner" --mode check --strict-head

tool-version-check:
  scripts/check-tool-versions.sh

check: nix-flake-check lint typecheck golden-check test go-vet go-staticcheck go-test

ci: nix-flake-check tool-version-check lint typecheck golden-check golden-check-nix test go-vet go-staticcheck go-test

ci-strict: nix-flake-check tool-version-check lint typecheck golden-check-ci golden-check-ci-nix test go-vet go-staticcheck go-test

# Codex sandbox helper tasks

agent-check:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just check

agent-ci:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just ci

agent-ci-strict:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just ci-strict
