#ifndef PUREGO_GEN_STAGE1_PARSE
#error "PUREGO_GEN_STAGE1_PARSE must be defined"
#endif

typedef struct purego_gen_stage1_point {
  int left;
  int right;
} purego_gen_stage1_point_t;

typedef const char* purego_gen_stage1_name_t;

extern int purego_gen_stage1_counter;

/** stage1 point docs */
purego_gen_stage1_point_t purego_gen_stage1_make_point(purego_gen_stage1_point_t value);
