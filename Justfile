set shell := ["zsh", "-eu", "-o", "pipefail", "-c"]

uv_run := "uv run"
codex_nix_prefix := "XDG_CACHE_HOME=$PWD/.cache nix develop -c"
djlint_flags := "--check --extension=j2 --preserve-leading-space --preserve-blank-lines"

default:
  @just --list

# Bootstrap

bootstrap:
  uv sync --group dev --python 3.14
  lefthook install

# Formatting

fmt:
  nix fmt

fmt-check:
  nix fmt -- --fail-on-change

template-fmt:
  scripts/format-template-go.sh

# Validation

nix-flake-check:
  nix flake check

lint:
  actionlint
  {{uv_run}} ruff check .
  {{uv_run}} ruff format --check .
  {{uv_run}} djlint {{djlint_flags}} templates/
  shellcheck scripts/*.sh
  shfmt -d scripts/*.sh

typecheck:
  {{uv_run}} basedpyright
  env -u PYTHONPATH {{uv_run}} pyrefly check .

test:
  {{uv_run}} pytest

golden-update:
  scripts/update-golden.sh

golden-check:
  scripts/check-golden.sh

golden-check-ci:
  GOLDEN_CHECK_STRICT_HEAD=1 scripts/check-golden.sh

check: lint typecheck golden-check test

gate: fmt nix-flake-check check

# Hooks

hook:
  lefthook run pre-commit

hook-gate: fmt-check

hook-push-gate: gate

# Codex sandbox helpers

codex-check:
  {{codex_nix_prefix}} just check

codex-gate:
  {{codex_nix_prefix}} just gate
