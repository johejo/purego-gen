# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Status

Early development. Interfaces and generated output may change.
- Single-command CLI (`purego-gen`) that parses C headers via libclang.
- Generates low-level bindings for `func/type/const/var`.
- Identifier scheme uses unexported `purego_` names with category prefixes
  (`func_/type_/const_/var_`) and C-side casing preserved in suffixes.
- Callers provide the library handle (no automatic `dlopen` policy).
- Runtime harness currently targets `libzstd` as the baseline objective library.

Detailed behavior and contract-level rules live in
[`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md).

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
