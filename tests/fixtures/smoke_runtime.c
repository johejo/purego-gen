#include "smoke_runtime.h"

int smoke_counter = 0;

void smoke_reset(void) {
  smoke_counter = 0;
}

void smoke_increment(void) {
  smoke_counter += 1;
}
