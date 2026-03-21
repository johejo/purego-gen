/*
 * Fixture for callback parameter name conflict across functions.
 * Both functions use "handler" but with different signatures.
 */
void fixture_fn_a(int (*handler)(void*));
void fixture_fn_b(void (*handler)(void*, int));
