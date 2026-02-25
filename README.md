# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Status

Early development. Interfaces and generated output may change.
- Single-command CLI (`purego-gen`) that parses C headers via libclang.
- Generates low-level bindings for `func/type/const/var` categories.
- Function bindings are emitted as typed Go function values derived from parsed C
  signatures (with `uintptr` fallback for unsupported types).
- Incomplete/opaque struct typedefs are emitted as `uintptr` aliases for
  pointer-handle style APIs.
- Compile-time constant extraction includes enum members plus supported
  object-like integer macros.
- Non-Windows first; generated identifiers are unexported `purego_` names.
- Callers provide the library handle (no automatic `dlopen` policy).
- M4 ABI checks now include C-side probe comparison (`sizeof`/`alignof`/`offsetof`)
  and explicit `passed`/`failed`/`skipped` fallback classification per record.
- v1 function-pointer handling is `uintptr`-only (no callback trampoline codegen).
- Symbols are required by default, with optional symbol handling configurable
  via `--optional-func-filter` / `--optional-var-filter`.
- Golden-case manifest is normalized to `header_paths`, and CI can enforce
  strict golden drift checks via `just golden-check-ci`.
- M5 `libzstd` objective harness fixture checks deterministic golden output and
  runtime block compress/decompress roundtrip for a stable API subset.

## CLI (current)

Single-command interface:

```sh
purego-gen --lib-id zstd --header zstd.h --out -
```

## Development Setup

Use the Nix dev shell as the default entrypoint and run local checks first:

```sh
nix develop
just format
just check
```

Run strict CI-equivalent checks before pushing (including `djlint` version parity checks):

```sh
just ci
```

The default dev shell respects existing user/environment cache settings.
Codex-specific sandbox workflow is documented in
[`AGENTS.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/AGENTS.md).

For detailed and up-to-date behavior, see:
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md) (implementation contract and technical details)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md) (execution plan and milestones)
- [`Justfile`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/Justfile) (automation entrypoints)

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
