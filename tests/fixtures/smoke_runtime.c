#include "smoke_runtime.h"

static int smoke_counter = 0;

int smoke_reset(void) {
  smoke_counter = 0;
  return smoke_counter;
}

int smoke_increment(void) {
  smoke_counter += 1;
  return smoke_counter;
}

int smoke_get_counter(void) {
  return smoke_counter;
}
