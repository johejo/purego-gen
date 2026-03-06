# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Quickstart

```sh
purego-gen --lib-id zstd --header zstd.h --out -
```

Run the CLI directly from the flake:

```sh
nix run . -- --help
nix run . -- --lib-id fixture_lib --header tests/fixtures/basic.h --pkg fixture --out -
```

## Key Constraints

- Non-Windows first; generator targets low-level `func/type/const/var` bindings.
- Generated identifiers are unexported `purego_` names with category prefixes
  (`func_/type_/const_/var_`) and C-side casing preserved in suffixes.
- Typed function signatures use emitted opaque-handle aliases (`purego_type_*`)
  when corresponding opaque typedefs are emitted.
- Function signatures keep pointer-like C types low-level by default; optional
  `--const-char-as-string` maps only `const char*` slots to Go `string`.
- Incomplete struct typedefs are treated as opaque handles; when `--emit`
  includes `type`, opaque handles are emitted as strict Go types
  (`type T uintptr`) by default.
- Optional `--strict-enum-typedefs` emits enum typedef aliases as strict Go
  types (`type T int32`) when `--emit` includes `type`.
- Optional `--typed-sentinel-constants` emits large sentinel-style constants
  as typed `uint64` constants.
- Stable diagnostic code values now use the `PUREGO_GEN_` prefix; this is a
  breaking code-value change from the earlier `PG_` prefix.
- CLI stderr includes stable opaque-summary diagnostics:
  `PUREGO_GEN_OPAQUE_EMITTED_COUNT` and
  `PUREGO_GEN_OPAQUE_FALLBACK_UINTPTR_COUNT`.
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

Golden/runtime regression tests are case-driven under
[`tests/cases`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/tests/cases):
- each case directory defines `profile.json` and expected `generated.go`
- optional `runtime_test.go` enables runtime `go test`; otherwise compile-only `go test -run '^$'` is used
- `just golden-update` regenerates all case `generated.go`
- `just golden-check` runs generation drift checks and Go compile/runtime validation

The default dev shell respects existing user/environment cache settings.
Codex-specific sandbox workflow is documented in
[`AGENTS.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/AGENTS.md).

See also:
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md) (implementation contract and technical details)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md) (execution plan and milestones)
- [`Justfile`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/Justfile) (automation entrypoints)

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
