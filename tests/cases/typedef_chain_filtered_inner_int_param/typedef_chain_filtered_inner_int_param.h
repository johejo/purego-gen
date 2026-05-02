/*
 * Fixture for chained integer typedef alias resolution where the inner typedef
 * is filtered out of `include.type` (only the outer typedef is emitted).
 *
 * `fixture_int_outer` is a typedef of `fixture_int_inner`, which is itself a
 * typedef of `long long`. Only `fixture_int_outer` is listed in `include.type`,
 * so `fixture_int_inner` is filtered. Python still resolves the chain through
 * the filtered intermediate typedef and emits `int64` in func signatures; the
 * Zig generator currently stops at the outer typedef name and emits
 * `fixture_int_outer`. Mirrors the libsqlite3 `sqlite3_int64` -> `sqlite_int64`
 * -> `long long` shape.
 */
typedef long long fixture_int_inner;
typedef fixture_int_inner fixture_int_outer;

fixture_int_outer fixture_get(fixture_int_outer value);
