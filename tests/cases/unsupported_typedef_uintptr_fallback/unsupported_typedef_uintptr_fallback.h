/*
 * Pins graceful degradation for references to a typedef whose body cannot be
 * rendered. `bitfield_record_t` has bit-field members, so the typedef itself is
 * skipped; functions that reference it must still be emitted, with the
 * unresolvable type falling back to `uintptr` (matching the Python generator)
 * instead of aborting generation.
 */
typedef struct bitfield_record {
  unsigned flags : 4;
  unsigned kind : 4;
} bitfield_record_t;

int use_bitfield(bitfield_record_t *handle, bitfield_record_t value);
