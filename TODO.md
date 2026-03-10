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

- [ ] Check in a stage0-generated `libclang` Go binding package as the bootstrap substrate for stage1.
- [ ] Define the stage1 Go package split and add a stage1 CLI entrypoint plus dual-run parity harness so stage0-vs-stage1 output can be compared on selected golden cases.
- [ ] Add generator/runtime support for libclang APIs that pass or return structs by value (`CXCursor`, `CXType`, `CXString`, `CXSourceLocation`, `CXUnsavedFile`, `CXToken`).
- [ ] Add callback/trampoline support needed to drive `clang_visitChildren` from stage1 without handwritten shims.
- [ ] Add `CXString` lifetime helpers and tests so stage1 can read cursor, type, and comment text safely.
- [ ] Add binding coverage for translation-unit traversal, type introspection, and tokenization/macro-classification APIs needed for stage0 feature parity.
- [ ] Port macro expression evaluation, declaration normalization/filtering, and ABI record metadata/layout validation from Python to Go, and validate them against the existing golden and ABI cases.
- [ ] Promote stage1 to the default generator only after golden/runtime parity across the existing case suite, keeping stage0 available as the bootstrap fallback until cutover is stable.

## Open Decisions

- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Decide whether enum mapping should stay on `int32` or use libclang-derived underlying size/signedness for ABI-accurate fixed-width Go types.
- [ ] Define trigger criteria for introducing `--config <file>`.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
