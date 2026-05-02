/*
 * Fixture for inline function-pointer passthrough through a buffer-helper
 * wrapper, resolved against a typedef alias.
 *
 * `fixture_destructor` is a typedef for `void (*)(void *)` and is in
 * `include.type`. `fixture_bind` declares the destructor as an inline
 * function pointer (matching the typedef's signature), and the function has
 * a `buffer_params` helper for `data`/`n` that produces a `_bytes` wrapper.
 * Python resolves the inline pointer to the typedef alias and renders
 * `destroy fixture_destructor` in both the FFI var block and the wrapper;
 * the Zig generator currently inlines it (`destroy func(uintptr)` in the
 * wrapper, `destroy uintptr` with a `// C: ...` comment in the var block).
 */
typedef void (*fixture_destructor)(void* p);

int fixture_bind(int idx, const void* data, int n, void (*destroy)(void*));
