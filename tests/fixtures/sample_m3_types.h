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
typedef struct sample_opaque sample_opaque_t;

struct sample_nested {
  struct {
    int value;
  } inner;
};
