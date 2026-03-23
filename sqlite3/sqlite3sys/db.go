package sqlite3sys

import "runtime"

// --- Library info ---

func Libversion() string        { return sqlite3_libversion() }
func LibversionNumber() int32   { return sqlite3_libversion_number() }
func Sourceid() string          { return sqlite3_sourceid() }
func Threadsafe() int32         { return sqlite3_threadsafe() }
func Complete(sql string) int32 { return sqlite3_complete(sql) }
func Sleep(ms int32) int32      { return sqlite3_sleep(ms) }

// --- Database lifecycle ---

func OpenV2(filename string, flags int32, vfs string, db **DB) int32 {
	if vfs == "" {
		return sqlite3_open_v2(filename, db, flags, 0)
	}
	ptr, buf := cStringPtr(vfs)
	rc := sqlite3_open_v2(filename, db, flags, ptr)
	runtime.KeepAlive(buf)
	return rc
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
	return sqlite3_expanded_sql_string(stmt)
}
