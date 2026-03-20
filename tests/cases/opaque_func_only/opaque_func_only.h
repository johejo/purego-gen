/*
 * Fixture for opaque struct referenced in function signatures
 * when only func emit is enabled (no type emit).
 */
typedef struct foo foo_t;

foo_t *create_ctx(const foo_t *ctx);
