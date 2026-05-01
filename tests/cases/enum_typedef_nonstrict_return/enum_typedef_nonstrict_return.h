typedef enum fixture_status {
  FIXTURE_OK = 0,
  FIXTURE_ERR = 1,
} fixture_status_t;

fixture_status_t fixture_query(void);
