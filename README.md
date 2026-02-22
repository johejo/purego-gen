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

## CLI (current)

Single-command interface:

```sh
purego-gen --lib-id zstd --header zstd.h --out -
```

## Development Setup

Use the Nix dev shell as the default entrypoint and run the standard gate:

```sh
nix develop
just bootstrap
just gate
```

The dev shell defaults caches to repo-local `.cache/` and enables `ccache` so repeated runs stay fast across sandbox sessions.

For detailed and up-to-date behavior, see:
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md) (implementation contract and technical details)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md) (execution plan and milestones)
- [`Justfile`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/Justfile) (automation entrypoints)

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
