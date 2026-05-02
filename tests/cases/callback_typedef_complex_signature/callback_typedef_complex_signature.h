/*
 * Fixture for inline function-pointer parameter resolved to a typedef alias.
 *
 * `fixture_cb_t` is a typedef for `int (*)(void *, int, char **)` and is in
 * `include.type`. The function `fixture_register` takes an inline function
 * pointer with the same signature. Python recognizes the matching signature
 * and renders the parameter as the typedef alias (`callback fixture_cb_t,`);
 * the Zig generator currently renders it as `callback uintptr` with a
 * `// C: ...` comment.
 */
typedef int (*fixture_cb_t)(void *, int, char **);

int fixture_register(int (*callback)(void *, int, char **));
