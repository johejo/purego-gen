# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Status

Early development. Interfaces and generated output may change.
- CLI entrypoint parses function declarations and basic typedefs via libclang.
- Generated output is still minimal and intentionally low-level.
- Generated output is automatically formatted with `gofmt`.

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
- `just nix-fmt`: run `nix fmt`
- `just nix-flake-check`: run `nix flake check`
- `just fmt`: run `treefmt`
- `just fmt-check`: run `treefmt --fail-on-change`
- `just lint`: run `ruff` checks
- `just typecheck`: run `basedpyright` and `pyrefly`
- `just test`: run `pytest`
- `just gate`: run `nix-fmt` -> `nix-flake-check` -> `check` (recommended for Codex/CI)

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
