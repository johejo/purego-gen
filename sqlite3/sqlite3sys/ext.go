package sqlite3sys

import (
	"runtime"
	"unsafe"
)

// --- Memory ---

func Malloc(n int32) uintptr                  { return sqlite3_malloc(n) }
func Malloc64(n uint64) uintptr               { return sqlite3_malloc64(n) }
func Realloc(ptr uintptr, n int32) uintptr    { return sqlite3_realloc(ptr, n) }
func Realloc64(ptr uintptr, n uint64) uintptr { return sqlite3_realloc64(ptr, n) }
func Free(ptr uintptr)                        { sqlite3_free(ptr) }
func MemoryUsed() int64                       { return sqlite3_memory_used() }
func MemoryHighwater(resetFlag int32) int64   { return sqlite3_memory_highwater(resetFlag) }
func SoftHeapLimit64(n int64) int64           { return sqlite3_soft_heap_limit64(n) }
func HardHeapLimit64(n int64) int64           { return sqlite3_hard_heap_limit64(n) }
func ReleaseMemory(n int32) int32             { return sqlite3_release_memory(n) }
func DBReleaseMemory(db *DB) int32            { return sqlite3_db_release_memory(db) }

// --- Hooks ---

func CommitHook(db *DB, callback func(uintptr) int32, userData uintptr) uintptr {
	return sqlite3_commit_hook_callbacks(db, callback, userData)
}

func RollbackHook(db *DB, callback func(uintptr), userData uintptr) uintptr {
	return sqlite3_rollback_hook_callbacks(db, callback, userData)
}

func UpdateHook(db *DB, callback func(uintptr, int32, uintptr, uintptr, int64), userData uintptr) uintptr {
	return sqlite3_update_hook_callbacks(db, callback, userData)
}

func ProgressHandler(db *DB, nOps int32, callback func(uintptr) int32, userData uintptr) {
	sqlite3_progress_handler_callbacks(db, nOps, callback, userData)
}

func TraceV2(db *DB, mask uint32, callback func(uint32, uintptr, uintptr, uintptr) int32, userData uintptr) int32 {
	return sqlite3_trace_v2_callbacks(db, mask, callback, userData)
}

func BusyHandler(db *DB, callback func(uintptr, int32) int32, userData uintptr) int32 {
	return sqlite3_busy_handler_callbacks(db, callback, userData)
}

func SetAuthorizer(db *DB, callback func(uintptr, int32, uintptr, uintptr, uintptr, uintptr) int32, userData uintptr) int32 {
	return sqlite3_set_authorizer_callbacks(db, callback, userData)
}

func WalHook(db *DB, callback func(uintptr, *DB, uintptr, int32) int32, userData uintptr) uintptr {
	return sqlite3_wal_hook_callbacks(db, callback, userData)
}

// --- Backup API ---

func BackupInit(dest *DB, destName string, source *DB, sourceName string) *Backup {
	return sqlite3_backup_init(dest, destName, source, sourceName)
}
func BackupStep(backup *Backup, nPage int32) int32 { return sqlite3_backup_step(backup, nPage) }
func BackupFinish(backup *Backup) int32            { return sqlite3_backup_finish(backup) }
func BackupRemaining(backup *Backup) int32         { return sqlite3_backup_remaining(backup) }
func BackupPagecount(backup *Backup) int32         { return sqlite3_backup_pagecount(backup) }

// --- Blob I/O ---

func BlobOpen(db *DB, dbName, table, column string, row int64, flags int32, blob **Blob) int32 {
	return sqlite3_blob_open(db, dbName, table, column, row, flags, blob)
}
func BlobClose(blob *Blob) int32             { return sqlite3_blob_close(blob) }
func BlobBytes(blob *Blob) int32             { return sqlite3_blob_bytes(blob) }
func BlobReopen(blob *Blob, row int64) int32 { return sqlite3_blob_reopen(blob, row) }

func BlobReadBytes(blob *Blob, buf []byte, offset int32) int32 {
	return sqlite3_blob_read_bytes(blob, buf, offset)
}

func BlobWriteBytes(blob *Blob, data []byte, offset int32) int32 {
	return sqlite3_blob_write_bytes(blob, data, offset)
}

// --- WAL ---

