package duckdbsys

// Extracted Statements

func ExtractStatements(conn Connection, query string, stmts *ExtractedStmts) uint64 {
	return duckdb_extract_statements(conn, query, stmts)
}

func PrepareExtractedStatement(conn Connection, stmts ExtractedStmts, index uint64, stmt *PreparedStatement) int32 {
	return duckdb_prepare_extracted_statement(conn, stmts, index, stmt)
}

func ExtractStatementsError(stmts ExtractedStmts) string {
	return duckdb_extract_statements_error(stmts)
}

func DestroyExtracted(stmts *ExtractedStmts) {
	duckdb_destroy_extracted(stmts)
}

// Pending Result

func PendingPrepared(stmt PreparedStatement, pending *PendingResult) int32 {
	return duckdb_pending_prepared(stmt, pending)
}

func PendingPreparedStreaming(stmt PreparedStatement, pending *PendingResult) int32 {
	return duckdb_pending_prepared_streaming(stmt, pending)
}

func DestroyPending(pending *PendingResult) {
	duckdb_destroy_pending(pending)
}

func PendingError(pending PendingResult) string {
	return duckdb_pending_error(pending)
}

func PendingExecuteTask(pending PendingResult) int32 {
	return duckdb_pending_execute_task(pending)
}

func PendingExecuteCheckState(pending PendingResult) int32 {
	return duckdb_pending_execute_check_state(pending)
}

func ExecutePending(pending PendingResult, result *Result) int32 {
	return duckdb_execute_pending(pending, result)
}

func PendingExecutionIsFinished(state int32) bool {
	return duckdb_pending_execution_is_finished(state)
}

// Value API

func DestroyValue(val *DuckDBValue) {
	duckdb_destroy_value(val)
}

func CreateVarchar(text string) DuckDBValue {
	return duckdb_create_varchar(text)
}

func CreateVarcharLength(text string, length uint64) DuckDBValue {
	return duckdb_create_varchar_length(text, length)
}

func CreateBool(val bool) DuckDBValue {
	return duckdb_create_bool(val)
}

func CreateInt8(val int8) DuckDBValue {
	return duckdb_create_int8(val)
}

func CreateUint8(val uint8) DuckDBValue {
	return duckdb_create_uint8(val)
}

func CreateInt16(val int16) DuckDBValue {
	return duckdb_create_int16(val)
}

func CreateUint16(val uint16) DuckDBValue {
	return duckdb_create_uint16(val)
}

func CreateInt32(val int32) DuckDBValue {
	return duckdb_create_int32(val)
}

func CreateUint32(val uint32) DuckDBValue {
	return duckdb_create_uint32(val)
}

func CreateInt64(val int64) DuckDBValue {
	return duckdb_create_int64(val)
}

func CreateUint64(val uint64) DuckDBValue {
	return duckdb_create_uint64(val)
}

func CreateHugeint(val Hugeint) DuckDBValue {
	return duckdb_create_hugeint(val)
}

func CreateUhugeint(val Uhugeint) DuckDBValue {
	return duckdb_create_uhugeint(val)
}

func CreateDecimalValue(val Decimal) DuckDBValue {
	return duckdb_create_decimal(val)
}

func CreateFloat(val float32) DuckDBValue {
	return duckdb_create_float(val)
}

func CreateDouble(val float64) DuckDBValue {
	return duckdb_create_double(val)
}

func CreateDateValue(val Date) DuckDBValue {
	return duckdb_create_date(val)
}

func CreateTimeValue(val Time) DuckDBValue {
	return duckdb_create_time(val)
}

func CreateTimeTZValue(val TimeTZ) DuckDBValue {
	return duckdb_create_time_tz_value(val)
}

func CreateTimestampValue(val Timestamp) DuckDBValue {
	return duckdb_create_timestamp(val)
}

func CreateTimestampTZValue(val Timestamp) DuckDBValue {
	return duckdb_create_timestamp_tz(val)
}

func CreateTimestampSValue(val TimestampS) DuckDBValue {
	return duckdb_create_timestamp_s(val)
}

func CreateTimestampMSValue(val TimestampMS) DuckDBValue {
	return duckdb_create_timestamp_ms(val)
}

func CreateTimestampNSValue(val TimestampNS) DuckDBValue {
	return duckdb_create_timestamp_ns(val)
}

func CreateIntervalValue(val Interval) DuckDBValue {
	return duckdb_create_interval(val)
}

func CreateBlobValue(data []byte) DuckDBValue {
	// duckdb_create_blob takes (const uint8_t*, idx_t); purego maps const uint8_t* to string.
	return duckdb_create_blob(string(data), uint64(len(data)))
}

func CreateUUID(val Uhugeint) DuckDBValue {
	return duckdb_create_uuid(val)
}

func CreateNullValue() DuckDBValue {
	return duckdb_create_null_value()
}

