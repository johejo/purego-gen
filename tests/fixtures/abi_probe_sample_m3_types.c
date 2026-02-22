#include <stddef.h>
#include <stdio.h>

#include "sample_m3_types.h"

#define PRINT_RECORD_LAYOUT(type_name) \
  printf("record,%s,%zu,%zu\n", #type_name, sizeof(type_name), _Alignof(type_name))

#define PRINT_FIELD_LAYOUT(type_name, field_name)                                   \
  printf("field,%s,%s,%zu,%zu,%zu\n", #type_name, #field_name,                     \
         offsetof(type_name, field_name) * 8,                                       \
         sizeof(__typeof__(((type_name *)0)->field_name)),                          \
         _Alignof(__typeof__(((type_name *)0)->field_name)))

int main(void) {
  PRINT_RECORD_LAYOUT(sample_point_t);
  PRINT_FIELD_LAYOUT(sample_point_t, left);
  PRINT_FIELD_LAYOUT(sample_point_t, right);
  PRINT_FIELD_LAYOUT(sample_point_t, mode);
  PRINT_FIELD_LAYOUT(sample_point_t, label);

  PRINT_RECORD_LAYOUT(sample_point_alias_t);
  PRINT_FIELD_LAYOUT(sample_point_alias_t, left);
  PRINT_FIELD_LAYOUT(sample_point_alias_t, right);
  PRINT_FIELD_LAYOUT(sample_point_alias_t, mode);
  PRINT_FIELD_LAYOUT(sample_point_alias_t, label);

  PRINT_RECORD_LAYOUT(sample_nested_point_t);
  PRINT_FIELD_LAYOUT(sample_nested_point_t, point);
  PRINT_FIELD_LAYOUT(sample_nested_point_t, inner);

  return 0;
}
