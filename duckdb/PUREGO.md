# purego Constraints

Limitations inherent to purego's FFI model that purego-gen cannot solve.

## Pointer types become `uintptr`

All C pointer types (`void*`, `int32_t*`, etc.) are represented as `uintptr` in purego.
Type safety is lost at the FFI boundary.

## Vector data access requires `unsafe`

`duckdb_vector_get_data()` returns `void*`. Converting to a typed Go slice requires
`unsafe.Pointer` and `unsafe.Slice`. This is unavoidable for any vector-based read/write.

## Callbacks require `purego.NewCallback()`

C function pointer parameters must be wrapped with `purego.NewCallback()`.
Lifetime management is the caller's responsibility (prevent GC of the Go function).

## Variadic C functions are unsupported

purego cannot call variadic C functions. This is not a practical issue for duckdb's C API
which has no variadic functions.

## `const` qualifier is lost

C `const` qualifiers are not reflected in generated Go bindings.

## Resource lifetime is manual

`duckdb_create_*` / `duckdb_destroy_*` pairs cannot be enforced at compile time.
Users must pair them correctly to avoid leaks or use-after-free.

## Large struct by-value passing

purego supports by-value struct passing, but architecture-specific ABI edge cases may
exist. Verified working on darwin/amd64 and darwin/arm64 for `duckdb_result` (48 bytes),
`duckdb_hugeint` (16 bytes), `duckdb_decimal` (24 bytes), etc.
