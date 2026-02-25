# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Status

Early development. Interfaces and generated output may change.
- Single-command CLI (`purego-gen`) that parses C headers via libclang.
- Generates low-level bindings for `func/type/const/var` categories.
- Non-Windows first; generated identifiers are unexported `purego_` names.
- Callers provide the library handle (no automatic `dlopen` policy).
- M4 ABI checks now include C-side probe comparison (`sizeof`/`alignof`/`offsetof`)
  and explicit `passed`/`failed`/`skipped` fallback classification per record.
- v1 function-pointer handling is `uintptr`-only (no callback trampoline codegen).
- v1 optional symbol policy is hard-error for emitted symbols.
- Golden-case manifest is normalized to `header_paths`, and CI can enforce
  strict golden drift checks via `just golden-check-ci`.
- M5 `libzstd` objective harness fixture now checks deterministic golden output
  and runtime symbol resolution for a stable API subset.

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

The dev shell respects existing user/environment cache settings. In Codex
sandbox sessions, `just agent-check` / `just agent-ci` use repo-local `.cache/`
defaults for repeatable runs.

For detailed and up-to-date behavior, see:
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md) (implementation contract and technical details)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md) (execution plan and milestones)
- [`Justfile`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/Justfile) (automation entrypoints)

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
