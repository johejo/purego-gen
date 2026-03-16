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
- Emission uses declarative templates rather than ad-hoc string concatenation.
- Template rendering must fail deterministically when required inputs are
  missing.
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

- `func`: C function declarations emitted as Go function variables plus a
  registration helper.
- `type`: supported structs, unions, enums, and typedefs emitted as Go type
  definitions.
- `const`: enum members and supported object-like integer macros emitted as Go
  `const` values. Supported macro expressions are limited to integer literals,
  references to already-known constants, unary `+`, `-`, `~`, and binary
  arithmetic, bitwise, and shift operators with parentheses.
- `var`: exported `extern` data symbols emitted as Go `uintptr`
  symbol-address variables.

## Type Mapping Contract

- Primitive mappings:
  - Basic numeric typedefs map to fixed-width Go primitives based on libclang
    canonical type kind.
  - Enum typedefs map to `int32`.
  - Pointer and function-pointer typedefs map to `uintptr`.
- Function signatures:
  - Pointer-like C types map to `uintptr` by default.
  - `--const-char-as-string` maps only `const char*` result and parameter slots
    to Go `string`.
  - Mutable `char*`, `void*`, and `const void*` remain `uintptr` regardless of
    `--const-char-as-string`.
  - Function-pointer support remains opaque; callback trampoline generation and
    signature-aware wrappers are out of scope.
- Record and typedef emission:
  - Struct typedefs with fully mappable fields are emitted as Go `struct`
    literals.
  - Nested struct fields are supported when nested field types are also
    mappable.
  - Arrays, unions, bitfields, and anonymous fields are unsupported in struct
    emission.
  - Incomplete struct typedefs are treated as opaque handles.
  - Opaque struct-handle typedefs are emitted as strict Go types when `--emit`
    includes `type`.
  - Unsupported struct patterns do not fall back to opaque handles.
  - `--strict-enum-typedefs` emits enum typedef aliases as strict Go types only
    when `--emit` includes `type`.
  - Function signatures use emitted opaque or enum aliases only when the
    matching alias is emitted; otherwise they keep the primitive fallback.
- Constant and diagnostic behavior:
  - `--typed-sentinel-constants` emits large sentinel-style compile-time
    constants (`value > MaxInt64`) as typed `uint64` constants.
  - Nested or unsupported record typedefs that are not representable by the
    current mapping are skipped from emitted type aliases.
  - Skipped typedefs emit stderr diagnostics with stable `PUREGO_GEN_` codes
    plus human-readable reasons.
  - Incomplete opaque struct typedef metadata uses
    `PUREGO_GEN_TYPE_OPAQUE_INCOMPLETE_STRUCT`, distinct from
    `PUREGO_GEN_TYPE_NO_SUPPORTED_FIELDS`.
  - CLI stderr also emits `PUREGO_GEN_OPAQUE_EMITTED_COUNT` and
    `PUREGO_GEN_OPAQUE_FALLBACK_UINTPTR_COUNT`.
  - Parser metadata retains record-level and field-level type-diagnostic codes
    so tests can assert unsupported behavior without depending on stderr text.

## ABI Validation Contract

- Parser output exposes structured record typedef metadata in
  `record_typedefs`, including size, alignment, and field offsets when clang
  reports them.
- ABI validation recomputes expected field offsets, struct alignment, and final
  size from parser metadata and compares them with clang layout data.
- ABI validation emits stable diagnostics for unsupported records and layout
  mismatches, preserving the source type-diagnostic code for unsupported
  ABI-sensitive patterns.
- Each validated record ends in exactly one state:
  - `passed`
  - `failed`
  - `skipped`
- ABI validation targets only struct typedefs with supported field kinds and
  available clang layout data.
- Union typedefs, structs with arrays, bitfields, or anonymous fields, and
  opaque or incomplete record typedefs are outside ABI validation scope.
- ABI-focused reporting is available through test and harness flows; default
  CLI output remains focused on generation diagnostics.

## Generated Code Contract

- Generated file header must include `// Code generated by purego-gen; DO NOT EDIT.`
- All generated identifiers are unexported.
- All generated identifiers must start with `purego_`.
- Generated declaration identifiers use category-specific prefixes:
  `purego_func_`, `purego_type_`, `purego_const_`, and `purego_var_`.
- The `<symbol>` suffix preserves C-side casing as much as possible.
- Non-identifier characters in `<symbol>` are normalized to `_`.
- If `<symbol>` starts with a digit, the generated suffix adds `n_`.
- If `<symbol>` is a Go keyword, the generated suffix appends `_`.
- Same-category collisions after normalization use deterministic numeric
  suffixes such as `_2`, `_3`, and so on.
- The generated prefix is fixed to `purego_`.
- Generated code does not keep a global library handle.
- Callers pass `handle uintptr` to generated registration and loading helpers.
- Generated helpers have this shape:

```go
func purego_<libid>_register_functions(handle uintptr) error
func purego_<libid>_load_runtime_vars(handle uintptr) error
```

- `purego_<libid>_register_functions` resolves symbols with `purego.Dlsym` and
  binds them with `purego.RegisterFunc`; missing required symbols return
  errors rather than panics.
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

## CLI Contract

Rules:
- `--config <path>` is required and points at a JSON object with top-level
  `schema_version`, `generator`, and optional `golden`.
- `generator` carries generation inputs including `lib_id`, `package`,
  `emit`, `headers`, `filters`, `type_mapping`, and `clang_args`.
- `headers.kind` supports `local` and `env_include`.
- JSON-local relative paths resolve from the config file directory.
- `generator.lib_id` is normalized to a safe snake_case identifier before
  code emission.
- Filters are category-specific regular expressions applied after
  normalization.
- If a category filter is provided for an emitted category and matches nothing,
  the CLI exits non-zero with an actionable error.
- `--out <path>` writes to a file.
- `--out -`, or omitting `--out`, writes generated code to stdout.
- Generated Go source is formatted with `gofmt` before writing to stdout or
  files.
- Diagnostics, including warnings, progress, and errors, go to stderr rather
  than stdout.
- On failure, the CLI exits non-zero with actionable error messages and does
  not emit partial generated code to stdout.

## Testing Strategy

- Golden and other end-to-end tests are the primary validation layer.
- Unit tests are optional and should be limited to small pure logic where e2e
  coverage is inefficient.
- ABI-focused checks cover supported struct layout validation against clang
  metadata.
- Target-library header and runtime resolution must remain explicit and
  config-driven; automatic discovery is out of scope.
