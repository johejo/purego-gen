/*
 * Fixture declarations that cover const/var parsing categories.
 * Identifier spellings are part of stable golden outputs.
 */
typedef unsigned int my_uint;

enum fixture_status {
  FIXTURE_STATUS_OK = 0,
  FIXTURE_STATUS_NG = 2,
};

extern int global_counter;
extern const char* build_id;
static int internal_state;

int add(int lhs, int rhs);
