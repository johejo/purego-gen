/*
 * Fixture for callback candidate detection in inspect subcommand.
 */
typedef void (*my_callback_t)(int);

int register_handler(void (*callback)(int, void*), void* user_data);
int set_callback(my_callback_t cb);
int multi_callback(void (*on_start)(void), void (*on_end)(int), int flags);
int plain_add(int a, int b);
