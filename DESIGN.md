## Objective

Build a practical code generator that turns C headers into Go bindings for
[ebitengine/purego](https://github.com/ebitengine/purego), with stable behavior
and predictable output.

This document defines the current implementation contract. Additions are allowed,
but existing contracts should not change without explicit versioning or migration notes.

## Scope

In scope:
- Parse C declarations from headers via libclang.
- Generate Go code for function bindings, selected types, constants, and runtime variables.
- Provide deterministic output suitable for golden testing.
- Support platform-specific parsing through user-provided clang arguments.

Out of scope (for now):
- Full C preprocessor emulation beyond what clang already provides.
- Automatic library loading policy (callers own open/close lifecycle).
- Perfect support for every C edge case in v1.
- Generating ergonomic public Go APIs from C headers. Consumers define public wrappers manually.
- Windows support in v1.

## Design Principles

- Use `nix flake` for reproducible development/build environment.
- Use `just` for project automation tasks.
- Use `lefthook` for local git hooks (`pre-commit` and `pre-push`).
- Use `uv` for Python dependency management. Do not invoke `python3` directly.
- Use libclang Python bindings as the single source of truth for C AST/type info.
- Use `basedpyright` and `pyrefly` for static type checks.
- Use `ruff` for linting/formatting.
- Use `treefmt` as the formatter orchestrator across file types.
- Use `clang-format` (`.clang-format`, LLVM-based) for test fixture C headers.
- Use `pytest` for tests.
- Prefer end-to-end golden tests for generator behavior; use unit tests for utilities.
- Keep templates simple; keep logic in generator code.
- All generated identifiers are unexported and use the `purego_` prefix.

## Development Workflow Contract

- Development shell is provided via `nix develop` and must include `uv`, `just`,
  `lefthook`, `treefmt`, Go toolchain, and libclang.
- Python tool configuration lives in `pyproject.toml`; tools are invoked via
  `uv run ...`.
- Project automation entrypoint is `just` with recipes:
  - `bootstrap` (install dev dependencies + install git hooks)
  - `nix-flake-check` (run `nix flake check`)
  - `fmt` (run `nix fmt`)
  - `fmt-check` (run `nix fmt -- --fail-on-change`)
  - `lint` (run `ruff`)
  - `typecheck` (run `basedpyright` and `pyrefly`)
  - `golden-update` (regenerate committed golden outputs)
  - `golden-check` (verify generated output matches committed golden outputs at `HEAD`)
  - `test` (run `pytest`)
  - `check` (aggregate lint + typecheck + golden-check + test)
  - `gate` (run `fmt` -> `nix-flake-check` -> `check`)
  - `hook-gate` (run `fmt-check` for fast pre-commit)
  - `hook-push-gate` (run full `gate` for pre-push)
- Git hooks are managed via `lefthook`:
  - `pre-commit`: `just hook-gate`
  - `pre-push`: `just hook-push-gate`
- Formatting scope includes `tests/fixtures/*.h` via `clang-format` in `treefmt`.

## Architecture

Pipeline:
1. Parse: Build translation unit(s) from input headers + clang args.
2. Normalize: Convert clang AST nodes into internal declaration models.
3. Filter: Apply category-specific filters (`func`, `type`, `const`, `var`).
4. Emit: Render Go code from normalized models (via templates).
5. Validate: Run formatting and compile/smoke checks in tests.

Emit layer templating contract (M2.5):
- Rendering entrypoint lives in `src/purego_gen/renderer.py`; CLI orchestration in
  `src/purego_gen/cli.py` must not build Go source by string concatenation.
- Renderer prepares a normalized context, templates stay declarative:
  - `package`, `lib_id`, `emit_kinds`
  - `type_aliases[].identifier`, `type_aliases[].go_type`
  - `constants[].identifier`, `constants[].value`
  - `functions[].identifier`
  - `runtime_vars[].identifier`
- Jinja2 environment uses `StrictUndefined` so missing template variables fail deterministically.
- Renderer validates required top-level context keys before template execution.
- `gofmt` remains the final canonical formatting step after template rendering.

## purego Integration Strategy

What `purego-gen` should delegate to `purego`:
- ABI-specific call marshalling and return decoding via `purego.RegisterFunc`.
- Dynamic symbol loading primitives (`Dlsym`, platform-specific symbol lookup behavior).
- Callback trampolines via `purego.NewCallback` when callback interop is explicitly needed.

What `purego-gen` should keep as its own responsibility:
- C header parsing, declaration modeling, filtering, and code emission.
- ABI layout validation for generated Go structs.
- Symbol registration/error policy and generated API shape.

Design constraints from upstream `purego` behavior:
- Do not use `purego.SyscallN` for normal generated bindings; prefer `RegisterFunc` path.
- Avoid `RegisterLibFunc` in generated registration helpers because it panics on missing symbols.
- For v1 target OSes (non-Windows), use `Dlsym + RegisterFunc` so generated code can return typed errors instead of panicking.
- Function pointer arguments can allocate callback slots via `NewCallback`; default generation should avoid implicit callback-heavy APIs unless explicitly requested.
- Struct arguments/returns must follow `purego` platform support constraints; unsupported targets must fail with clear diagnostics.

## Declaration Model

The generator distinguishes declaration categories explicitly:

- Function declarations:
  - Source: C function declarations.
  - Output: Go function variables + register helper.

- Type declarations:
  - Source: structs/unions/enums/typedefs (supported subset by phase).
  - Output: Go type definitions with ABI-aware layout decisions.

- Compile-time constants:
  - Source: enum members, integer-like macro values resolvable from clang.
  - Output: Go `const` values.
  - Important: these are not loaded via `Dlsym`.

- Runtime variables (exported data symbols):
  - Source: `extern` variables exported by shared library.
  - Output: Go `var` values populated by symbol lookup.
  - Loaded via `Dlsym` + typed pointer/value conversion.

This split removes ambiguity between "constant" and "data symbol".

## Generated Code Contract

Generated file header:
- Must include `// Code generated by purego-gen; DO NOT EDIT.`

Naming:
- All generated identifiers are unexported.
- All generated identifiers must start with `purego_`.
- Current implementation keeps the prefix fixed to `purego_` for simplicity.
- Prefix customization may be added later if it becomes necessary.

Handle ownership:
- Generated code does not keep a global library handle.
- Callers pass `handle uintptr` to generated registration/loading functions.
- This keeps initialization explicit and supports multiple handles safely.

Required helper shape (conceptual):

```go
func purego_<libid>_register_functions(handle uintptr) error
func purego_<libid>_load_runtime_vars(handle uintptr) error
```

Behavior:
- `purego_<libid>_register_functions` resolves symbols with `purego.Dlsym` and binds with `purego.RegisterFunc`.
- `purego_<libid>_register_functions` returns an error for missing required symbols instead of panicking.
- `purego_<libid>_load_runtime_vars` resolves exported data symbols and returns an error on missing required symbols.
- Compile-time constants are emitted directly as Go constants and do not require runtime loading.

## CLI Contract

Example:

```sh
purego-gen \
  --lib-id zstd \
  --header foo.h \
  --header bar.h \
  --pkg mypkg \
  --out ./bindings_gen.go \
  --emit func,type,const,var \
  --func-filter '^(foo_|bar_)' \
  --type-filter '^(Foo|Bar)' \
  --const-filter '^(FOO_|BAR_)' \
  --var-filter '^(foo_|bar_)' \
  -- \
  -I./include -D_GNU_SOURCE
```

Stdout-oriented example:

```sh
purego-gen \
  --lib-id zstd \
  --header foo.h \
  --out - \
  -- \
  -I./include | gofmt
```

Rules:
- `--header` is repeatable and order-preserving.
- Multiple headers should be handled in a single invocation when they share the same generation context.
- Running the command multiple times is allowed, but cross-run merge/de-dup/conflict handling is caller responsibility.
- `--lib-id` is required and determines generated helper names to avoid multi-library symbol collisions.
- `--lib-id` is normalized to a safe snake_case identifier before code emission.
- `--` separates generator flags from clang flags.
- Filters are category-specific regexes and applied after normalization.
- `--emit` controls which categories are generated.
- Current implementation always generates `purego_`-prefixed identifiers.
- `--out <path>` writes to a file.
- `--out -` or omitted `--out` writes generated code to stdout.
- Generated Go source is formatted with `gofmt` before writing to stdout or files.
- Current CLI is single-command (`purego-gen`) with no subcommand.
- Diagnostics (warnings/progress/errors) must go to stderr, not stdout.
- On failure, exit with non-zero status and do not emit partial generated code to stdout.
- CLI failures must return non-zero exit code with actionable error messages.
- Current interface is intentionally flag-first to keep the design slim.
- A config file mode may be added later via `--config <file>` if repeated workflows justify it.

## Testing Strategy

- Unit tests:
  - Type mapping helpers.
  - Constant/runtime-variable classification.
  - Name sanitization and filtering behavior.

- End-to-end golden tests:
  - Input headers + clang args -> expected generated Go file.
  - Include platform-sensitive cases behind per-platform test fixtures.

- ABI-focused checks (phased):
  - Verify generated struct size/alignment against clang-reported layout where supported.

Objective harness targets:
- Must: `libzstd`
  - Baseline library for stable C API coverage and deterministic golden tests.
- Must: `onnxruntime`
  - Stress target for complex signatures and real-world API shape.
- Optional (Linux-only): `libsystemd`
  - Platform-dependent target to validate Linux integration paths.

## Milestones (Capability-Based)

M1: Core parsing and deterministic emission
- Parse functions + basic typedefs.
- Emit minimal compilable bindings.
- Golden test harness in place.

Current implementation note:
- `purego-gen` provides a single-command CLI entrypoint with flag parsing and
  clang-argument passthrough (`--`).
- Current parser phase extracts C function declarations and basic typedefs via libclang.

M2 implementation note (partial):
- Declaration model now includes explicit categories for `func`, `type`, `const`, and `var`.
- Current `const` extraction covers enum constants.
- Current `var` extraction covers `extern` runtime data symbol declarations.
- Current `--emit` handling supports `func,type,const,var`, including Go `const` emission.

M2: Category-complete symbol model
- Implement explicit separation of `const` vs `runtime var`.
- Implement category-specific filters and `--emit`.

M3: Type system expansion
- Struct/enum coverage for common patterns.
- Pointer/function-pointer mapping rules documented and tested.

M4: ABI validation
- Add layout checks for supported struct cases.
- Add clear unsupported-case diagnostics.

M5: Target libraries
- Validate against objective harness targets (`libzstd`, `onnxruntime`) once M1-M4 are stable.
- Add `libsystemd` coverage as optional Linux-only validation.

## Open Decisions

- Exact supported subset for function pointers in v1.
- Policy for optional symbols (warn vs hard error).
- How much macro evaluation to support beyond enum-like values.
- Trigger criteria for introducing `--config` (e.g., complexity threshold or repeated CI use).
