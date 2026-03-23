# DUCKDB TODO

Issues discovered while building the DuckDB database/sql driver.
Items that are purego-gen core improvements are tracked in root [`TODO.md`](../TODO.md).

## DuckDB-Specific Notes

- **`duckdb_result` by-value passing**: `duckdb_result_return_type` and `duckdb_fetch_chunk` take the 48-byte struct by value. purego-gen generates this correctly; purego handles large struct ABI.
- **`duckdb_from_date`/`duckdb_from_time`/`duckdb_from_timestamp`**: Small struct by-value params and returns. Generated correctly.
- **`DuckDBSuccess`/`DuckDBError`**: CamelCase C enum values preserved as-is in generated constants. Appropriate.

## purego-gen Improvements That Would Benefit duckdb

### `duckdb_string_t` union type (partially resolved)

`duckdb_string_t` is now generated as an opaque 16-byte union typedef, and
`duckdb_string_is_inlined` / `duckdb_string_t_length` are generated with by-value
arguments. Hand-written `ReadStringFromVector`/`ReadBlobFromVector` helpers remain
needed for reading strings from vectors (different responsibility).

### ~~`owned_string_returns` wildcard patterns~~ (resolved)

`function_pattern` field now supports regex patterns in `owned_string_returns` config.
DuckDB config uses `"function_pattern": "^duckdb_"` to match all string-returning functions.

### `buffer_inputs` pattern

Functions like `duckdb_append_blob(appender, const void*, idx_t)` take a
`(pointer, length)` pair. A `buffer_inputs` config pattern would generate safe Go
`[]byte` wrappers automatically, reducing per-function manual config.

### Callback typedef resolution (partially resolved)

`auto_callback_inputs: true` is implemented. DuckDB callbacks use a struct-wrapped pattern
(callbacks are set via setter functions), so enabling auto-discovery requires adding the
setter functions (`duckdb_scalar_function_set_function`, etc.) to the func filter first.
`inspect --emit-callback-config` can list candidates as JSON.

### Array pointer parameters

Functions like `duckdb_create_struct_value(logical_type, duckdb_value*)` and
`duckdb_create_data_chunk(duckdb_logical_type*, idx_t)` take pointer-to-array parameters.
These become `uintptr` and require hand-written helpers to pass Go slices safely.
