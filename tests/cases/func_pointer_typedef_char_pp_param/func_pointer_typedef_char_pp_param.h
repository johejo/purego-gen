typedef int (*fixture_callback)(void* user, int n, char** values, char** names);

int fixture_run(fixture_callback cb, void* user);
