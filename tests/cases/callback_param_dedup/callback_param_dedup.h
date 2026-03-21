/*
 * Fixture for callback parameter deduplication.
 * Both functions use "on_done" with the same signature.
 */
void fixture_fn_a(void (*on_done)(int));
void fixture_fn_b(void (*on_done)(int));
