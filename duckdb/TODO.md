# DUCKDB TODO

Issues discovered while building the DuckDB database/sql driver.
Items that are purego-gen core improvements are tracked in root [`TODO.md`](../TODO.md).

## DuckDB-Specific Notes

- **`duckdb_result` by-value passing**: `duckdb_result_return_type` and `duckdb_fetch_chunk` take the 48-byte struct by value. purego-gen generates this correctly; purego handles large struct ABI.
- **`duckdb_from_date`/`duckdb_from_time`/`duckdb_from_timestamp`**: Small struct by-value params and returns. Generated correctly.
- **`DuckDBSuccess`/`DuckDBError`**: CamelCase C enum values preserved as-is in generated constants. Appropriate.

## purego-gen Improvements That Would Benefit duckdb

### `duckdb_string_t` union type

purego-gen renders unions as opaque byte arrays. The 16-byte inline/pointer string union
(`duckdb_string_t`) requires hand-written `ReadStringFromVector`/`ReadBlobFromVector`.
Union support improvements would allow generating these helpers.

### `duckdb_string_t` by-value arguments

Functions like `duckdb_string_is_inlined` and `duckdb_string_t_length` take
`duckdb_string_t` by value. Since the union type is not supported, these functions
cannot be generated.

### `owned_string_returns` wildcard patterns

Many `duckdb_get_*` functions return `char*` that must be freed with `duckdb_free`.
Currently each must be listed individually. A wildcard/regex pattern (e.g. `duckdb_get_varchar`,
`duckdb_enum_dictionary_value`, `duckdb_struct_type_child_name`, `duckdb_union_type_member_name`,
`duckdb_logical_type_get_alias`, `duckdb_value_to_string`, `duckdb_table_description_get_column_name`)
would reduce config verbosity.

### `buffer_inputs` pattern

Functions like `duckdb_append_blob(appender, const void*, idx_t)` take a
`(pointer, length)` pair. A `buffer_inputs` config pattern would generate safe Go
`[]byte` wrappers automatically, reducing per-function manual config.

### Callback typedef resolution

duckdb defines ~29 callback typedefs (`duckdb_scalar_function_t`, `duckdb_table_function_bind_t`,
etc.). Each requires `callback_inputs` config. Improved callback autodiscovery could reduce
boilerplate.

### Array pointer parameters

Functions like `duckdb_create_struct_value(logical_type, duckdb_value*)` and
`duckdb_create_data_chunk(duckdb_logical_type*, idx_t)` take pointer-to-array parameters.
These become `uintptr` and require hand-written helpers to pass Go slices safely.
