# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Status

Early development. Interfaces and generated output may change.
- CLI entrypoint parses function declarations and basic typedefs via libclang.
- Declaration model includes explicit `func/type/const/var` categories
  (`const`: enum constants, `var`: `extern` runtime data symbols).
- `--emit` supports selecting `func,type,const,var` categories, with `const`
  emitted as Go compile-time constants.
- Emit layer uses Jinja2 templates with strict undefined-variable failures.
- Generated output is still minimal and intentionally low-level.
- Generated output is automatically formatted with `gofmt`.
- Test fixture C headers (`tests/fixtures/*.h`) are formatted with `clang-format` via `treefmt`.

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

Use the Nix dev shell as the default entrypoint:

```sh
nix develop
```

Initialize local tooling and git hooks:

```sh
just bootstrap
```

Run all local quality gates:

```sh
just check
```

Main tasks:
- `just fmt`: run `nix fmt` (includes `.nix`, `.py`, `.go`, `scripts/*.sh`, and `tests/fixtures/*.h`)
- `just fmt-check`: run formatter checks (`nix fmt -- --fail-on-change`)
- `just golden-update`: regenerate `tests/golden/*.go`
- `just golden-check`: compare generated output against committed golden files at `HEAD`
- `just check`: run lint/typecheck/golden-check/test (`lint` includes `shellcheck` and `shfmt -d` for `scripts/*.sh`)
- `just gate`: run `fmt` -> `nix-flake-check` -> `check` (recommended for Codex/CI)

Git hook flow (`lefthook`):
- `pre-commit`: `just hook-gate` (`fmt-check` only)
- `pre-push`: `just hook-push-gate` (full `gate`)

Recommended usage:
- Codex/CI: run `just gate` directly.
- Local git operations: rely on `lefthook` for commit/push guardrails.

For detailed and up-to-date behavior, see:
- [`DESIGN.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/DESIGN.md)
- [`TODO.md`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/TODO.md)

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
