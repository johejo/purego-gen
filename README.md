# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Getting Started

```sh
nix run github:johejo/purego-gen -- --help
nix run github:johejo/purego-gen -- --lib-id my_lib --header /path/to/header.h --output /path/to/generated.go --emit func,type,const,var
```

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](/Users/mitsuoheijo/repos/github.com/johejo/purego-gen/LICENSE).
