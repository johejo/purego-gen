# DUCKDB TODO

Issues discovered while building the DuckDB database/sql driver.
Items that are purego-gen core improvements are tracked in root [`TODO.md`](../TODO.md).

## purego-gen Gaps Found (tracked in root TODO.md)

- **Union typedef support**: `duckdb_string_t` skipped; manual vector string reading needed.

## DuckDB-Specific Notes

- **`duckdb_result` by-value passing**: `duckdb_result_return_type` and `duckdb_fetch_chunk` take the 48-byte struct by value. purego-gen generates this correctly; purego handles large struct ABI.
- **`duckdb_from_date`/`duckdb_from_time`/`duckdb_from_timestamp`**: Small struct by-value params and returns. Generated correctly.
- **`DuckDBSuccess`/`DuckDBError`**: CamelCase C enum values preserved as-is in generated constants. Appropriate.
