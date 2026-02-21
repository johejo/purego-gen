set shell := ["zsh", "-eu", "-o", "pipefail", "-c"]

default:
  @just --list

bootstrap:
  uv sync --group dev --python 3.14
  lefthook install

nix-fmt:
  nix fmt

nix-flake-check:
  nix flake check

fmt:
  treefmt

lint:
  uv run ruff check .
  uv run ruff format --check .

typecheck:
  uv run basedpyright
  env -u PYTHONPATH uv run pyrefly check .

test:
  uv run pytest

check: lint typecheck test

gate: nix-fmt nix-flake-check check

hook-gate: gate

hook:
  lefthook run pre-commit