// WalCheckpointV2 runs a checkpoint. Pass empty dbName for the default (main)
// database, which passes NULL to C (distinct from the string "main").
func WalCheckpointV2(db *DB, dbName string, mode int32, nLog *int32, nCkpt *int32) int32 {
	if dbName == "" {
		return sqlite3_wal_checkpoint_v2(db, 0, mode, nLog, nCkpt)
	}
	ptr, buf := cStringPtr(dbName)
	rc := sqlite3_wal_checkpoint_v2(db, ptr, mode, nLog, nCkpt)
	runtime.KeepAlive(buf)
	return rc
}
func WalAutocheckpoint(db *DB, n int32) int32 { return sqlite3_wal_autocheckpoint(db, n) }

// WalCheckpoint runs a passive checkpoint. Pass empty dbName for the default
// (main) database.
func WalCheckpoint(db *DB, dbName string) int32 {
	if dbName == "" {
		return sqlite3_wal_checkpoint(db, 0)
	}
	ptr, buf := cStringPtr(dbName)
	rc := sqlite3_wal_checkpoint(db, ptr)
	runtime.KeepAlive(buf)
	return rc
}

// --- Table Column Metadata ---

// TableColumnMetadata retrieves metadata about a specific column.
func TableColumnMetadata(
	db *DB, dbName, tableName, columnName string,
) (dataType, collSeq string, notNull, primaryKey, autoinc, rc int32) {
	var pzDataType, pzCollSeq uintptr
	rc = sqlite3_table_column_metadata(
		db, dbName, tableName, columnName,
		&pzDataType, &pzCollSeq,
		&notNull, &primaryKey, &autoinc,
	)
	if rc == SQLITE_OK {
		dataType = goString(pzDataType)
		collSeq = goString(pzCollSeq)
	}
	return
}

// --- Extension Loading ---

// LoadExtension loads a shared library extension. Pass empty proc for the
// default entry point.
func LoadExtension(db *DB, file string, proc string) int32 {
	if proc == "" {
		return sqlite3_load_extension(db, file, 0, 0)
	}
	ptr, buf := cStringPtr(proc)
	rc := sqlite3_load_extension(db, file, ptr, 0)
	runtime.KeepAlive(buf)
	return rc
}

func EnableLoadExtension(db *DB, onoff int32) int32 {
	return sqlite3_enable_load_extension(db, onoff)
}

func ResetAutoExtension() { sqlite3_reset_auto_extension() }

// --- Serialization ---

// Serialize serializes a database into a byte slice. The returned bytes are
// always a Go-owned copy regardless of whether SQLITE_SERIALIZE_NOCOPY is set.
// Returns nil on error (e.g., unknown schema). An empty but non-nil slice
// indicates a valid empty database.
func Serialize(db *DB, schema string, flags uint32) []byte {
	var size int64
	ptr := sqlite3_serialize(db, schema, &size, flags)
	if ptr == 0 {
		return nil
	}
	if size == 0 {
		if flags&SQLITE_SERIALIZE_NOCOPY == 0 {
			sqlite3_free(ptr)
		}
		return []byte{}
	}
	data := copyBytesN(ptr, int(size))
	if flags&SQLITE_SERIALIZE_NOCOPY == 0 {
		sqlite3_free(ptr)
	}
	return data
}

// Deserialize loads a database from a byte slice. The data is copied to
// SQLite-managed memory and SQLITE_DESERIALIZE_FREEONCLOSE is always added
// to flags so that SQLite frees the buffer when the connection closes.
// The caller must not rely on the absence of FREEONCLOSE.
func Deserialize(db *DB, schema string, data []byte, flags uint32) int32 {
	sz := int64(len(data))
	buf := sqlite3_malloc64(uint64(sz))
	if buf == 0 && sz > 0 {
		return SQLITE_NOMEM
	}
	if sz > 0 {
		dst := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), buf)), int(sz))
		copy(dst, data)
	}
	return sqlite3_deserialize(db, schema, buf, sz, sz, flags|SQLITE_DESERIALIZE_FREEONCLOSE)
}

// --- Status ---

func Status(op int32, resetFlag int32) (current, highwater, rc int32) {
	rc = sqlite3_status(op, &current, &highwater, resetFlag)
	return
}

func Status64(op int32, resetFlag int32) (current, highwater int64, rc int32) {
	rc = sqlite3_status64(op, &current, &highwater, resetFlag)
	return
}

func DBStatus(db *DB, op int32, resetFlag int32) (current, highwater, rc int32) {
	rc = sqlite3_db_status(db, op, &current, &highwater, resetFlag)
	return
}

func DBStatus64(db *DB, op int32, resetFlag int32) (current, highwater int64, rc int32) {
	rc = sqlite3_db_status64(db, op, &current, &highwater, resetFlag)
	return
}
