## Objective

Build a practical code generator that turns C headers into Go bindings for
[ebitengine/purego](https://github.com/ebitengine/purego), with stable behavior
and predictable output.

This document defines the current implementation contract. Additions are allowed,
but existing contracts should not change without explicit versioning or migration notes.

## Document Roles

- `README.md` is the quick-start and high-level project summary.
- `DESIGN.md` (this file) is the normative behavior contract.
- `TODO.md` is the execution plan and milestone tracker.
- Keep `README.md` concise; do not duplicate contract-level detail from this file.

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
- Use `uv` for Python dependency management. Do not invoke `python3` directly.
- Use libclang Python bindings as the single source of truth for C AST/type info.
- Use `basedpyright` and `pyrefly` for static type checks.
- Use `ruff` for linting/formatting.
- Use `actionlint` for GitHub Actions workflow linting.
- Use `shellcheck` for shell script linting (`scripts/*.sh`).
- Use `shfmt` for shell script formatting (`scripts/*.sh`).
- Use `treefmt` as the formatter orchestrator across file types.
- Use `clang-format` (`.clang-format`, LLVM-based) for test fixture C headers.
- Use `pytest` for tests.
- Prefer end-to-end golden tests for generator behavior; use unit tests for utilities.
- Keep templates simple; keep logic in generator code.

## Development Workflow Contract

- Development shell is provided via `nix develop` and must include `uv`, `just`,
  `treefmt`, Go toolchain, and libclang.
- Development shell also includes `ccache`.
- Default dev shell (`nix develop`) does not override user/environment cache defaults.
- Python tool configuration lives in `pyproject.toml`; tools are invoked via
  `uv run ...`.
- Project automation entrypoint is `just` (`Justfile` is the source of truth
  for recipe names and wiring).
- GitHub Actions CI executes through `just` recipes.
- `just check` is local-first and must work in dirty/uncommitted working trees.
- `just ci` is strict and CI-oriented (`format-check`, strict golden drift checks,
  and `djlint` version parity between Nix and `uv.lock`).
- Formatting scope includes `tests/fixtures/*.h` via `clang-format` and
  `scripts/*.sh` via `shfmt` in `treefmt`.

## Architecture

Pipeline:
1. Parse: Build translation unit(s) from input headers + clang args.
2. Normalize: Convert clang AST nodes into internal declaration models.
3. Filter: Apply category-specific filters (`func`, `type`, `const`, `var`).
4. Emit: Render Go code from normalized models (via templates).
5. Validate: Run formatting and compile/smoke checks in tests.
   - Compile smoke checks use a pinned real `github.com/ebitengine/purego`
     module in fixture modules (no local stub replacement).

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
  - Source: enum members and supported object-like integer macros.
  - Supported macro-expression subset: integer literals (including `U`/`L`
    suffixes), references to already-known constants, unary `+/-/~`, and
    binary `+ - * / % << >> | & ^` with parentheses.
  - Output: Go `const` values.
  - Important: these are not loaded via `Dlsym`.

- Runtime variables (exported data symbols):
  - Source: `extern` variables exported by shared library.
  - Output: Go `uintptr` symbol-address vars populated by symbol lookup.
  - Loaded via `Dlsym` in M2; richer typed conversion is deferred.

This split removes ambiguity between "constant" and "data symbol".

## Type Mapping Rules (M3 Baseline)

- Basic numeric typedefs map to fixed-width Go primitives (`int32`, `uint32`,
  `int64`, `uint64`, etc.) based on libclang canonical type kind.
- Enum typedefs map to `int32`.
- Pointer typedefs map to `uintptr`.
- Function-pointer typedefs are supported in v1 as raw symbol-sized values and
  also map to `uintptr` (no callback trampoline generation yet).
- Function signatures keep pointer-like C types as `uintptr` by default.
- Optional CLI mode `--const-char-as-string` maps `const char*` function
  result/parameter slots to Go `string`.
- Mutable `char*` in function signatures remains `uintptr` even when
  `--const-char-as-string` is enabled, to avoid treating writable/output
  buffers as immutable strings.
- `void*` / `const void*` in function signatures remains `uintptr` (no
  size-heuristic or buffer-shape inference in v1), regardless of
  `--const-char-as-string`.
- v1 function-pointer support boundary is intentionally low-level:
  - supported: opaque `uintptr` mapping for function-pointer declarations.
  - unsupported: callback trampoline/codegen flows and signature-aware wrappers.
- Struct typedefs with fully mappable fields are emitted as Go `struct { ... }`
  type literals (`field` types are mapped with the same baseline rules).
- Nested struct fields are supported when nested field types are also mappable.
- Struct field kinds currently unsupported in v1: arrays, unions, bitfields,
  and anonymous fields.
- Incomplete/opaque struct typedefs are emitted as `uintptr` aliases for
  handle-style interop.
- Optional CLI mode `--strict-opaque-handles` emits only opaque struct-handle
  typedefs as strict Go types (`type T uintptr`) instead of aliases.
- `--strict-opaque-handles` has effect only when `--emit` includes `type`.
- When an opaque typedef alias is emitted (`--emit` includes `type`), function
  signatures use the emitted alias (`purego_type_*`) for matching `T*` /
  `const T*` result and parameter types instead of raw `uintptr`.
- If matching opaque aliases are not emitted (for example `--emit func` only),
  function signatures keep `uintptr` fallback for those types.
- Nested/unsupported record typedefs that are not representable by the current
  baseline mapping are skipped from emitted type aliases.
- When a typedef is skipped due to unsupported record mapping, the CLI emits a
  stderr diagnostic with both a stable diagnostic code and human-readable
  reason.
- The parser model also retains these type-diagnostic codes (record-level and
  field-level) so ABI-focused tests can assert unsupported behavior without
  depending on exact stderr phrasing.

## M4 ABI Input Boundary (Prework)

- Parser now exposes structured record typedef metadata (`record_typedefs`)
  including record-level and field-level layout attributes (size/align/offset
  when available from clang).
- ABI layout utility now recomputes expected struct field offsets, struct
  alignment, and final size from field metadata and compares them with
  clang-reported values for supported records.
- ABI layout utility emits stable diagnostic codes for unsupported records and
  layout-metadata mismatches so tests can assert outcomes deterministically.
- ABI layout diagnostics for unsupported ABI-sensitive patterns keep the source
  type-diagnostic code (from parser metadata) so unsupported causes can be
  asserted without depending on human-readable text.
- ABI layout validation fallback behavior is explicit per record:
  - `passed`: no layout diagnostics.
  - `failed`: deterministic layout mismatch diagnostics exist (offset/align/size).
  - `skipped`: validation could not be completed due to unsupported patterns or
    incomplete metadata; diagnostics are still emitted and carry fallback reason.
- In v1, ABI fallback results are surfaced through harness/test reports using
  ABI utility outputs; default `purego-gen` CLI output remains focused on
  generation diagnostics.
- Intended v1 ABI-check target set:
  - struct typedefs with supported field kinds and available clang layout data.
- Current non-target set for v1 ABI checks:
  - union typedefs
  - structs with arrays, bitfields, or anonymous fields
  - opaque/incomplete record typedefs

## Generated Code Contract

Generated file header:
- Must include `// Code generated by purego-gen; DO NOT EDIT.`

Naming:
- All generated identifiers are unexported.
- All generated identifiers must start with `purego_`.
- Generated declaration identifiers keep category-specific prefixes:
  - `purego_func_<symbol>`
  - `purego_type_<symbol>`
  - `purego_const_<symbol>`
  - `purego_var_<symbol>`
- The `<symbol>` suffix preserves C-side casing as much as possible.
- Non-identifier characters in `<symbol>` are normalized to `_`.
- If `<symbol>` starts with a digit, generated suffix adds `n_` prefix.
- If `<symbol>` is a Go keyword, generated suffix appends `_`.
- Same-category collisions after normalization use deterministic numeric suffixes
  (`_2`, `_3`, ...).
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
- Generated function placeholders are typed Go function values derived from parsed C signatures
  (with `uintptr` fallback for currently unsupported types, and emitted opaque-handle aliases
  used when available) and are bound via `RegisterFunc`.
- Generated function parameter names are taken from C declarations when available and sanitized
  into Go identifiers; unnamed/invalid slots fall back to deterministic `argN` names.
- Function signature convenience mapping in v1 is intentionally narrow and
  opt-in: with `--const-char-as-string`, only `const char*` is lifted to Go
  `string`; mutable `char*` and `void*` remain low-level pointer-sized values.
- `purego_<libid>_load_runtime_vars` resolves exported data symbols, stores their addresses in `purego_var_* uintptr`, and returns an error on missing required symbols.
- All emitted runtime symbols are required; generated helpers return errors
  when symbol resolution fails.
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
- If a category filter is provided for an emitted category and matches nothing, CLI exits non-zero with an actionable error.
- `--emit` controls which categories are generated.
- `--const-char-as-string` is opt-in and disabled by default.
- `--strict-opaque-handles` is opt-in and disabled by default.
- `--out <path>` writes to a file.
- `--out -` or omitted `--out` writes generated code to stdout.
- Generated Go source is formatted with `gofmt` before writing to stdout or files.
- Current CLI is single-command (`purego-gen`) with no subcommand.
- Diagnostics (warnings/progress/errors) must go to stderr, not stdout.
- On failure, exit non-zero with actionable error messages and do not emit partial generated code to stdout.
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
  - Include a minimal C-side probe fixture that emits `sizeof`/`alignof`/`offsetof`
    values for selected records and compare those values with parser metadata.

Objective harness targets:
- Must: `libzstd`
  - Baseline library for stable C API coverage and deterministic golden tests.
- Must: `onnxruntime`
  - Stress target for complex signatures and real-world API shape.
- Optional (Linux-only): `libsystemd`
  - Platform-dependent target to validate Linux integration paths.

M5 harness environment contract:
- Discovery order:
  - first: `pkg-config` (`--cflags`/`--libs`) for target libraries.
  - fallback: standard compiler/linker flags (`CPPFLAGS`/`CFLAGS`/`LDFLAGS`)
    and explicit include/library options (`-I`/`-L`).
- Dedicated per-library include/lib environment variables are intentionally not
  part of the baseline M5 contract.
- Runtime harness tests should accept explicit shared-library path overrides via
  environment variables rather than assuming system loader paths.

## Roadmap Tracking

- Milestones and open decisions are tracked in
  [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md).
