# purego Limitations

Known limitations and constraints of [purego](https://github.com/ebitengine/purego) that affect code generation.

## Variadic Functions

purego does not support calling C variadic functions. The following sqlite3 functions cannot be bound:

- `sqlite3_config(int, ...)` — global configuration
- `sqlite3_db_config(sqlite3*, int, ...)` — per-connection configuration
- `sqlite3_mprintf(const char*, ...)` — formatted string allocation
- `sqlite3_snprintf(int, char*, const char*, ...)` — formatted string with buffer
- `sqlite3_log(int, const char*, ...)` — error logging
- `sqlite3_str_appendf(sqlite3_str*, const char*, ...)` — string builder append
- `sqlite3_test_control(int, ...)` — testing interface
- `sqlite3_vtab_config(sqlite3*, int, ...)` — virtual table configuration

## Function Pointer Type Mismatches

`sqlite3_auto_extension` and `sqlite3_cancel_auto_extension` accept `void(*)(void)` but SQLite actually calls the function with the signature `int(*)(sqlite3*, char**, const sqlite3_api_routines*)`. purego callbacks are strongly typed, so the mismatch would cause a crash at runtime.

## Owned String Returns

C functions that return `char *` (non-const) where the caller must free the memory (e.g., `sqlite3_expanded_sql`) cannot use purego's automatic string conversion. The raw C pointer must be captured, the string copied to Go, and the C memory freed explicitly. These require manual registration with `uintptr` return type.
