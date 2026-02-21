set shell := ["zsh", "-eu", "-o", "pipefail", "-c"]

default:
  @just --list

bootstrap:
  uv sync --group dev --python 3.14
  lefthook install

nix-flake-check:
  nix flake check

fmt:
  nix fmt

fmt-check:
  nix fmt -- --fail-on-change

lint:
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

check: lint typecheck golden-check test

gate: fmt nix-flake-check check

hook-gate: fmt-check

hook-push-gate: gate

hook:
  lefthook run pre-commit

template-fmt:
  uv run djlint --reformat --extension=j2 --preserve-leading-space --preserve-blank-lines templates/
