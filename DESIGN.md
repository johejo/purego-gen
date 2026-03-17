# Design Notes

## Purpose

`purego-gen` is a practical generator that turns C headers into low-level Go
bindings for [ebitengine/purego](https://github.com/ebitengine/purego).

This document is a compact record of current design decisions, not a complete
or frozen specification. It explains what the generator is trying to optimize
for and where its boundaries are.

This document does not cover day-to-day workflow. See [AGENTS.md](./AGENTS.md).
It does not replace the project overview in [README.md](./README.md), and it
does not track open work or unresolved decisions from [TODO.md](./TODO.md).

## Boundaries

In scope:
- parse headers with libclang
- normalize declarations into an internal model
- generate deterministic Go bindings for `purego`
- keep output suitable for golden-style testing
- support non-Windows targets first

Out of scope:
- perfect support for all C constructs
- full preprocessor emulation beyond clang
- automatic target-library discovery or policy
- ergonomic public Go APIs layered on top of generated bindings

The generator is intended to produce a reliable low-level layer. Public wrappers
and package ergonomics belong to downstream code.

## Core Design Decisions

- Use libclang as the parsing boundary rather than implementing a separate C
  frontend.
- Keep the pipeline simple: parse, normalize, filter, and render deterministic
  output.
- Generate bindings that fit `purego`'s model instead of inventing a parallel
  runtime abstraction.
- Leave ABI-specific calling, symbol invocation, and callback machinery to
  `purego`; keep header interpretation, declaration modeling, validation, and
  code emission in `purego-gen`.
- Prefer explicit configuration over implicit discovery so target-library
  coverage stays understandable and testable.
- Favor predictable generated output and golden-testability over aggressive
  convenience features.
- Keep the project incremental and practical. Pre-v1 details can change when
  implementation experience shows a better boundary.

## Stability And Sources Of Truth

`DESIGN.md` is intentionally brief. It does not try to enumerate every type
mapping rule, emitted naming detail, CLI edge case, diagnostic code, or testing
policy.

Those details live primarily in the implementation, golden cases, and tests.
When this document and the code disagree on a pre-v1 detail, treat the code and
tests as the more precise source of truth and update this note if a higher-level
design decision has changed.
