#include "buffer_input_helper.h"

#include <stdint.h>

int fixture_sum_bytes(const void* data, size_t data_len, uint32_t salt) {
  const uint8_t* bytes = (const uint8_t*)data;
  uint32_t total = salt;
  for (size_t i = 0; i < data_len; ++i) {
    total += bytes[i];
  }
  return (int)total;
}
