package duckdbsys

import "unsafe"

// Prepared Statements

func Prepare(conn Connection, query string, stmt *PreparedStatement) int32 {
	return duckdb_prepare(conn, query, stmt)
}

func DestroyPrepare(stmt *PreparedStatement) {
	duckdb_destroy_prepare(stmt)
}

func PrepareError(stmt PreparedStatement) string {
	return duckdb_prepare_error(stmt)
}

func Nparams(stmt PreparedStatement) uint64 {
	return duckdb_nparams(stmt)
}

func ParameterName(stmt PreparedStatement, index uint64) string {
	return duckdb_parameter_name_string(stmt, index)
}

func ParamType(stmt PreparedStatement, index uint64) int32 {
	return duckdb_param_type(stmt, index)
}

func ParamLogicalType(stmt PreparedStatement, index uint64) LogicalType {
	return duckdb_param_logical_type(stmt, index)
}

func BindParameterIndex(stmt PreparedStatement, name string) (uint64, int32) {
	var idx uint64
	state := duckdb_bind_parameter_index(stmt, &idx, name)
	return idx, state
}

func ClearBindings(stmt PreparedStatement) int32 {
	return duckdb_clear_bindings(stmt)
}

func ExecutePrepared(stmt PreparedStatement, result *Result) int32 {
	return duckdb_execute_prepared(stmt, result)
}

func ExecutePreparedStreaming(stmt PreparedStatement, result *Result) int32 {
	return duckdb_execute_prepared_streaming(stmt, result)
}

func PreparedStatementType(stmt PreparedStatement) int32 {
	return duckdb_prepared_statement_type(stmt)
}

func PreparedStatementColumnCount(stmt PreparedStatement) uint64 {
	return duckdb_prepared_statement_column_count(stmt)
}

func PreparedStatementColumnName(stmt PreparedStatement, index uint64) string {
	return duckdb_prepared_statement_column_name_string(stmt, index)
}

func PreparedStatementColumnType(stmt PreparedStatement, index uint64) int32 {
	return duckdb_prepared_statement_column_type(stmt, index)
}

func PreparedStatementColumnLogicalType(stmt PreparedStatement, index uint64) LogicalType {
	return duckdb_prepared_statement_column_logical_type(stmt, index)
}

// Binding

func BindValue(stmt PreparedStatement, idx uint64, val DuckDBValue) int32 {
	return duckdb_bind_value(stmt, idx, val)
}

func BindBoolean(stmt PreparedStatement, idx uint64, val bool) int32 {
	return duckdb_bind_boolean(stmt, idx, val)
}

func BindInt8(stmt PreparedStatement, idx uint64, val int8) int32 {
	return duckdb_bind_int8(stmt, idx, val)
}

func BindInt16(stmt PreparedStatement, idx uint64, val int16) int32 {
	return duckdb_bind_int16(stmt, idx, val)
}

func BindInt32(stmt PreparedStatement, idx uint64, val int32) int32 {
	return duckdb_bind_int32(stmt, idx, val)
}

func BindInt64(stmt PreparedStatement, idx uint64, val int64) int32 {
	return duckdb_bind_int64(stmt, idx, val)
}

func BindUint8(stmt PreparedStatement, idx uint64, val uint8) int32 {
	return duckdb_bind_uint8(stmt, idx, val)
}

func BindUint16(stmt PreparedStatement, idx uint64, val uint16) int32 {
	return duckdb_bind_uint16(stmt, idx, val)
}

func BindUint32(stmt PreparedStatement, idx uint64, val uint32) int32 {
	return duckdb_bind_uint32(stmt, idx, val)
}

func BindUint64(stmt PreparedStatement, idx uint64, val uint64) int32 {
	return duckdb_bind_uint64(stmt, idx, val)
}

func BindHugeint(stmt PreparedStatement, idx uint64, val Hugeint) int32 {
	return duckdb_bind_hugeint(stmt, idx, val)
}

func BindUhugeint(stmt PreparedStatement, idx uint64, val Uhugeint) int32 {
	return duckdb_bind_uhugeint(stmt, idx, val)
}

func BindDecimal(stmt PreparedStatement, idx uint64, val Decimal) int32 {
	return duckdb_bind_decimal(stmt, idx, val)
}

func BindFloat(stmt PreparedStatement, idx uint64, val float32) int32 {
	return duckdb_bind_float(stmt, idx, val)
}

func BindDouble(stmt PreparedStatement, idx uint64, val float64) int32 {
	return duckdb_bind_double(stmt, idx, val)
}

func BindDate(stmt PreparedStatement, idx uint64, val Date) int32 {
	return duckdb_bind_date(stmt, idx, val)
}

func BindTime(stmt PreparedStatement, idx uint64, val Time) int32 {
	return duckdb_bind_time(stmt, idx, val)
}

func BindTimestamp(stmt PreparedStatement, idx uint64, val Timestamp) int32 {
	return duckdb_bind_timestamp(stmt, idx, val)
}

func BindTimestampTZ(stmt PreparedStatement, idx uint64, val Timestamp) int32 {
	return duckdb_bind_timestamp_tz(stmt, idx, val)
}

func BindInterval(stmt PreparedStatement, idx uint64, val Interval) int32 {
	return duckdb_bind_interval(stmt, idx, val)
}

func BindVarchar(stmt PreparedStatement, idx uint64, val string) int32 {
	return duckdb_bind_varchar(stmt, idx, val)
}

func BindVarcharLength(stmt PreparedStatement, idx uint64, val string, length uint64) int32 {
	return duckdb_bind_varchar_length(stmt, idx, val, length)
}

func BindBlob(stmt PreparedStatement, idx uint64, data []byte) int32 {
	ptr := uintptr(0)
	if len(data) > 0 {
		ptr = uintptr(unsafe.Pointer(&data[0]))
	}
	return duckdb_bind_blob(stmt, idx, ptr, uint64(len(data)))
}

func BindNull(stmt PreparedStatement, idx uint64) int32 {
	return duckdb_bind_null(stmt, idx)
}
