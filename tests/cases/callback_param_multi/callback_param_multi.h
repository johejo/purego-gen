typedef int (*fixture_invoke_fn)(int);
typedef void (*fixture_step_fn)(int);
typedef void (*fixture_final_fn)(void);

int fixture_register(fixture_invoke_fn xFunc, fixture_step_fn xStep, fixture_final_fn xFinal);
