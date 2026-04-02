# Zig Rewrite Library Selection Notes

## Goal

Before a full Zig rewrite, identify which parts of the current implementation are awkward with Zig `std` alone and decide where third-party libraries are justified.

This note is intentionally practical. It is not a commitment to keep every current Python feature as-is.

## Current dependency-heavy areas in the Python implementation

The current Python implementation depends on four external capabilities:

- `clang` Python bindings for libclang integration
- `pydantic` for config decoding and validation
- `jinja2` for Go code generation
- Python `re`-heavy logic for filters, helper discovery, and C type string parsing

The Zig prototype already shows that direct libclang C API usage is viable, but it only covers a narrow `inspect`-style slice.

## Recommendation Summary

### Keep on Zig std + direct C API

- libclang integration
- JSON decoding
- filesystem/path/env handling
- process execution (`gofmt`)
- diagnostics formatting
- deterministic string/code emission

### Add third-party dependency

- CLI parsing: `Hejsil/zig-clap`
- Template rendering, if template files remain: `batiati/mustache-zig`

### Avoid third-party if possible by simplifying design

- regex engine
- schema-validation framework
- AST/codegen framework

## Area-by-area assessment

### 1. libclang integration

Status: Zig `std` only is enough.

Why:

- The existing Zig prototype already uses `@cImport("clang-c/Index.h")`.
- The production boundary is the C libclang API, not a Python-only abstraction.
- Memory control and stable traversal are straightforward in Zig.

What is still hard:

- string lifetime handling from `CXString`
- stable declaration collection/modeling
- macro classification fallbacks
- richer diagnostics and unsupported-pattern reporting

None of that requires a third-party Zig package. The hard part is implementation effort, not missing ecosystem support.

Decision:

- Keep this layer dependency-light.
- Continue talking directly to libclang via C import.

### 2. Config loading and validation

Status: Zig `std` is enough if we accept manual validation.

Why:

- Config files are JSON, not YAML/TOML.
- Zig `std.json` is enough to parse the current config shape.
- The current `pydantic` value is mostly strict validation and nice error messages.

What becomes awkward with std only:

- discriminated unions like `headers.kind`
- precise path-aware validation errors
- reusable validators for helper config, naming, public API filters, etc.

Recommendation:

- Do not add a general schema library first.
- Parse with `std.json`, then validate into explicit internal structs.
- Build a small project-local validation layer with structured error accumulation.

Decision:

- No third-party library required here initially.

### 3. CLI argument parsing

Status: std-only is possible, but not a good use of time.

Current scope includes:

- subcommands (`gen`, `inspect`)
- repeated options (`--clang-arg`)
- defaults
- typed values
- help text

Recommended library:

- `Hejsil/zig-clap`

Why:

- mature and actively maintained enough for current Zig versions
- supports short/long flags, repeated values, help generation, and typed parsing
- removes boilerplate from a part that is not product differentiation

Decision:

- Adopt `zig-clap` early.

### 4. Templating and code generation

Status: this is the main place where Zig `std` alone gets painful.

Current Python code uses:

- Jinja2 template files
- a large normalized render context
- conditional blocks and repeated sections

Zig std can emit strings directly, but pain increases when:

- the template stays file-based
- output layout must stay easy to diff
- conditional emission rules keep growing

Recommended direction:

- Prefer replacing Jinja-style templating with structured Zig emitters over time.
- If you want a transitional step that preserves external template files, use `batiati/mustache-zig`.

Why not keep a full logic-rich template engine requirement:

- most generator complexity is already in context building, not in template language power
- Mustache is sufficient for repeated sections and conditionals when precomputed in Zig
- a logic-less template keeps generation deterministic and easier to reason about

Decision:

- Short term: `mustache-zig` is the best migration aid if template files stay.
- Long term: move toward direct Zig writers and reduce template-engine dependence.

### 5. Regex-heavy matching

Status: this is the most suspicious area for third-party selection.

Current usage:

- include/exclude filters
- public API include/exclude rules
- helper pattern matching
- C type string parsing helpers

Zig std does not provide a built-in regex engine comparable to Python `re`.

Candidate:

- `tiehuis/zig-regex`

Why I would not adopt it as a core dependency yet:

- the project still describes itself as work in progress
- missing pieces are explicitly listed upstream
- config matching in this project is not performance-critical enough to justify engine complexity

Better rewrite strategy:

- keep exact-name matching as first-class
- replace regex-configured APIs with simpler match forms where possible:
  - exact name
  - prefix/suffix
  - substring
  - small wildcard/glob syntax
- keep regex support only if real target-library coverage work proves it necessary

Decision:

- Do not take a regex dependency in the first rewrite phase.
- Treat regex as a deferred feature or compatibility layer.

### 6. Helper discovery heuristics

Status: std-only is enough, but some current heuristics should be redesigned.

The current code uses regex and C type string parsing for:

- callback candidate detection
- buffer parameter detection
- owned-string helper expansion

In Zig, the maintainable boundary is:

- normalize declarations once
- attach canonicalized type metadata
- run helper detection on normalized metadata, not raw string regexes where possible

Decision:

- No third-party dependency.
- Spend effort on better internal data modeling instead.

### 7. C type string parsing utilities

Status: std-only is enough.

The current Python code parses function pointer spellings and opaque-pointer typedef forms mostly with regexes. In Zig this should be moved away from generic regex and toward:

- token scanning
- delimiter-aware parsing
- more libclang-derived structure, less string re-parsing

Decision:

- No third-party parser library.

### 8. ABI/layout validation

Status: std-only is enough.

This is arithmetic, model validation, and reporting. No external library is justified.

## Proposed dependency set for phase 1

Keep phase 1 intentionally small:

- required: `Hejsil/zig-clap`
- optional transitional dependency: `batiati/mustache-zig`
- no regex library
- no schema-validation library

## Suggested rewrite order

1. Expand the Zig libclang layer until `inspect` parity is good enough.
2. Introduce `zig-clap` and move the CLI to the Zig binary cleanly.
3. Rebuild config parsing on `std.json` + manual validation.
4. Recreate the internal declaration model and diagnostics.
5. Choose one codegen path:
   - direct Zig writers, preferred
   - `mustache-zig` as a migration bridge
6. Reintroduce helper discovery with reduced regex dependence.
7. Re-evaluate whether regex support is still worth carrying.

## Final call

The rewrite does not look blocked by a lack of Zig ecosystem support overall.

The only areas where third-party libraries currently look justified are:

- CLI parsing
- optionally template rendering during migration

The area that looks tempting but should probably be resisted is regex. For this project, redesigning config and helper matching is likely better than importing a regex engine early.

## Sources

- Current repo implementation:
  - `src/purego_gen/*.py`
  - `src/purego_gen_zig/*.zig`
- `zig-clap`: <https://github.com/Hejsil/zig-clap>
- `mustache-zig`: <https://github.com/batiati/mustache-zig>
- `zig-regex`: <https://github.com/tiehuis/zig-regex>
