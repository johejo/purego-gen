# TODO

Active tasks and unresolved decisions only.
Completed work is intentionally omitted.

## Target Library Coverage

- [ ] Add `onnxruntime` harness fixture and golden outputs.
- [ ] Add optional Linux-only `libsystemd` harness fixture.
- [ ] Wire target-library jobs into the CI matrix with platform guards.

## Future Capabilities

- [x] Detect `typedef struct { void *internal_ptr; } *name` as an opaque handle pattern and generate a distinct named type (like forward-declared opaque structs), instead of collapsing all such handles to bare `uintptr`. Found via DuckDB: all handles (`duckdb_database`, `duckdb_connection`, etc.) lose type distinction in generated code.
- [ ] Add basic union typedef support, at minimum for tagged unions and single-member-struct-containing-union patterns. Currently all structs with union fields are skipped entirely (`TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF`). Found via DuckDB: `duckdb_string_t` (inline/pointer string union) required fully manual handling.
- [ ] Add an option to generate exported accessor methods for struct fields, so downstream packages can read field values without `unsafe.Pointer` arithmetic. Currently all struct fields are emitted as unexported (lowercase), matching C naming. Found via DuckDB: `duckdb_date_struct`, `duckdb_time_struct` etc. required manual unsafe accessors in the wrapper layer.
- [ ] Add ownership/lifetime annotation for `const char *` return values so `const_char_as_string` can distinguish "borrowed" returns (no free needed) from "owned" returns (caller must free). Currently the Go string copy is always made but the original C pointer is never freed, causing a memory leak for owned returns. Found via DuckDB: `duckdb_parameter_name` returns a `const char *` that must be freed with `duckdb_free`.
- [ ] Add support for in-memory overlays via `CXUnsavedFile` so parsing can work without relying on on-disk headers.

## UX Improvements

- [ ] Add a broad declaration-collection mode so users can start from "generate everything supported" and then narrow with excludes instead of large allowlists.
- [ ] Add opt-in mapping policies for common C API patterns such as nullable `const char *`, blob-like `const void *`, and similar pointer/value conventions that currently force handwritten call-site boilerplate.
- [ ] Improve generic callback/destructor ergonomics so common function-pointer registration patterns require less handwritten marshalling around generated bindings.
- [ ] Add callback-helper candidate inventory and a staged path toward partial auto-generation so function-pointer-heavy libraries can opt into safe patterns without hand-enumerating every helper target.
- [ ] Strengthen type classification and conversion heuristics for helper generation so callback/buffer/string-like patterns can be recognized from typedef-heavy signatures before any partial auto-generation mode.
- [ ] Emit a clearer supported/skipped declaration inventory so users can quickly see what still requires handwritten code after generation.
- [ ] Explore an optional helper-layer generation mode that builds small ergonomic wrappers on top of the low-level purego bindings without baking target-library-specific policy into the core generator.
- [ ] Add an opt-in downstream package scaffold mode that can emit a private raw package config plus symbol-loader/bootstrap glue so practical driver/wrapper packages need less handwritten setup around generated bindings.

## Open Decisions

- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
