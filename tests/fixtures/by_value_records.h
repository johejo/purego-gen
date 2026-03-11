typedef struct fixture_point {
  int left;
  int right;
} fixture_point_t;

fixture_point_t fixture_make_point(fixture_point_t value);
void fixture_store_point(fixture_point_t value);
