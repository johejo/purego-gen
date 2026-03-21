# TODO

Active tasks and unresolved decisions only.
Completed work is intentionally omitted.

## Target Library Coverage

- [ ] Add `onnxruntime` harness fixture and golden outputs.
- [ ] Add optional Linux-only `libsystemd` harness fixture.
- [ ] Wire target-library jobs into the CI matrix with platform guards.

## UX Improvements

- [ ] Add a broad declaration-collection mode so users can start from "generate everything supported" and then narrow with excludes instead of large allowlists.
- [ ] Add opt-in mapping policies for common C API patterns such as nullable `const char *`, blob-like `const void *`, and similar pointer/value conventions that currently force handwritten call-site boilerplate.
- [ ] Improve generic callback/destructor ergonomics so common function-pointer registration patterns require less handwritten marshalling around generated bindings.
- [ ] Strengthen type classification and conversion heuristics for helper generation so buffer/string-like patterns can be recognized from typedef-heavy signatures before any partial auto-generation mode (callback typedef resolution done; buffer/string patterns remain).
- [ ] Explore an optional helper-layer generation mode that builds small ergonomic wrappers on top of the low-level purego bindings without baking target-library-specific policy into the core generator.

## Open Decisions

- [ ] Decide macro evaluation boundary beyond enum-like constants.
- [ ] Re-evaluate Windows support scope after v1 (API and symbol-loading strategy).
