/*
 * Fixture for inline function pointer parameter resolution to Go func types.
 *
 * These function pointers are NOT backed by a typedef and have no callback
 * helper configured, so they should resolve directly to Go ``func(...)`` types.
 */
void fixture_set_handler(void (*on_ready)(int, const char*), void* user_data);
int fixture_transform(int (*fn)(int), int value);
