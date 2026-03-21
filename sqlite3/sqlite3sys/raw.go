//go:generate ../../scripts/uv-run-python-src.sh -m purego_gen gen --config ./config.json --out ./generated.go

package sqlite3sys

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"sync"
	"unsafe"

	"github.com/ebitengine/purego"
)

type (
	DB             = sqlite3
	Stmt           = sqlite3_stmt
	Value          = sqlite3_value
	Context        = sqlite3_context
	Int64          = sqlite3_int64
	Uint64         = sqlite3_uint64
	DestructorType = sqlite3_destructor_type
	Backup         = sqlite3_backup
	Blob           = sqlite3_blob
	Mutex          = sqlite3_mutex
)

var (
	loadOnce sync.Once
	loadErr  error
	openV2Fn func(filename string, ppDB **sqlite3, flags int32, zVfs uintptr) int32

	// Manually registered functions that need special signatures.
	expandedSqlFn         func(pStmt *sqlite3_stmt) uintptr
	loadExtensionFn       func(db *sqlite3, zFile string, zProc uintptr, pzErrMsg uintptr) int32
	tableColumnMetadataFn func(
		db *sqlite3, zDbName string, zTableName string, zColumnName string,
		pzDataType *uintptr, pzCollSeq *uintptr,
		pNotNull *int32, pPrimaryKey *int32, pAutoinc *int32,
	) int32
	walCheckpointV2Fn func(
		db *sqlite3, zDb uintptr, eMode int32, pnLog *int32, pnCkpt *int32,
	) int32
	walCheckpointFn func(db *sqlite3, zDb uintptr) int32
)

// Load resolves libsqlite3 and registers all required symbols once per process.
func Load() error {
	loadOnce.Do(func() {
		handle, err := openLibrary()
		if err != nil {
			loadErr = err
			return
		}
		if err := sqlite3_register_functions(handle); err != nil {
			loadErr = err
			return
		}
		purego.RegisterLibFunc(&openV2Fn, handle, "sqlite3_open_v2")
		purego.RegisterLibFunc(&expandedSqlFn, handle, "sqlite3_expanded_sql")
		purego.RegisterLibFunc(&loadExtensionFn, handle, "sqlite3_load_extension")
		purego.RegisterLibFunc(&tableColumnMetadataFn, handle, "sqlite3_table_column_metadata")
		purego.RegisterLibFunc(&walCheckpointV2Fn, handle, "sqlite3_wal_checkpoint_v2")
		purego.RegisterLibFunc(&walCheckpointFn, handle, "sqlite3_wal_checkpoint")
	})
	return loadErr
}

func openLibrary() (uintptr, error) {
	candidates := libraryCandidates()
	var errs []error
	for _, candidate := range candidates {
		handle, err := purego.Dlopen(candidate, purego.RTLD_NOW|purego.RTLD_LOCAL)
		if err == nil {
			return handle, nil
		}
		errs = append(errs, fmt.Errorf("%s: %w", candidate, err))
	}
	return 0, fmt.Errorf("open libsqlite3: %v", errs)
}

func libraryCandidates() []string {
	var candidates []string

	if envPath := os.Getenv("PUREGO_GEN_TEST_LIBSQLITE3_PATH"); envPath != "" {
		candidates = append(candidates, envPath)
	}
	if envDir := os.Getenv("PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR"); envDir != "" {
		candidates = append(candidates, sharedLibraryCandidates(envDir, "sqlite3")...)
	}

	switch runtime.GOOS {
	case "darwin":
		candidates = append(candidates, "libsqlite3.dylib")
	default:
		candidates = append(candidates, "libsqlite3.so", "libsqlite3.so.0")
	}

	return dedupeStrings(candidates)
}

func sharedLibraryCandidates(libDir string, libraryName string) []string {
	stem := libraryName
	if len(stem) < 3 || stem[:3] != "lib" {
		stem = "lib" + stem
	}

	if runtime.GOOS == "darwin" {
		return []string{filepath.Join(libDir, stem+".dylib")}
	}

	candidates := []string{filepath.Join(libDir, stem+".so")}
	matches, err := filepath.Glob(filepath.Join(libDir, stem+".so.*"))
	if err == nil {
		sort.Strings(matches)
		candidates = append(candidates, matches...)
	}
	return candidates
}

func dedupeStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	out := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}

// --- Library info ---

func Libversion() string        { return sqlite3_libversion() }
func LibversionNumber() int32   { return sqlite3_libversion_number() }
func Sourceid() string          { return sqlite3_sourceid() }
func Threadsafe() int32         { return sqlite3_threadsafe() }
func Complete(sql string) int32 { return sqlite3_complete(sql) }
func Sleep(ms int32) int32      { return sqlite3_sleep(ms) }

// --- Database lifecycle ---

