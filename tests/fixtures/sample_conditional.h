#ifdef SAMPLE_ENABLE_EXTRA
int extra_add(int lhs, int rhs);
extern int extra_counter;
#else
int base_add(int lhs, int rhs);
#endif
