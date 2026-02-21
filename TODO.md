# TODO

## M0 Development Tooling Baseline

- [x] Add `flake.nix` with a reproducible `devShell` for Python, Go, and libclang tooling.
- [x] Add `pyproject.toml` with `ruff`, `basedpyright`, `pyrefly`, and `pytest` configuration.
- [x] Add formatter orchestration with `treefmt`.
- [x] Add git hook automation with `lefthook` (`pre-commit` runs fmt-only checks, `pre-push` runs full gate).
- [x] Add `Justfile` recipes for `bootstrap`, `nix-fmt`, `nix-flake-check`, `fmt`, `fmt-check`, `lint`, `typecheck`, `test`, `check`, `gate`, `hook-gate`, and `hook-push-gate`.
- [ ] Wire `nix develop -c just check` into CI.

## M1 Core Parsing and Deterministic Emission

- [x] Create project skeleton (`src/`, `templates/`, `tests/`).
- [ ] Implement single-command CLI entrypoint (`purego-gen` without subcommands).
- [ ] Support repeatable `--header` and clang args passthrough via `--`.
- [ ] Parse function declarations and basic typedefs via libclang.
- [ ] Build internal normalized model for `func` and minimal `type`.
- [ ] Emit compilable Go output with generated header comment.
- [ ] Emit unexported `purego_`-prefixed identifiers only.
- [ ] Implement `--out <path>` and stdout mode (`--out -` or omitted).
- [ ] Ensure diagnostics go to stderr and failures return non-zero.
- [ ] Add first golden test fixture with a small synthetic header.

## M2 Category-Complete Symbol Model

- [ ] Add declaration categories: `func`, `type`, `const`, `var`.
- [ ] Implement explicit split between compile-time constants and runtime data symbols.
- [ ] Implement `--emit func,type,const,var`.
- [ ] Add required `--lib-id` and normalize it to snake_case-safe identifier.
- [ ] Implement category filters: `--func-filter`, `--type-filter`, `--const-filter`, `--var-filter`.
- [ ] Generate `purego_<libid>_register_functions(handle uintptr) error` (`Dlsym + RegisterFunc`, panic-free).
- [ ] Generate `purego_<libid>_load_runtime_vars(handle uintptr) error`.
- [ ] Add golden tests for mixed category selection and filtering behavior.

## M3 Type System Expansion

- [ ] Expand struct/enum/typedef coverage for common C patterns.
- [ ] Document pointer mapping rules used by the generator.
- [ ] Add limited function-pointer support for v1 target subset.
- [ ] Add unit tests for type mapping edge cases.
- [ ] Add golden fixtures with nested/opaque types.

## M4 ABI Validation

- [ ] Add layout check utility for struct size/alignment against clang metadata.
- [ ] Emit clear diagnostics for unsupported ABI-sensitive patterns.
- [ ] Add ABI-focused tests for supported structs.
- [ ] Define fallback behavior when ABI validation cannot be completed.

## M5 Target Libraries (Objective Harness)

- [ ] Add `libzstd` harness fixture and golden outputs (must).
- [ ] Add `onnxruntime` harness fixture and golden outputs (must).
- [ ] Add optional Linux-only `libsystemd` harness fixture.
- [ ] Wire target-library jobs into CI matrix with platform guards.
- [ ] Record known unsupported declarations per library.

## Backlog / Open Decisions

- [ ] Decide v1 support boundary for function pointers.
- [ ] Decide optional symbol policy (`warn` vs `error`).
- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Define trigger criteria for introducing `--config <file>`.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