func OpenV2(filename string, flags int32, vfs string, db **DB) int32 {
	if vfs != "" {
		return sqlite3_open_v2(filename, db, flags, vfs)
	}
	return openV2Fn(filename, db, flags, 0)
}

func CloseV2(db *DB) int32               { return sqlite3_close_v2(db) }
func Errmsg(db *DB) string               { return sqlite3_errmsg(db) }
func Errcode(db *DB) int32               { return sqlite3_errcode(db) }
func ExtendedErrcode(db *DB) int32       { return sqlite3_extended_errcode(db) }
func Errstr(rc int32) string             { return sqlite3_errstr(rc) }
func ErrorOffset(db *DB) int32           { return sqlite3_error_offset(db) }
func BusyTimeout(db *DB, ms int32) int32 { return sqlite3_busy_timeout(db, ms) }

func ExtendedResultCodes(db *DB, onoff int32) int32 {
	return sqlite3_extended_result_codes(db, onoff)
}

func GetAutocommit(db *DB) int32              { return sqlite3_get_autocommit(db) }
func IsInterrupted(db *DB) int32              { return sqlite3_is_interrupted(db) }
func DBHandle(stmt *Stmt) *DB                 { return sqlite3_db_handle(stmt) }
func DBName(db *DB, n int32) string           { return sqlite3_db_name(db, n) }
func DBFilename(db *DB, dbName string) string { return sqlite3_db_filename(db, dbName) }
func DBReadonly(db *DB, dbName string) int32  { return sqlite3_db_readonly(db, dbName) }
func TxnState(db *DB, schema string) int32    { return sqlite3_txn_state(db, schema) }
func ContextDBHandle(ctx *Context) *DB        { return sqlite3_context_db_handle(ctx) }
func DBMutex(db *DB) *Mutex                   { return sqlite3_db_mutex(db) }
func SystemErrno(db *DB) int32                { return sqlite3_system_errno(db) }
func DBCacheflush(db *DB) int32               { return sqlite3_db_cacheflush(db) }

func Limit(db *DB, id int32, newVal int32) int32 {
	return sqlite3_limit(db, id, newVal)
}

// --- Statement lifecycle ---

func PrepareV2(db *DB, sql string, stmt **Stmt) int32 {
	return sqlite3_prepare_v2(db, sql, -1, stmt, 0)
}

func Finalize(stmt *Stmt) int32      { return sqlite3_finalize(stmt) }
func Reset(stmt *Stmt) int32         { return sqlite3_reset(stmt) }
func ClearBindings(stmt *Stmt) int32 { return sqlite3_clear_bindings(stmt) }
func Step(stmt *Stmt) int32          { return sqlite3_step(stmt) }
func Interrupt(db *DB)               { sqlite3_interrupt(db) }

func SQL(stmt *Stmt) string                     { return sqlite3_sql(stmt) }
func StmtReadonly(stmt *Stmt) int32             { return sqlite3_stmt_readonly(stmt) }
func StmtIsexplain(stmt *Stmt) int32            { return sqlite3_stmt_isexplain(stmt) }
func StmtExplain(stmt *Stmt, eMode int32) int32 { return sqlite3_stmt_explain(stmt, eMode) }
func StmtBusy(stmt *Stmt) int32                 { return sqlite3_stmt_busy(stmt) }
func DataCount(stmt *Stmt) int32                { return sqlite3_data_count(stmt) }
func NextStmt(db *DB, stmt *Stmt) *Stmt         { return sqlite3_next_stmt(db, stmt) }
func StmtStatus(stmt *Stmt, op int32, resetFlg int32) int32 {
	return sqlite3_stmt_status(stmt, op, resetFlg)
}

// ExpandedSQL returns the SQL text of a prepared statement with bound
// parameters expanded. The returned string is a copy; the caller does not
// need to free anything.
func ExpandedSQL(stmt *Stmt) string {
	ptr := expandedSqlFn(stmt)
	if ptr == 0 {
		return ""
	}
	s := goString(ptr)
	sqlite3_free(ptr)
	return s
}

// --- Binding ---

