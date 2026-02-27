# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Quickstart

```sh
purego-gen --lib-id zstd --header zstd.h --out -
```

## Key Constraints

- Non-Windows first; generator targets low-level `func/type/const/var` bindings.
- Generated identifiers are unexported `purego_` names with category prefixes
  (`func_/type_/const_/var_`) and C-side casing preserved in suffixes.
- Typed function signatures use emitted opaque-handle aliases (`purego_type_*`)
  when corresponding opaque typedefs are emitted.
- Function signatures keep pointer-like C types low-level by default; optional
  `--const-char-as-string` maps only `const char*` slots to Go `string`.
- Optional `--strict-opaque-handles` emits opaque struct-handle typedefs as
  strict Go types (`type T uintptr`) when `--emit` includes `type`.
- Optional `--strict-enum-typedefs` emits enum typedef aliases as strict Go
  types (`type T int32`) when `--emit` includes `type`.
- Optional `--typed-sentinel-constants` emits large sentinel-style constants
  as typed `uint64` constants.
- Declaration comments from C headers are copied to generated Go declarations
  as `//` comments when libclang provides declaration-attached comments.
- Plain `//` / `/* */` comments are copied only when clang is invoked with
  `-fparse-all-comments` (pass it through after `--`).
- Callers provide and own the library handle (`dlopen` policy is out of scope).

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

See also:
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md) (implementation contract and technical details)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md) (execution plan and milestones)
- [`Justfile`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/Justfile) (automation entrypoints)

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
