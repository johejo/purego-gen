/*
 * Fixture for auto_callback_inputs discovery.
 */
int fixture_register(void (*on_event)(int));
void fixture_notify(void (*on_done)(void));
