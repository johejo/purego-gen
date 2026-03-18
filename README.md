# purego-gen

A code generator for [ebitengine/purego](https://github.com/ebitengine/purego).

## Motivation

When using purego, you often need to write a lot of boilerplate code to call C functions. This tool generates that boilerplate code for you, making it easier to use purego.

## Getting Started

```sh
nix run github:johejo/purego-gen -- --config /path/to/config.json --out /path/to/generated.go
```

Config filters can now work in two directions:

- `generator.parse.filters`: include only matching declarations
- `generator.parse.exclude`: start broad and drop matching declarations afterward

Example:

```json
{
  "schema_version": 1,
  "generator": {
    "lib_id": "example",
    "package": "example",
    "emit": "func,const",
    "parse": {
      "headers": {
        "kind": "local",
        "headers": ["example.h"]
      },
      "filters": {},
      "exclude": {
        "func": "^internal_",
        "const": ["EXAMPLE_INTERNAL_SENTINEL"]
      }
    },
    "render": {
      "naming": {
        "identifier_prefix": "purego_"
      }
    }
  }
}
```

`generator.render.naming.identifier_prefix` controls the leading generated Go identifier prefix and defaults to `purego_`.

## License

Apache License 2.0 (`Apache-2.0`). See [`LICENSE`](./LICENSE).
