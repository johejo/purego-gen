/*
 * Fixture declarations for casted sentinel macro extraction.
 */
typedef void (*fixture_destructor_t)(void*);

#define FIXTURE_STATIC ((fixture_destructor_t)0)
#define FIXTURE_TRANSIENT ((fixture_destructor_t) - 1)
