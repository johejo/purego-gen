# TODO

## M0 Development Tooling Baseline

- [x] Add `flake.nix` with a reproducible `devShell` for Python, Go, and libclang tooling.
- [x] Add `pyproject.toml` with `ruff`, `basedpyright`, `pyrefly`, and `pytest` configuration.
- [x] Add formatter orchestration with `treefmt`.
- [x] Add `clang-format` for test fixture C headers (`tests/fixtures/*.h`) via `treefmt`.
- [x] Add `shellcheck` for `scripts/*.sh` and wire it into lint/check flow.
- [x] Add `shfmt` for `scripts/*.sh` and wire it into fmt/lint flow.
- [x] Add git hook automation with `lefthook` (`pre-commit` runs fmt-only checks, `pre-push` runs full gate).
- [x] Add `Justfile` recipes for `bootstrap`, `nix-flake-check`, `fmt`, `fmt-check`, `lint`, `typecheck`, `test`, `check`, `gate`, `hook-gate`, and `hook-push-gate`.
- [x] Make `just fmt`/`just fmt-check` use `nix fmt` to keep hook formatting checks flake-aware.
- [x] Remove redundant `nix-fmt` alias and keep `fmt` as the single formatting entrypoint.
- [ ] Wire `nix develop -c just check` into CI.
- [x] Persist `ccache`, Go caches, and Nix user cache in repo-local ignored directories (`.cache/`) by wiring `CCACHE_DIR`/`GOCACHE`/`GOMODCACHE`/`XDG_CACHE_HOME` defaults in the dev shell.

## M1 Core Parsing and Deterministic Emission

- [x] Create project skeleton (`src/`, `templates/`, `tests/`).
- [x] Implement single-command CLI entrypoint (`purego-gen` without subcommands).
- [x] Support repeatable `--header` and clang args passthrough via `--`.
- [x] Parse function declarations and basic typedefs via libclang.
- [x] Build internal normalized model for `func` and minimal `type`.
- [x] Emit compilable Go output with generated header comment.
- [ ] Emit unexported `purego_`-prefixed identifiers only.
- [x] Implement `--out <path>` and stdout mode (`--out -` or omitted).
- [x] Format generated output with `gofmt` before writing.
- [x] Ensure diagnostics go to stderr and failures return non-zero.
- [x] Add first golden test fixture with a small synthetic header.

## M2 Category-Complete Symbol Model

- [x] Add declaration categories: `func`, `type`, `const`, `var`.
- [x] Implement explicit split between compile-time constants and runtime data symbols.
- [x] Implement `--emit func,type,const,var`.
- [x] Add required `--lib-id` and normalize it to snake_case-safe identifier.
- [x] Implement category filters: `--func-filter`, `--type-filter`, `--const-filter`, `--var-filter`.
- [x] Fail fast when a provided category filter matches no declarations in emitted categories.
- [x] Generate `purego_<libid>_register_functions(handle uintptr) error` (`Dlsym + RegisterFunc`, panic-free).
- [x] Generate `purego_<libid>_load_runtime_vars(handle uintptr) error`.
- [x] Add golden tests for mixed category selection and filtering behavior.

## M2.5 Emit Layer Templating (Jinja2)

- [x] Document emit-layer templating contract in `DESIGN.md` (logic stays in Python, templates stay declarative).
- [x] Add `jinja2` dependency and keep tooling checks green (`ruff`, `basedpyright`, `pyrefly`, `pytest`).
- [x] Add `djlint` for Jinja2 template lint/format and wire it into project checks.
- [x] Tune `djlint` options for Go-template readability, explicitly using `preserve-leading-space` and `preserve-blank-lines`.
- [x] Introduce a dedicated renderer module (e.g. `renderer.py`) and move output assembly out of `cli.py`.
- [x] Configure Jinja2 environment with strict undefined handling for deterministic failures.
- [x] Add initial Go file template(s) under `templates/` and migrate existing emit categories (`func`, `type`, `const`, `var`) without behavior changes.
- [x] Keep `gofmt` as the final formatting step after template rendering.
- [x] Preserve golden output equivalence for current fixtures (`tests/golden/*.go`), allowing only formatting-equivalent differences.
- [x] Add focused tests for template rendering context validation and missing-variable failures.
- [x] Remove obsolete string-concatenation render helpers from `cli.py` after migration.

## M3 Type System Expansion

- [ ] Expand struct/enum/typedef coverage for common C patterns.
- [x] Document pointer mapping rules used by the generator.
- [x] Add limited function-pointer support for v1 target subset.
- [x] Add unit tests for type mapping edge cases.
- [x] Add golden fixtures with nested/opaque types.

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
