# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Status

Early development. Interfaces and generated output may change.
- Single-command CLI (`purego-gen`) parses C headers via libclang.
- Generation supports `func/type/const/var` categories and category filters.
- Runtime symbol binding uses panic-free `Dlsym + RegisterFunc` helpers.
- Emit layer uses Jinja2 templates; generated code is formatted with `gofmt`.
- M3 baseline type mapping includes enum typedefs (`int32`) and function-pointer
  typedefs (`uintptr`), and skips unsupported record typedefs (including opaque).
- Common struct typedef patterns with mappable fields are emitted as Go struct
  type literals.
- Skipped typedefs caused by unsupported record field kinds are reported as
  diagnostics on stderr.
- Skipped-type diagnostics now include stable machine-readable codes in both
  parser model metadata and CLI stderr output.
- Parser now also exposes structured record/field metadata internally as M4 ABI
  validation input.
- M4 now includes a layout validation utility that checks supported struct
  size/alignment/offset consistency against clang metadata with stable
  diagnostic codes.
- M4 now also includes a minimal C ABI probe fixture (`sizeof`/`alignof`/`offsetof`)
  that is compared against parser-extracted record metadata in tests.
- Tooling and checks are standardized around `nix`, `just`, `uv`, and `pytest`.

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

## Development Setup

Use the Nix dev shell as the default entrypoint and run the standard gate:

```sh
nix develop
just bootstrap
just gate
```

The dev shell defaults caches to repo-local `.cache/` and enables `ccache` so repeated runs stay fast across sandbox sessions.

For detailed and up-to-date behavior, see:
- [`Justfile`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/Justfile)
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md)

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
