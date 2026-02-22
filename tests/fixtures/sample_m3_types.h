typedef enum sample_mode {
  SAMPLE_MODE_OFF = 0,
  SAMPLE_MODE_ON = 1,
} sample_mode_t;

typedef sample_mode_t sample_mode_alias_t;
typedef int (*sample_callback_t)(int value);
typedef const char* sample_name_t;
typedef void* sample_context_t;
typedef struct sample_point {
  int left;
  int right;
  sample_mode_t mode;
  const char* label;
} sample_point_t;
typedef sample_point_t sample_point_alias_t;
typedef struct sample_nested_point {
  sample_point_t point;
  struct {
    int level;
  } inner;
} sample_nested_point_t;
typedef struct sample_with_array {
  int values[4];
} sample_with_array_t;
typedef union sample_union {
  int as_int;
  float as_float;
} sample_union_t;
typedef struct sample_with_bitfield {
  unsigned int flags : 3;
} sample_with_bitfield_t;
typedef struct sample_with_anonymous_field {
  struct {
    int value;
  };
} sample_with_anonymous_field_t;
typedef struct sample_opaque sample_opaque_t;

struct sample_nested {
  struct {
    int value;
  } inner;
};