func CreateEnumValue(logicalType LogicalType, val uint64) DuckDBValue {
	return duckdb_create_enum_value(logicalType, val)
}

func CreateStructValue(logicalType LogicalType, values *DuckDBValue) DuckDBValue {
	return duckdb_create_struct_value(logicalType, values)
}

func CreateListValue(logicalType LogicalType, values *DuckDBValue, size uint64) DuckDBValue {
	return duckdb_create_list_value(logicalType, values, size)
}

func CreateArrayValue(logicalType LogicalType, values *DuckDBValue, size uint64) DuckDBValue {
	return duckdb_create_array_value(logicalType, values, size)
}

func CreateMapValue(logicalType LogicalType, keys *DuckDBValue, values *DuckDBValue, size uint64) DuckDBValue {
	return duckdb_create_map_value(logicalType, keys, values, size)
}

func CreateUnionValue(logicalType LogicalType, memberIndex uint64, val DuckDBValue) DuckDBValue {
	return duckdb_create_union_value(logicalType, memberIndex, val)
}

func GetBool(val DuckDBValue) bool {
	return duckdb_get_bool(val)
}

func GetInt8(val DuckDBValue) int8 {
	return duckdb_get_int8(val)
}

func GetUint8(val DuckDBValue) uint8 {
	return duckdb_get_uint8(val)
}

func GetInt16(val DuckDBValue) int16 {
	return duckdb_get_int16(val)
}

func GetUint16(val DuckDBValue) uint16 {
	return duckdb_get_uint16(val)
}

func GetInt32(val DuckDBValue) int32 {
	return duckdb_get_int32(val)
}

func GetUint32(val DuckDBValue) uint32 {
	return duckdb_get_uint32(val)
}

func GetInt64(val DuckDBValue) int64 {
	return duckdb_get_int64(val)
}

func GetUint64(val DuckDBValue) uint64 {
	return duckdb_get_uint64(val)
}

func GetHugeint(val DuckDBValue) Hugeint {
	return duckdb_get_hugeint(val)
}

func GetUhugeint(val DuckDBValue) Uhugeint {
	return duckdb_get_uhugeint(val)
}

func GetDecimal(val DuckDBValue) Decimal {
	return duckdb_get_decimal(val)
}

func GetFloat(val DuckDBValue) float32 {
	return duckdb_get_float(val)
}

func GetDouble(val DuckDBValue) float64 {
	return duckdb_get_double(val)
}

func GetDate(val DuckDBValue) Date {
	return duckdb_get_date(val)
}

func GetTime(val DuckDBValue) Time {
	return duckdb_get_time(val)
}

func GetTimeTZ(val DuckDBValue) TimeTZ {
	return duckdb_get_time_tz(val)
}

func GetTimestamp(val DuckDBValue) Timestamp {
	return duckdb_get_timestamp(val)
}

func GetTimestampTZ(val DuckDBValue) Timestamp {
	return duckdb_get_timestamp_tz(val)
}

func GetTimestampS(val DuckDBValue) TimestampS {
	return duckdb_get_timestamp_s(val)
}

func GetTimestampMS(val DuckDBValue) TimestampMS {
	return duckdb_get_timestamp_ms(val)
}

func GetTimestampNS(val DuckDBValue) TimestampNS {
	return duckdb_get_timestamp_ns(val)
}

func GetInterval(val DuckDBValue) Interval {
	return duckdb_get_interval(val)
}

func GetValueType(val DuckDBValue) LogicalType {
	return duckdb_get_value_type(val)
}

func GetBlobValue(val DuckDBValue) Blob {
	return duckdb_get_blob(val)
}

func GetUUID(val DuckDBValue) Uhugeint {
	return duckdb_get_uuid(val)
}

func GetVarchar(val DuckDBValue) string {
	return ownedString(duckdb_get_varchar(val))
}

func GetMapSize(val DuckDBValue) uint64 {
	return duckdb_get_map_size(val)
}

func GetMapKey(val DuckDBValue, index uint64) DuckDBValue {
	return duckdb_get_map_key(val, index)
}

func GetMapValue(val DuckDBValue, index uint64) DuckDBValue {
	return duckdb_get_map_value(val, index)
}

func IsNullValue(val DuckDBValue) bool {
	return duckdb_is_null_value(val)
}

func GetListSize(val DuckDBValue) uint64 {
	return duckdb_get_list_size(val)
}

func GetListChild(val DuckDBValue, index uint64) DuckDBValue {
	return duckdb_get_list_child(val, index)
}

func GetEnumValue(val DuckDBValue) uint64 {
	return duckdb_get_enum_value(val)
}

func GetStructChild(val DuckDBValue, index uint64) DuckDBValue {
	return duckdb_get_struct_child(val, index)
}

func ValueToString(val DuckDBValue) string {
	return ownedString(duckdb_value_to_string(val))
}