func BindParameterCount(stmt *Stmt) int32 { return sqlite3_bind_parameter_count(stmt) }
func BindParameterIndex(stmt *Stmt, name string) int32 {
	return sqlite3_bind_parameter_index(stmt, name)
}
func BindParameterName(stmt *Stmt, index int32) string {
	return sqlite3_bind_parameter_name(stmt, index)
}
func BindNull(stmt *Stmt, index int32) int32 { return sqlite3_bind_null(stmt, index) }
func BindBlobBytes(stmt *Stmt, index int32, value []byte, destructor DestructorType) int32 {
	return sqlite3_bind_blob_bytes(stmt, index, value, destructor)
}
func BindDouble(stmt *Stmt, index int32, value float64) int32 {
	return sqlite3_bind_double(stmt, index, value)
}
func BindInt(stmt *Stmt, index int32, value int32) int32 {
	return sqlite3_bind_int(stmt, index, value)
}
func BindInt64(stmt *Stmt, index int32, value int64) int32 {
	return sqlite3_bind_int64(stmt, index, value)
}
func BindText(stmt *Stmt, index int32, value string, destructor DestructorType) int32 {
	return sqlite3_bind_text(stmt, index, value, -1, destructor)
}
func BindValue(stmt *Stmt, index int32, value *Value) int32 {
	return sqlite3_bind_value(stmt, index, value)
}
func BindZeroblob(stmt *Stmt, index int32, n int32) int32 {
	return sqlite3_bind_zeroblob(stmt, index, n)
}
func BindZeroblob64(stmt *Stmt, index int32, n uint64) int32 {
	return sqlite3_bind_zeroblob64(stmt, index, n)
}

// --- Columns ---

func ColumnCount(stmt *Stmt) int32 { return sqlite3_column_count(stmt) }
func ColumnType(stmt *Stmt, index int32) int32 {
	return sqlite3_column_type(stmt, index)
}
func ColumnBytes(stmt *Stmt, index int32) int32 {
	return sqlite3_column_bytes(stmt, index)
}
func ColumnInt(stmt *Stmt, index int32) int32 {
	return sqlite3_column_int(stmt, index)
}
func ColumnInt64(stmt *Stmt, index int32) int64 {
	return sqlite3_column_int64(stmt, index)
}
func ColumnDouble(stmt *Stmt, index int32) float64 {
	return sqlite3_column_double(stmt, index)
}
func ColumnText(stmt *Stmt, index int32) string { return sqlite3_column_text(stmt, index) }
func ColumnName(stmt *Stmt, index int32) string { return sqlite3_column_name(stmt, index) }
func ColumnDeclType(stmt *Stmt, index int32) string {
	return sqlite3_column_decltype(stmt, index)
}
func ColumnValue(stmt *Stmt, index int32) *Value {
	return sqlite3_column_value(stmt, index)
}
func ColumnBlobBytes(stmt *Stmt, index int32) []byte {
	ptr := sqlite3_column_blob(stmt, index)
	length := sqlite3_column_bytes(stmt, index)
	return copyBytes(ptr, length)
}
func ColumnDatabaseName(stmt *Stmt, index int32) string {
	return sqlite3_column_database_name(stmt, index)
}
func ColumnTableName(stmt *Stmt, index int32) string {
	return sqlite3_column_table_name(stmt, index)
}
func ColumnOriginName(stmt *Stmt, index int32) string {
	return sqlite3_column_origin_name(stmt, index)
}

// --- Changes/rowid ---

func Changes(db *DB) int32                { return sqlite3_changes(db) }
func Changes64(db *DB) int64              { return sqlite3_changes64(db) }
func TotalChanges(db *DB) int32           { return sqlite3_total_changes(db) }
func TotalChanges64(db *DB) int64         { return sqlite3_total_changes64(db) }
func LastInsertRowid(db *DB) int64        { return sqlite3_last_insert_rowid(db) }
func SetLastInsertRowid(db *DB, id int64) { sqlite3_set_last_insert_rowid(db, id) }
func UserData(ctx *Context) uintptr       { return sqlite3_user_data(ctx) }
func AggregateContext(ctx *Context, nBytes int32) uintptr {
	return sqlite3_aggregate_context(ctx, nBytes)
}

// --- Function/collation registration ---

func CreateFunctionV2Callbacks(
	db *DB,
	name string,
	nArg int32,
	textRep int32,
	app uintptr,
	xFunc func(*Context, int32, **Value),
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_function_v2_callbacks(
		db,
		name,
		nArg,
		textRep,
		app,
		xFunc,
		nil,
		nil,
		xDestroy,
	)
}

func CreateAggregateFunctionV2Callbacks(
	db *DB,
	name string,
	nArg int32,
	textRep int32,
	app uintptr,
	xStep func(*Context, int32, **Value),
	xFinal func(*Context),
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_function_v2_callbacks(
		db,
		name,
		nArg,
		textRep,
		app,
		nil,
		xStep,
		xFinal,
		xDestroy,
	)
}

func CreateWindowFunctionCallbacks(
	db *DB,
	name string,
	nArg int32,
	textRep int32,
	app uintptr,
	xStep func(*Context, int32, **Value),
	xFinal func(*Context),
	xValue func(*Context),
	xInverse func(*Context, int32, **Value),
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_window_function_callbacks(
		db,
		name,
		nArg,
		textRep,
		app,
		xStep,
		xFinal,
		xValue,
		xInverse,
		xDestroy,
	)
}

