set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

python_src_prefix := "scripts/uv-run-python-src.sh"
default:
  @just --list

codex-orchestrate:
  ./scripts/codex-orchestrate.sh run

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
  go vet ./...

go-staticcheck:
  staticcheck ./...

go-test:
  go test ./...

go-generate:
  go generate ./...

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

zig_build_opts := "-Dlibclang-include-dir=\"${PUREGO_GEN_LIBCLANG_INCLUDE_DIR}\" \
  -Dlibclang-link-dir=\"${PUREGO_GEN_LIBCLANG_LINK_DIR}\" \
  -Dlibclang-link-mode=\"${PUREGO_GEN_LIBCLANG_LINK_MODE}\" \
  -Dllvm-link-dir=\"${PUREGO_GEN_LLVM_LINK_DIR}\" \
  -Dzlib-link-dir=\"${PUREGO_GEN_ZLIB_LINK_DIR}\" \
  -Dlibcxx-link-dir=\"${PUREGO_GEN_LIBCXX_LINK_DIR}\""

zig-build:
  zig build {{zig_build_opts}}

zig-test:
  zig build test {{zig_build_opts}}

zig-inspect *ARGS:
  zig build {{zig_build_opts}} && ./zig-out/bin/purego-gen-zig {{ARGS}}

zig-golden-check *ARGS:
  {{python_src_prefix}} scripts/zig_golden_cases.py {{ARGS}}

check: nix-flake-check lint typecheck golden-check test go-vet go-staticcheck go-test zig-build

ci: nix-flake-check lint typecheck golden-check golden-check-nix test go-vet go-staticcheck go-test zig-build

ci-strict: nix-flake-check lint typecheck golden-check-ci golden-check-ci-nix test go-vet go-staticcheck go-test zig-build
