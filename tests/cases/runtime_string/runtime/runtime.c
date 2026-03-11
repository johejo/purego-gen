#include "smoke_string_runtime.h"

#include <string.h>

static const char* last_roundtrip = "";

const char* smoke_const_greeting(void) { return "hello-from-c"; }

int smoke_const_is_expected(const char* value) {
  if (value == NULL) {
    return 0;
  }
  return strcmp(value, "ping-from-go") == 0 ? 1 : 0;
}

const char* smoke_const_roundtrip(const char* value) {
  last_roundtrip = value == NULL ? "" : value;
  return last_roundtrip;
}
