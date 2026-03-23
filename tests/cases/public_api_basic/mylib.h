typedef struct mylib_db mylib_db;
typedef struct mylib_stmt mylib_stmt;
typedef struct mylib_value mylib_value;

void* mylib_malloc(int size);
void mylib_free(void* ptr);
int mylib_db_release_memory(mylib_db* db);
const char* mylib_db_filename(mylib_db* db, const char* name);
int mylib_bind_int(mylib_stmt* stmt, int index, int value);
int mylib_bind_text(mylib_stmt* stmt, int index, const char* text, int n);
