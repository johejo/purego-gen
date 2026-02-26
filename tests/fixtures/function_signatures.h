/*
 * Fixture declarations for function-signature type mapping behavior.
 * Identifier spellings are part of stable test assertions.
 */
const char* fixture_const_name(void);

const char* fixture_lookup_name(const char* key);

char* fixture_mutable_name(void);

int fixture_fill_name(char* dst, const char* src);

void* fixture_user_data(void* ctx, const void* src);
