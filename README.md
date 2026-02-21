# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Status

Early development. Interfaces and generated output may change.

## Current Direction (v1)

- Target: generate low-level bindings from C headers for `purego`.
- Scope: non-Windows first.
- Generated identifiers are unexported and prefixed with `purego_`.
- Generated code expects a library handle from the caller (no automatic `dlopen` policy).

## CLI (current)

Single-command interface:

```sh
purego-gen --lib-id zstd --header zstd.h --out -
```

For detailed and up-to-date behavior, see:
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md)
