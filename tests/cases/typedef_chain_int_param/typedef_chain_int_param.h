/*
 * Fixture for chained integer typedef alias resolution.
 *
 * `fixture_int_outer` is a typedef of `fixture_int_inner`, which is itself a
 * typedef of `long long`. Python resolves the chain and emits `int64` in func
 * signatures; the Zig generator currently stops at the first typedef name and
 * emits `fixture_int_outer`.
 */
typedef long long fixture_int_inner;
typedef fixture_int_inner fixture_int_outer;

fixture_int_outer fixture_get(fixture_int_outer value);
