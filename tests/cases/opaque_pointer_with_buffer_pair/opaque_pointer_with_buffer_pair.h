#include <stddef.h>

typedef struct fixture_ctx fixture_ctx;

size_t fixture_consume(fixture_ctx* ctx, const void* src, size_t src_size);
