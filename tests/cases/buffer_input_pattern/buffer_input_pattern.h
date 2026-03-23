#include <stddef.h>
#include <stdint.h>

/* Functions with (const void*, length) pairs - should be auto-detected */
int lib_send_data(int fd, const void* data, size_t data_len);
int lib_write_blob(const void* buf, uint32_t buf_len, uint32_t flags);

/* Function without buffer pair - should be skipped by pattern */
int lib_get_count(int id);

/* Function with non-void pointer - should NOT match */
int lib_read_str(const char* str, size_t str_len);
