/*
 * Fixture declarations for object-like macro constant extraction.
 * Identifier spellings are part of stable test assertions.
 */
enum fixture_macro_seed {
  FIXTURE_MACRO_SEED = 7,
};

#define FIXTURE_VERSION_MAJOR 1
#define FIXTURE_VERSION_MINOR 2U
#define FIXTURE_VERSION_PATCH 3UL
#define FIXTURE_VERSION_NUMBER ((FIXTURE_VERSION_MAJOR * 10000) + (FIXTURE_VERSION_MINOR * 100) + FIXTURE_VERSION_PATCH)
#define FIXTURE_MAGIC_NUMBER 0xFD2FB528U
#define FIXTURE_CONTENTSIZE_UNKNOWN (0ULL - 1)
#define FIXTURE_CONTENTSIZE_ERROR (0ULL - 2)
#define FIXTURE_MACRO_FN(x) ((x) + 1)
