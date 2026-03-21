/* align=4: int/float members */
typedef union my_union {
  int as_int;
  float as_float;
} my_union_t;

/* align=8: double member forces 8-byte alignment */
typedef union my_wide_union {
  int as_int;
  double as_double;
} my_wide_union_t;

/* align=1: char-only union, no alignment wrapper needed */
typedef union my_byte_union {
  char a;
  char b;
} my_byte_union_t;

typedef struct with_union_field {
  int tag;
  my_union_t value;
} with_union_field_t;

void use_union(my_union_t u);
