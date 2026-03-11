#include <stddef.h>
#include <stdio.h>

#include "abi_types.h"

#define EMIT_RECORD_LAYOUT(record_type)                                                            \
  printf("record,%s,%zu,%zu\n", #record_type, sizeof(record_type), _Alignof(record_type))

#define EMIT_FIELD_LAYOUT(record_type, member_name)                                                \
  printf("field,%s,%s,%zu,%zu,%zu\n", #record_type, #member_name,                                  \
         offsetof(record_type, member_name) * 8,                                                   \
         sizeof(__typeof__(((record_type*)0)->member_name)),                                       \
         _Alignof(__typeof__(((record_type*)0)->member_name)))

int main(void) {
  EMIT_RECORD_LAYOUT(fixture_point_t);
  EMIT_FIELD_LAYOUT(fixture_point_t, left);
  EMIT_FIELD_LAYOUT(fixture_point_t, right);
  EMIT_FIELD_LAYOUT(fixture_point_t, mode);
  EMIT_FIELD_LAYOUT(fixture_point_t, label);

  EMIT_RECORD_LAYOUT(fixture_point_alias_t);
  EMIT_FIELD_LAYOUT(fixture_point_alias_t, left);
  EMIT_FIELD_LAYOUT(fixture_point_alias_t, right);
  EMIT_FIELD_LAYOUT(fixture_point_alias_t, mode);
  EMIT_FIELD_LAYOUT(fixture_point_alias_t, label);

  EMIT_RECORD_LAYOUT(fixture_nested_point_t);
  EMIT_FIELD_LAYOUT(fixture_nested_point_t, point);
  EMIT_FIELD_LAYOUT(fixture_nested_point_t, inner);

  EMIT_RECORD_LAYOUT(fixture_with_array_t);
  EMIT_FIELD_LAYOUT(fixture_with_array_t, values);

  return 0;
}