func CreateCollationV2Callbacks(
	db *DB,
	name string,
	textRep int32,
	app uintptr,
	xCompare func(uintptr, int32, uintptr, int32, uintptr) int32,
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_collation_v2_callbacks(
		db,
		name,
		textRep,
		app,
		xCompare,
		xDestroy,
	)
}

// --- Values ---

func ValueType(value *Value) int32        { return sqlite3_value_type(value) }
func ValueInt(value *Value) int32         { return sqlite3_value_int(value) }
func ValueInt64(value *Value) int64       { return sqlite3_value_int64(value) }
func ValueDouble(value *Value) float64    { return sqlite3_value_double(value) }
func ValueText(value *Value) string       { return sqlite3_value_text(value) }
func ValueNumericType(value *Value) int32 { return sqlite3_value_numeric_type(value) }
func ValueNochange(value *Value) int32    { return sqlite3_value_nochange(value) }
func ValueFrombind(value *Value) int32    { return sqlite3_value_frombind(value) }
func ValueSubtype(value *Value) uint32    { return sqlite3_value_subtype(value) }
func ValueDup(value *Value) *Value        { return sqlite3_value_dup(value) }
func ValueFree(value *Value)              { sqlite3_value_free(value) }
func ValueBlobBytes(value *Value) []byte {
	ptr := sqlite3_value_blob(value)
	length := sqlite3_value_bytes(value)
	return copyBytes(ptr, length)
}

// --- Results ---

func ResultNull(ctx *Context) { sqlite3_result_null(ctx) }
func ResultBlobBytes(ctx *Context, value []byte, destructor DestructorType) {
	sqlite3_result_blob_bytes(ctx, value, destructor)
}
func ResultDouble(ctx *Context, value float64) { sqlite3_result_double(ctx, value) }
func ResultInt(ctx *Context, value int32)      { sqlite3_result_int(ctx, value) }
func ResultInt64(ctx *Context, value int64)    { sqlite3_result_int64(ctx, value) }
func ResultText(ctx *Context, value string, destructor DestructorType) {
	sqlite3_result_text(ctx, value, -1, destructor)
}
func ResultError(ctx *Context, value string) { sqlite3_result_error(ctx, value, -1) }
func ResultValue(ctx *Context, value *Value) { sqlite3_result_value(ctx, value) }
func ResultZeroblob(ctx *Context, n int32)   { sqlite3_result_zeroblob(ctx, n) }
func ResultZeroblob64(ctx *Context, n uint64) int32 {
	return sqlite3_result_zeroblob64(ctx, n)
}
func ResultSubtype(ctx *Context, subtype uint32) { sqlite3_result_subtype(ctx, subtype) }
func ResultErrorToobig(ctx *Context)             { sqlite3_result_error_toobig(ctx) }
func ResultErrorNomem(ctx *Context)              { sqlite3_result_error_nomem(ctx) }
func ResultErrorCode(ctx *Context, code int32)   { sqlite3_result_error_code(ctx, code) }

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
		return walCheckpointV2Fn(db, 0, mode, nLog, nCkpt)
	}
	return sqlite3_wal_checkpoint_v2(db, dbName, mode, nLog, nCkpt)
}
func WalAutocheckpoint(db *DB, n int32) int32 { return sqlite3_wal_autocheckpoint(db, n) }

// WalCheckpoint runs a passive checkpoint. Pass empty dbName for the default
// (main) database.
func WalCheckpoint(db *DB, dbName string) int32 {
	if dbName == "" {
		return walCheckpointFn(db, 0)
	}
	return sqlite3_wal_checkpoint(db, dbName)
}

// --- Table Column Metadata ---

// TableColumnMetadata retrieves metadata about a specific column.
func TableColumnMetadata(
	db *DB, dbName, tableName, columnName string,
) (dataType, collSeq string, notNull, primaryKey, autoinc, rc int32) {
	var pzDataType, pzCollSeq uintptr
	rc = tableColumnMetadataFn(
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
		return loadExtensionFn(db, file, 0, 0)
	}
	return sqlite3_load_extension(db, file, proc, 0)
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

// --- Helpers ---

func copyBytes(ptr uintptr, length int32) []byte {
	return copyBytesN(ptr, int(length))
}

func copyBytesN(ptr uintptr, length int) []byte {
	if ptr == 0 || length <= 0 {
		return nil
	}
	src := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), ptr)), length)
	dst := make([]byte, length)
	copy(dst, src)
	return dst
}

// goStringMaxLen is the maximum number of bytes goString will scan.
const goStringMaxLen = 1 << 30

func goString(ptr uintptr) string {
	if ptr == 0 {
		return ""
	}
	p := unsafe.Add(unsafe.Pointer(nil), ptr)
	n := 0
	for n < goStringMaxLen && *(*byte)(unsafe.Add(p, n)) != 0 {
		n++
	}
	return string(unsafe.Slice((*byte)(p), n))
}
