package sqlite3sys

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
