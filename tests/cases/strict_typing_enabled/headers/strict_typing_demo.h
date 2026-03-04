/*
 * Fixture declarations to compare strict/non-strict enum and sentinel typing.
 */
typedef enum strict_typing_demo_error_code {
  STRICT_TYPING_DEMO_ERROR_OK = 0,
  STRICT_TYPING_DEMO_ERROR_INTERNAL = 1,
} strict_typing_demo_error_code_t;

strict_typing_demo_error_code_t strict_typing_demo_get_error_code(unsigned long long result);

#define STRICT_TYPING_DEMO_CONTENTSIZE_UNKNOWN (0ULL - 1)
#define STRICT_TYPING_DEMO_CONTENTSIZE_ERROR (0ULL - 2)
