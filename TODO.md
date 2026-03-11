# TODO

Active tasks and unresolved decisions only.
Completed work is intentionally omitted.

## Target Library Coverage

- [ ] Add `libduckdb` harness fixture and golden outputs (must).
- [ ] Add `onnxruntime` harness fixture and golden outputs.
- [ ] Add optional Linux-only `libsystemd` harness fixture.
- [ ] Wire target-library jobs into the CI matrix with platform guards.
- [ ] Record known unsupported declarations per library.

## Stage1 Go Bootstrap

- [ ] Define the stage1 Go package split and add a stage1 CLI entrypoint plus dual-run parity harness so stage0-vs-stage1 output can be compared on selected golden cases.
- [ ] Add stage1 support for in-memory overlays via `CXUnsavedFile` when header parsing can no longer rely on on-disk files.
- [ ] Replace the current raw `clang_visitChildren` binding with a typed Go wrapper once purego can safely bridge libclang's by-value `CXCursor` callback ABI.
- [ ] Decide whether generic callback/trampoline codegen is worth adding to stage0, or whether libclang-specific handwritten bridges should remain the default.
- [ ] Add tokenization and macro-classification bindings (`CXToken`, `clang_tokenize`, `clang_disposeTokens`, token spelling, macro predicates) needed for stage0 feature parity.
- [ ] Port macro expression evaluation, declaration normalization/filtering, and ABI record metadata/layout validation from Python to Go, and validate them against the existing golden and ABI cases.
- [ ] Promote stage1 to the default generator only after golden/runtime parity across the existing case suite, keeping stage0 available as the bootstrap fallback until cutover is stable.

## Open Decisions

- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Decide whether enum mapping should stay on `int32` or use libclang-derived underlying size/signedness for ABI-accurate fixed-width Go types.
- [ ] Define trigger criteria for introducing `--config <file>`.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
