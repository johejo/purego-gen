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

## UX Improvements

- [ ] Add a broad declaration-collection mode so users can start from "generate everything supported" and then narrow with excludes instead of large allowlists.
- [ ] Add opt-in mapping policies for common C API patterns such as nullable `const char *`, blob-like `const void *`, and similar pointer/value conventions that currently force handwritten call-site boilerplate.
- [ ] Improve generic callback/destructor ergonomics so common function-pointer registration patterns require less handwritten marshalling around generated bindings.
- [ ] Add callback-helper candidate inventory and a staged path toward partial auto-generation so function-pointer-heavy libraries can opt into safe patterns without hand-enumerating every helper target.
- [ ] Strengthen type classification and conversion heuristics for helper generation so callback/buffer/string-like patterns can be recognized from typedef-heavy signatures before any partial auto-generation mode.
- [ ] Emit a clearer supported/skipped declaration inventory so users can quickly see what still requires handwritten code after generation.
- [ ] Explore an optional helper-layer generation mode that builds small ergonomic wrappers on top of the low-level purego bindings without baking target-library-specific policy into the core generator.
- [ ] Revisit config schema/model/normalize/load boundaries so config additions stop requiring repeated cross-file edits.
- [ ] Revisit whether `target_profile` and normal config loading should share type-mapping and validation helpers.

## Open Decisions

- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Decide whether enum mapping should stay on `int32` or use libclang-derived underlying size/signedness for ABI-accurate fixed-width Go types.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
