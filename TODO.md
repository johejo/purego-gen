# TODO

## M0 Development Tooling Baseline

- [x] Establish a reproducible Nix-based development baseline (`devShell` and toolchain), while keeping Codex-local cache defaults scoped to `agent` recipes.
- [x] Standardize automation entrypoints in `Justfile` (`format`, `check`, `ci`) with local-vs-CI role separation.
- [x] Integrate formatting/lint/typecheck/test and golden drift verification into the project gate flow.
- [x] Wire GitHub Actions CI to run the strict `just ci` flow (format-check, strict golden drift checks, and `djlint` version parity) on pinned runners.

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
- [x] Remove `go.mod replace`-based purego stubs from compile smoke fixtures and pin real purego dependency.

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

- [x] Expand struct/enum/typedef coverage for common C patterns.
- [x] Document pointer mapping rules used by the generator.
- [x] Add limited function-pointer support for v1 target subset.
- [x] Add unit tests for type mapping edge cases.
- [x] Add golden fixtures with nested/opaque types.
- [x] Define explicit support boundary for struct field kinds in v1 (`array`, `union`, bitfield, anonymous field).
- [x] Add focused tests for nested-record typedef handling policy (supported vs skipped).
- [x] Add explicit diagnostics when typedefs are skipped due to unsupported record field types.

## M4 ABI Validation

- [x] Add a pre-M4 typed declaration model for records/fields (beyond string-only `go_type`) to support deterministic ABI calculations.
- [x] Add a minimal ABI fixture harness that captures C-side `sizeof`/`alignof`/`offsetof` values for comparison tests.
- [x] Promote skipped-type diagnostics to structured diagnostic codes (not stderr text only) so ABI tests can assert behavior stably.
- [x] Document M4 ABI-validation input boundary in `DESIGN.md` (which record patterns are in/out for v1 ABI checks).
- [x] Split parser-vs-ABI-model tests (`tests/test_clang_parser.py` vs dedicated ABI model tests) to reduce coupling before M4 implementation.
- [x] Add layout check utility for struct size/alignment against clang metadata.
- [x] Emit clear diagnostics for unsupported ABI-sensitive patterns.
- [x] Add ABI-focused tests for supported structs.
- [x] Define fallback behavior when ABI validation cannot be completed.

## M5 Target Libraries (Objective Harness)

- [x] Add `libzstd` harness fixture and golden outputs (must).
- [ ] Add `onnxruntime` harness fixture and golden outputs (must).
- [ ] Add optional Linux-only `libsystemd` harness fixture.
- [ ] Wire target-library jobs into CI matrix with platform guards.
- [ ] Record known unsupported declarations per library.

## M5.5 libzstd Practical Usability

- [x] Generate typed function signatures (result + params) instead of `func()` placeholders for selected `libzstd` APIs.
- [ ] Introduce opaque-handle type emission policy for incomplete structs (`ZSTD_CCtx` / `ZSTD_DCtx` / `ZSTD_CDict` / `ZSTD_DDict`) so pointer-based APIs can be represented safely.
- [ ] Extend constant extraction beyond enum constants to object-like macro constants required by `libzstd` (`ZSTD_VERSION_*`, magic/content-size related values).
- [ ] Add symbol requirement metadata (`required` vs `optional`) and generate registration flow that can tolerate optional symbol absence when configured.
- [x] Add runtime harness scenario that performs real block compress/decompress roundtrip using generated bindings (not symbol-resolution only).
- [ ] Define and document a stable `libzstd` API subset profile for v1 generation tests (allowlist-based to reduce cross-version drift).

## Pre-M5 Hardening

- [x] Define where ABI layout fallback results (`passed`/`failed`/`skipped`) are surfaced (CLI vs harness report).
- [x] Add strict CI mode for `golden-check` that always compares against `HEAD` only.
- [x] Normalize golden case manifest schema to one header field shape (`header_paths`).
- [x] Document M5 harness environment contract (header/library discovery strategy and fallback flags).
- [x] Resolve open decisions required by M5 execution (function pointer boundary and optional symbol policy).

## Backlog / Open Decisions

- [x] Decide v1 support boundary for function pointers.
- [x] Decide optional symbol policy (`warn` vs `error`).
- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Define trigger criteria for introducing `--config <file>`.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
