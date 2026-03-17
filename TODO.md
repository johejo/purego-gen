# TODO

Active tasks and unresolved decisions only.
Completed work is intentionally omitted.

## Target Library Coverage

- [ ] Add `libduckdb` harness fixture and golden outputs (must).
- [ ] Add `onnxruntime` harness fixture and golden outputs.
- [ ] Add optional Linux-only `libsystemd` harness fixture.
- [ ] Wire target-library jobs into the CI matrix with platform guards.
- [ ] Record known unsupported declarations per library.

## Future Capabilities

- [ ] Add support for in-memory overlays via `CXUnsavedFile` so parsing can work without relying on on-disk headers.
- [ ] Add string mapping for `const unsigned char *` results/parameters so APIs like `sqlite3_column_text()` do not fall back to `uintptr`.
- [ ] Add a first-class strategy for callback/destructor function pointers in generated bindings so APIs like `sqlite3_exec()` and `sqlite3_bind_text()` are practical to use.

## Open Decisions

- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Decide whether enum mapping should stay on `int32` or use libclang-derived underlying size/signedness for ABI-accurate fixed-width Go types.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
