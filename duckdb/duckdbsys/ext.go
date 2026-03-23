package duckdbsys

import "unsafe"

// Date/Time conversion

func FromDate(date Date) DateStruct {
	return duckdb_from_date(date)
}

func ToDate(date DateStruct) Date {
	return duckdb_to_date(date)
}

func IsFiniteDate(date Date) bool {
	return duckdb_is_finite_date(date)
}

func FromTime(t Time) TimeStruct {
	return duckdb_from_time(t)
}

func ToTime(t TimeStruct) Time {
	return duckdb_to_time(t)
}

func CreateTimeTZ(micros int64, offset int32) TimeTZ {
	return duckdb_create_time_tz(micros, offset)
}

func FromTimeTZ(t TimeTZ) TimeTZStruct {
	return duckdb_from_time_tz(t)
}

func FromTimestamp(ts Timestamp) TimestampStruct {
	return duckdb_from_timestamp(ts)
}

func ToTimestamp(ts TimestampStruct) Timestamp {
	return duckdb_to_timestamp(ts)
}

func IsFiniteTimestamp(ts Timestamp) bool {
	return duckdb_is_finite_timestamp(ts)
}

func HugeintToDouble(val Hugeint) float64 {
	return duckdb_hugeint_to_double(val)
}

func DoubleToHugeint(val float64) Hugeint {
	return duckdb_double_to_hugeint(val)
}

func UhugeintToDouble(val Uhugeint) float64 {
	return duckdb_uhugeint_to_double(val)
}

func DoubleToUhugeint(val float64) Uhugeint {
	return duckdb_double_to_uhugeint(val)
}

func DoubleToDecimal(val float64, width uint8, scale uint8) Decimal {
	return duckdb_double_to_decimal(val, width, scale)
}

func DecimalToDouble(val Decimal) float64 {
	return duckdb_decimal_to_double(val)
}

// Appender

func AppenderCreate(conn Connection, schema string, table string, appender *Appender) int32 {
	return duckdb_appender_create(conn, schema, table, appender)
}

func AppenderColumnCount(appender Appender) uint64 {
	return duckdb_appender_column_count(appender)
}

func AppenderColumnType(appender Appender, colIndex uint64) LogicalType {
	return duckdb_appender_column_type(appender, colIndex)
}

func AppenderError(appender Appender) string {
	return duckdb_appender_error(appender)
}

func AppenderFlush(appender Appender) int32 {
	return duckdb_appender_flush(appender)
}

func AppenderClose(appender Appender) int32 {
	return duckdb_appender_close(appender)
}

func AppenderDestroy(appender *Appender) int32 {
	return duckdb_appender_destroy(appender)
}

func AppenderBeginRow(appender Appender) int32 {
	return duckdb_appender_begin_row(appender)
}

func AppenderEndRow(appender Appender) int32 {
	return duckdb_appender_end_row(appender)
}

func AppendDefault(appender Appender) int32 {
	return duckdb_append_default(appender)
}

func AppendBool(appender Appender, val bool) int32 {
	return duckdb_append_bool(appender, val)
}

func AppendInt8(appender Appender, val int8) int32 {
	return duckdb_append_int8(appender, val)
}

func AppendInt16(appender Appender, val int16) int32 {
	return duckdb_append_int16(appender, val)
}

func AppendInt32(appender Appender, val int32) int32 {
	return duckdb_append_int32(appender, val)
}

func AppendInt64(appender Appender, val int64) int32 {
	return duckdb_append_int64(appender, val)
}

func AppendHugeint(appender Appender, val Hugeint) int32 {
	return duckdb_append_hugeint(appender, val)
}

func AppendUint8(appender Appender, val uint8) int32 {
	return duckdb_append_uint8(appender, val)
}

func AppendUint16(appender Appender, val uint16) int32 {
	return duckdb_append_uint16(appender, val)
}

func AppendUint32(appender Appender, val uint32) int32 {
	return duckdb_append_uint32(appender, val)
}

