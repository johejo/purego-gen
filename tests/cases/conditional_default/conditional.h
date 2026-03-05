/*
 * Fixture declarations for conditional parsing with and without -D flags.
 * Identifier spellings are part of stable golden outputs.
 */
#ifdef FIXTURE_ENABLE_EXTRA
int extra_add(int lhs, int rhs);
extern int extra_counter;
#else
int base_add(int lhs, int rhs);
#endif
