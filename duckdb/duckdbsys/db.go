package duckdbsys

import "unsafe"

// Lifecycle

func Open(path string, db *Database) int32 {
	return duckdb_open(path, db)
}

func OpenExt(path string, db *Database, config Config, outError *uintptr) int32 {
	return duckdb_open_ext(path, db, config, uintptr(unsafe.Pointer(outError)))
}

func Close(db *Database) {
	duckdb_close(db)
}

func Connect(db Database, conn *Connection) int32 {
	return duckdb_connect(db, conn)
}

func Disconnect(conn *Connection) {
	duckdb_disconnect(conn)
}

func Interrupt(conn Connection) {
	duckdb_interrupt(conn)
}

func LibraryVersion() string {
	return duckdb_library_version()
}

// Config

func CreateConfig(config *Config) int32 {
	return duckdb_create_config(config)
}

func ConfigCount() uint64 {
	return duckdb_config_count()
}

func GetConfigFlag(index uint64) (name string, description string, state int32) {
	var namePtr, descPtr uintptr
	state = duckdb_get_config_flag(index, uintptr(unsafe.Pointer(&namePtr)), uintptr(unsafe.Pointer(&descPtr)))
	if state == DuckDBSuccess {
		name = gostring(namePtr)
		description = gostring(descPtr)
	}
	return
}

func SetConfig(config Config, name string, option string) int32 {
	return duckdb_set_config(config, name, option)
}

func DestroyConfig(config *Config) {
	duckdb_destroy_config(config)
}

// Query

func Query(conn Connection, query string, result *Result) int32 {
	return duckdb_query(conn, query, result)
}

func DestroyResult(result *Result) {
	duckdb_destroy_result(result)
}

func ResultError(result *Result) string {
	return duckdb_result_error(result)
}

func ResultErrorType(result *Result) int32 {
	return duckdb_result_error_type(result)
}

func ResultStatementType(result Result) int32 {
	return duckdb_result_statement_type(result)
}

func ResultReturnType(result Result) int32 {
	return duckdb_result_return_type(result)
}

func RowsChanged(result *Result) uint64 {
	return duckdb_rows_changed(result)
}

func RowCount(result *Result) uint64 {
	return duckdb_row_count(result)
}

func ColumnCount(result *Result) uint64 {
	return duckdb_column_count(result)
}

func ColumnName(result *Result, col uint64) string {
	return duckdb_column_name(result, col)
}

func ColumnType(result *Result, col uint64) int32 {
	return duckdb_column_type(result, col)
}

func ColumnLogicalType(result *Result, col uint64) LogicalType {
	return duckdb_column_logical_type(result, col)
}

func ResultChunkCount(result Result) uint64 {
	return duckdb_result_chunk_count(result)
}

func ResultGetChunk(result Result, chunkIndex uint64) DataChunk {
	return duckdb_result_get_chunk(result, chunkIndex)
}

func ResultIsStreaming(result Result) bool {
	return duckdb_result_is_streaming(result)
}
