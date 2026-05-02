typedef struct fixture_ctx fixture_ctx;
typedef struct fixture_val fixture_val;

typedef void (*fixture_process_fn)(fixture_ctx* ctx, int n, fixture_val** values);

int fixture_process(fixture_process_fn fn);
