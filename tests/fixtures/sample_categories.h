typedef unsigned int my_uint;

enum sample_status {
  SAMPLE_STATUS_OK = 0,
  SAMPLE_STATUS_NG = 2,
};

extern int global_counter;
extern const char* build_id;
static int internal_state;

int add(int lhs, int rhs);
