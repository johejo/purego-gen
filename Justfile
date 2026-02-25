set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

agent_nix_prefix := "env XDG_CACHE_HOME=$PWD/.cache GOMODCACHE=$PWD/.cache/gomod GOCACHE=$PWD/.cache/go-build CCACHE_DIR=$PWD/.cache/ccache CCACHE_BASEDIR=$PWD CCACHE_NOHASHDIR=1 UV_PROJECT_ENVIRONMENT=.venv nix develop -c"

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

golden-update:
  scripts/update-golden.sh

golden-check:
  scripts/check-golden.sh

golden-check-ci:
  GOLDEN_CHECK_STRICT_HEAD=1 scripts/check-golden.sh

check: lint typecheck golden-check test

ci: format-check nix-flake-check lint typecheck golden-check-ci test

# Codex sandbox helper tasks

agent-check:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just check

agent-ci:
  mkdir -p .cache/nix .cache/gomod .cache/go-build .cache/ccache
  {{agent_nix_prefix}} just ci