func AppendUint64(appender Appender, val uint64) int32 {
	return duckdb_append_uint64(appender, val)
}

func AppendUhugeint(appender Appender, val Uhugeint) int32 {
	return duckdb_append_uhugeint(appender, val)
}

func AppendFloat(appender Appender, val float32) int32 {
	return duckdb_append_float(appender, val)
}

func AppendDouble(appender Appender, val float64) int32 {
	return duckdb_append_double(appender, val)
}

func AppendDate(appender Appender, val Date) int32 {
	return duckdb_append_date(appender, val)
}

func AppendTime(appender Appender, val Time) int32 {
	return duckdb_append_time(appender, val)
}

func AppendTimestamp(appender Appender, val Timestamp) int32 {
	return duckdb_append_timestamp(appender, val)
}

func AppendInterval(appender Appender, val Interval) int32 {
	return duckdb_append_interval(appender, val)
}

func AppendVarchar(appender Appender, val string) int32 {
	return duckdb_append_varchar(appender, val)
}

func AppendVarcharLength(appender Appender, val string, length uint64) int32 {
	return duckdb_append_varchar_length(appender, val, length)
}

func AppendBlob(appender Appender, data []byte) int32 {
	ptr := uintptr(0)
	if len(data) > 0 {
		ptr = uintptr(unsafe.Pointer(&data[0]))
	}
	return duckdb_append_blob(appender, ptr, uint64(len(data)))
}

func AppendNull(appender Appender) int32 {
	return duckdb_append_null(appender)
}

func AppendValue(appender Appender, val DuckDBValue) int32 {
	return duckdb_append_value(appender, val)
}

func AppendDataChunk(appender Appender, chunk DataChunk) int32 {
	return duckdb_append_data_chunk(appender, chunk)
}

// Table Description

func TableDescriptionCreate(conn Connection, schema string, table string, desc *TableDescription) int32 {
	return duckdb_table_description_create(conn, schema, table, desc)
}

func TableDescriptionDestroy(desc *TableDescription) {
	duckdb_table_description_destroy(desc)
}

func TableDescriptionError(desc TableDescription) string {
	return duckdb_table_description_error(desc)
}

func TableDescriptionGetColumnCount(desc TableDescription) uint64 {
	return duckdb_table_description_get_column_count(desc)
}

func TableDescriptionGetColumnName(desc TableDescription, index uint64) string {
	return ownedString(duckdb_table_description_get_column_name(desc, index))
}

func TableDescriptionGetColumnType(desc TableDescription, index uint64) LogicalType {
	return duckdb_table_description_get_column_type(desc, index)
}

func ColumnHasDefault(desc TableDescription, colIndex uint64, hasDefault *bool) int32 {
	return duckdb_column_has_default(desc, colIndex, hasDefault)
}

// Profiling

func GetProfilingInfo(conn Connection) ProfilingInfo {
	return duckdb_get_profiling_info(conn)
}

func ProfilingInfoGetValue(info ProfilingInfo, key string) DuckDBValue {
	return duckdb_profiling_info_get_value(info, key)
}

func ProfilingInfoGetMetrics(info ProfilingInfo) DuckDBValue {
	return duckdb_profiling_info_get_metrics(info)
}

func ProfilingInfoGetChildCount(info ProfilingInfo) uint64 {
	return duckdb_profiling_info_get_child_count(info)
}

func ProfilingInfoGetChild(info ProfilingInfo, index uint64) ProfilingInfo {
	return duckdb_profiling_info_get_child(info, index)
}

// Streaming

func StreamFetchChunk(result Result) DataChunk {
	return duckdb_stream_fetch_chunk(result)
}

func FetchChunk(result Result) DataChunk {
	return duckdb_fetch_chunk(result)
}

// Query Progress

func QueryProgress(conn Connection) QueryProgressType {
	return duckdb_query_progress(conn)
}

// Table Names

func GetTableNames(conn Connection, query string, parseOnly bool) DuckDBValue {
	return duckdb_get_table_names(conn, query, parseOnly)
}
