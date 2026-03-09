## Objective / Document Boundary

Build a practical code generator that turns C headers into Go bindings for
[ebitengine/purego](https://github.com/ebitengine/purego), with stable behavior
and predictable output.

This document defines the current normative contract for parsing, declaration
modeling, code generation, generated output, and CLI behavior. Additions are
allowed, but existing contracts should not change without explicit versioning or
migration notes.

This document does not define:
- Development workflow or tool invocation details. See
  [`AGENTS.md`](./AGENTS.md).
- Quick start or project overview. See
  [`README.md`](./README.md).
- Active tasks, future work, or unresolved decisions. See
  [`TODO.md`](./TODO.md).

## Scope

In scope:
- Parse C declarations from headers via libclang.
- Generate Go code for function bindings, selected types, constants, and
  runtime variables.
- Provide deterministic output suitable for golden testing.
- Support platform-specific parsing through user-provided clang arguments.
- Target non-Windows platforms.

Out of scope:
- Full C preprocessor emulation beyond what clang already provides.
- Automatic library loading policy beyond generated symbol registration and data
  symbol lookup helpers.
- Perfect support for every C edge case.
- Generating ergonomic public Go APIs from C headers. Consumers define public
  wrappers manually.

## Generation Pipeline

Pipeline:
1. Parse: Build translation units from input headers and clang arguments.
2. Normalize: Convert clang AST nodes into internal declaration models.
3. Filter: Apply category-specific filters (`func`, `type`, `const`, `var`).
4. Emit: Render Go code from normalized models through templates.
5. Validate: Verify output through formatting and compile or smoke checks in
   tests.

Rendering contract:
- Rendering entrypoint lives in `src/purego_gen/renderer.py`; CLI orchestration
  in `src/purego_gen/cli.py` must not build Go source by string concatenation.
- Renderer prepares a normalized context and templates remain declarative.
- Required top-level template context keys are:
  - `package`
  - `lib_id`
  - `emit_kinds`
  - `type_aliases[].identifier`
  - `type_aliases[].go_type`
  - `constants[].identifier`
  - `constants[].value`
  - `functions[].identifier`
  - `runtime_vars[].identifier`
- The Jinja2 environment uses `StrictUndefined` so missing template variables
  fail deterministically.
- Renderer validates required top-level context keys before template execution.
- `gofmt` is the final canonical formatting step after template rendering.

## Integration Boundaries

`purego-gen` delegates these responsibilities to `purego`:
- ABI-specific call marshalling and return decoding via
  `purego.RegisterFunc`.
- Dynamic symbol loading primitives such as `Dlsym`.
- Callback trampolines via `purego.NewCallback` when callback interop is
  explicitly needed.

`purego-gen` keeps these responsibilities:
- C header parsing, declaration modeling, filtering, and code emission.
- ABI layout validation for generated Go structs.
- Symbol registration and error policy.
- Generated API shape and naming.

Integration constraints:
- Generated bindings use `purego.Dlsym` plus `purego.RegisterFunc` for normal
  function registration.
- Generated bindings do not use `purego.SyscallN` for standard bindings.
- Generated registration helpers do not use `RegisterLibFunc`, because missing
  symbols must produce typed errors instead of panics.
- Default generation keeps callback-heavy flows explicit; no signature-aware
  callback wrapper generation is required for function-pointer declarations.
- Struct arguments and returns must stay within `purego` platform support
  constraints. Unsupported targets must fail with clear diagnostics.

## Declaration Categories

The generator distinguishes declaration categories explicitly:

- Function declarations:
  - Source: C function declarations.
  - Output: Go function variables plus a registration helper.

- Type declarations:
  - Source: structs, unions, enums, and typedefs within the supported subset.
  - Output: Go type definitions with ABI-aware layout decisions.

- Compile-time constants:
  - Source: enum members and supported object-like integer macros.
  - Supported macro-expression subset: integer literals, including `U` and `L`
    suffixes; references to already-known constants; unary `+`, `-`, `~`; and
    binary `+`, `-`, `*`, `/`, `%`, `<<`, `>>`, `|`, `&`, `^` with
    parentheses.
  - Output: Go `const` values.
  - These are not loaded via `Dlsym`.

- Runtime variables:
  - Source: `extern` variables exported by a shared library.
  - Output: Go `uintptr` symbol-address variables populated by symbol lookup.
  - Typed conversion beyond raw symbol addresses is out of scope.

This split removes ambiguity between compile-time constants and exported data
symbols.

## Type Mapping Contract

- Basic numeric typedefs map to fixed-width Go primitives such as `int32`,
  `uint32`, `int64`, and `uint64`, based on libclang canonical type kind.
- Enum typedefs map to `int32`.
- Pointer typedefs map to `uintptr`.
- Function-pointer typedefs map to `uintptr`.
- Function signatures keep pointer-like C types as `uintptr` by default.
- `--const-char-as-string` maps `const char*` function result and parameter
  slots to Go `string`.
- Mutable `char*` in function signatures remains `uintptr` even when
  `--const-char-as-string` is enabled.
- `void*` and `const void*` in function signatures remain `uintptr`,
  regardless of `--const-char-as-string`.
- Function-pointer support is intentionally low-level:
  - Supported: opaque `uintptr` mapping for function-pointer declarations.
  - Unsupported: callback trampoline code generation and signature-aware
    wrappers.
- Struct typedefs with fully mappable fields are emitted as Go `struct { ... }`
  type literals.
- Nested struct fields are supported when nested field types are also
  mappable.
- Unsupported struct field kinds are arrays, unions, bitfields, and anonymous
  fields.
- Incomplete struct typedefs are treated as opaque handles.
- Opaque struct-handle typedefs are emitted as strict Go types (`type T
  uintptr`) when `--emit` includes `type`.
- Unsupported struct patterns do not fall back to opaque handles.
- `--strict-enum-typedefs` emits enum typedef aliases as strict Go types
  (`type T int32`) when `--emit` includes `type`.
- `--strict-enum-typedefs` has effect only when `--emit` includes `type`.
- `--typed-sentinel-constants` emits large sentinel-style compile-time
  constants (`value > MaxInt64`) as typed `uint64` constants.
- When an opaque typedef alias is emitted, matching `T*` and `const T*`
  function result and parameter types use the emitted `purego_type_*` alias
  instead of raw `uintptr`.
- When strict enum typedef aliases are emitted, matching function result and
  parameter slots use the emitted `purego_type_*` alias instead of raw `int32`.
- If matching opaque aliases are not emitted, function signatures keep the
  `uintptr` fallback.
- If matching strict enum aliases are not emitted, function signatures keep the
  `int32` fallback.
- Nested or unsupported record typedefs that are not representable by the
  current mapping are skipped from emitted type aliases.
- When a typedef is skipped due to unsupported record mapping, the CLI emits a
  stderr diagnostic with both a stable diagnostic code and a human-readable
  reason.
- Stable generator and ABI diagnostic codes use the `PUREGO_GEN_` prefix.
- Incomplete opaque struct typedef metadata uses
  `PUREGO_GEN_TYPE_OPAQUE_INCOMPLETE_STRUCT` and remains distinct from
  `PUREGO_GEN_TYPE_NO_SUPPORTED_FIELDS`, which is used by unsupported empty or
  anonymous patterns.
- CLI stderr also emits stable opaque-summary diagnostics:
  `PUREGO_GEN_OPAQUE_EMITTED_COUNT` and
  `PUREGO_GEN_OPAQUE_FALLBACK_UINTPTR_COUNT`.
- The parser model retains type-diagnostic codes at record and field level so
  ABI-focused tests can assert unsupported behavior without depending on exact
  stderr phrasing.

## ABI Validation Contract

- Parser output exposes structured record typedef metadata in
  `record_typedefs`, including record-level and field-level layout attributes
  such as size, alignment, and field offsets when clang reports them.
- ABI layout validation recomputes expected struct field offsets, struct
  alignment, and final size from field metadata and compares them with clang
  layout data for supported records.
- ABI layout validation emits stable diagnostic codes for unsupported records
  and layout mismatches.
- ABI layout diagnostics for unsupported ABI-sensitive patterns preserve the
  source type-diagnostic code from parser metadata.
- ABI validation produces one of these outcomes per record:
  - `passed`: no layout diagnostics.
  - `failed`: deterministic offset, alignment, or size mismatch diagnostics
    exist.
  - `skipped`: validation could not be completed because metadata is incomplete
    or the record uses unsupported patterns; diagnostics still carry the reason.
- ABI validation is targeted at struct typedefs with supported field kinds and
  available clang layout data.
- ABI validation does not target:
  - union typedefs
  - structs with arrays, bitfields, or anonymous fields
  - opaque or incomplete record typedefs
- ABI-focused reporting is available through test and harness flows; default
  CLI output remains focused on generation diagnostics.

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
- If `<symbol>` starts with a digit, the generated suffix adds `n_`.
- If `<symbol>` is a Go keyword, the generated suffix appends `_`.
- Same-category collisions after normalization use deterministic numeric
  suffixes such as `_2`, `_3`, and so on.
- The generated prefix is fixed to `purego_`.

Handle ownership:
- Generated code does not keep a global library handle.
- Callers pass `handle uintptr` to generated registration and loading helpers.
- This keeps initialization explicit and supports multiple handles safely.

Required helper shape:

```go
func purego_<libid>_register_functions(handle uintptr) error
func purego_<libid>_load_runtime_vars(handle uintptr) error
```

Behavior:
- `purego_<libid>_register_functions` resolves symbols with `purego.Dlsym` and
  binds them with `purego.RegisterFunc`.
- `purego_<libid>_register_functions` returns an error for missing required
  symbols instead of panicking.
- Generated function placeholders are typed Go function values derived from
  parsed C signatures, with the type-mapping fallbacks and emitted aliases
  defined by this document.
- Generated function parameter names are taken from C declarations when
  available and sanitized into Go identifiers; unnamed or invalid slots fall
  back to deterministic `argN` names.
- Generated declarations copy libclang declaration-attached C comments into
  preceding Go `//` comments when comment metadata is available.
- Plain C comments are included only when clang is invoked with
  `-fparse-all-comments`; otherwise doc-style declaration comments are the
  default source.
- `purego_<libid>_load_runtime_vars` resolves exported data symbols, stores
  their addresses in `purego_var_* uintptr`, and returns an error on missing
  required symbols.
- All emitted runtime symbols are required.
- Compile-time constants are emitted directly as Go constants and do not
  require runtime loading.
- Constants are untyped by default; `--typed-sentinel-constants` changes only
  qualifying sentinel-style values into typed `uint64` constants.

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
- Multiple headers should be handled in a single invocation when they share the
  same generation context.
- Running the command multiple times is allowed, but cross-run merge,
  de-duplication, and conflict handling are caller responsibility.
- `--lib-id` is required and determines generated helper names to avoid
  multi-library symbol collisions.
- `--lib-id` is normalized to a safe snake_case identifier before code
  emission.
- `--` separates generator flags from clang flags.
- Filters are category-specific regular expressions applied after
  normalization.
- If a category filter is provided for an emitted category and matches nothing,
  the CLI exits non-zero with an actionable error.
- `--emit` controls which categories are generated.
- `--const-char-as-string` is opt-in and disabled by default.
- `--strict-enum-typedefs` is opt-in and disabled by default.
- `--typed-sentinel-constants` is opt-in and disabled by default.
- `--out <path>` writes to a file.
- `--out -`, or omitting `--out`, writes generated code to stdout.
- Generated Go source is formatted with `gofmt` before writing to stdout or
  files.
- The CLI is single-command `purego-gen` with no subcommand layer.
- Diagnostics, including warnings, progress, and errors, go to stderr rather
  than stdout.
- On failure, the CLI exits non-zero with actionable error messages and does
  not emit partial generated code to stdout.

## Testing Strategy

- Unit tests cover:
  - type mapping helpers
  - constant and runtime-variable classification
  - name sanitization and filtering behavior
- End-to-end golden tests cover input headers plus clang arguments to expected
  generated Go files, including platform-sensitive cases behind per-platform
  fixtures.
- ABI-focused checks verify generated struct size and alignment against clang
  layout data where supported, including probe fixtures for `sizeof`,
  `alignof`, and `offsetof` comparisons.
- Library harness coverage should prioritize stable real-world targets such as
  `libzstd` and `onnxruntime`; optional Linux-only coverage may include
  `libsystemd`.
- Target-library header and runtime resolution must be explicit and
  profile-driven. Automatic library discovery through `pkg-config` or toolchain
  defaults is out of scope.
