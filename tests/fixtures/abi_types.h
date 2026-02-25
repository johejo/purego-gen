/*
 * Fixture declarations for ABI-model and unsupported-pattern diagnostics.
 * Identifier spellings are part of stable test assertions.
 */
typedef enum fixture_mode {
  FIXTURE_MODE_OFF = 0,
  FIXTURE_MODE_ON = 1,
} fixture_mode_t;

typedef fixture_mode_t fixture_mode_alias_t;
typedef int (*fixture_callback_t)(int value);
typedef const char* fixture_name_t;
typedef void* fixture_context_t;

typedef struct fixture_point {
  int left;
  int right;
  fixture_mode_t mode;
  const char* label;
} fixture_point_t;
typedef fixture_point_t fixture_point_alias_t;

typedef struct fixture_nested_point {
  fixture_point_t point;
  struct {
    int level;
  } inner;
} fixture_nested_point_t;

typedef struct fixture_with_array {
  int values[4];
} fixture_with_array_t;

typedef union fixture_union {
  int as_int;
  float as_float;
} fixture_union_t;

typedef struct fixture_with_bitfield {
  unsigned int flags : 3;
} fixture_with_bitfield_t;

typedef struct fixture_with_anonymous_field {
  struct {
    int value;
  };
} fixture_with_anonymous_field_t;

typedef struct fixture_opaque fixture_opaque_t;

struct fixture_nested {
  struct {
    int value;
  } inner;
};
