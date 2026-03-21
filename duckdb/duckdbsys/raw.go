//go:generate ../../scripts/uv-run-python-src.sh -m purego_gen gen --config ./config.json --out ./generated.go

package duckdbsys

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
	Database          = duckdb_database
	Connection        = duckdb_connection
	PreparedStatement = duckdb_prepared_statement
	Config            = duckdb_config
	DataChunk         = duckdb_data_chunk
	Vector            = duckdb_vector
	LogicalType       = duckdb_logical_type
	Result            = duckdb_result
	Timestamp         = duckdb_timestamp
	TimestampS        = duckdb_timestamp_s
	TimestampMS       = duckdb_timestamp_ms
	TimestampNS       = duckdb_timestamp_ns
	Date              = duckdb_date
	Time              = duckdb_time
	DateStruct        = duckdb_date_struct
	TimeStruct        = duckdb_time_struct
	TimestampStruct   = duckdb_timestamp_struct
	Interval          = duckdb_interval
	Hugeint           = duckdb_hugeint
	Uhugeint          = duckdb_uhugeint
	Blob              = duckdb_blob
	DuckDBString      = duckdb_string
	Decimal           = duckdb_decimal
	ListEntry         = duckdb_list_entry
	TimeTZ            = duckdb_time_tz
	TimeTZStruct      = duckdb_time_tz_struct
	QueryProgressType = duckdb_query_progress_type
	Appender          = duckdb_appender
	PendingResult     = duckdb_pending_result
	DuckDBValue       = duckdb_value
	ExtractedStmts    = duckdb_extracted_statements
	ProfilingInfo     = duckdb_profiling_info
	TableDescription  = duckdb_table_description
)

var (
	loadOnce sync.Once
	loadErr  error
)

// Load resolves libduckdb and registers all required symbols once per process.
func Load() error {
	loadOnce.Do(func() {
		handle, err := openLibrary()
		if err != nil {
			loadErr = err
			return
		}
		if err := duckdb_register_functions(handle); err != nil {
			loadErr = err
			return
		}
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
	return 0, fmt.Errorf("open libduckdb: %v", errs)
}

func libraryCandidates() []string {
	var candidates []string

	if envPath := os.Getenv("PUREGO_GEN_TEST_LIBDUCKDB_PATH"); envPath != "" {
		candidates = append(candidates, envPath)
	}
	if envDir := os.Getenv("PUREGO_GEN_TEST_LIBDUCKDB_LIB_DIR"); envDir != "" {
		candidates = append(candidates, sharedLibraryCandidates(envDir, "duckdb")...)
	}

	switch runtime.GOOS {
	case "darwin":
		candidates = append(candidates, "libduckdb.dylib")
	default:
		candidates = append(candidates, "libduckdb.so", "libduckdb.so.0")
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

// ownedString converts a char* uintptr (freed with duckdb_free) to a Go string.
func ownedString(ptr uintptr) string {
	s := gostring(ptr)
	if ptr != 0 {
		duckdb_free(ptr)
	}
	return s
}

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

// Logical Type

func CreateLogicalType(typeID int32) LogicalType {
	return duckdb_create_logical_type(typeID)
}

func LogicalTypeGetAlias(logicalType LogicalType) string {
	return ownedString(duckdb_logical_type_get_alias(logicalType))
}

func LogicalTypeSetAlias(logicalType LogicalType, alias string) {
	duckdb_logical_type_set_alias(logicalType, alias)
}

func CreateListType(childType LogicalType) LogicalType {
	return duckdb_create_list_type(childType)
}

func CreateArrayType(childType LogicalType, size uint64) LogicalType {
	return duckdb_create_array_type(childType, size)
}

func CreateMapType(keyType LogicalType, valueType LogicalType) LogicalType {
	return duckdb_create_map_type(keyType, valueType)
}

func CreateUnionType(memberTypes *LogicalType, memberNames uintptr, memberCount uint64) LogicalType {
	return duckdb_create_union_type(memberTypes, memberNames, memberCount)
}

func CreateStructType(memberTypes *LogicalType, memberNames uintptr, memberCount uint64) LogicalType {
	return duckdb_create_struct_type(memberTypes, memberNames, memberCount)
}

func CreateEnumType(memberNames uintptr, memberCount uint64) LogicalType {
	return duckdb_create_enum_type(memberNames, memberCount)
}

func CreateDecimalType(width uint8, scale uint8) LogicalType {
	return duckdb_create_decimal_type(width, scale)
}

func GetTypeId(logicalType LogicalType) int32 {
	return duckdb_get_type_id(logicalType)
}

func DecimalWidth(logicalType LogicalType) uint8 {
	return duckdb_decimal_width(logicalType)
}

func DecimalScale(logicalType LogicalType) uint8 {
	return duckdb_decimal_scale(logicalType)
}

func DecimalInternalType(logicalType LogicalType) int32 {
	return duckdb_decimal_internal_type(logicalType)
}

func EnumInternalType(logicalType LogicalType) int32 {
	return duckdb_enum_internal_type(logicalType)
}

func EnumDictionarySize(logicalType LogicalType) uint32 {
	return duckdb_enum_dictionary_size(logicalType)
}

func EnumDictionaryValue(logicalType LogicalType, index uint64) string {
	return ownedString(duckdb_enum_dictionary_value(logicalType, index))
}

func ListTypeChildType(logicalType LogicalType) LogicalType {
	return duckdb_list_type_child_type(logicalType)
}

func ArrayTypeChildType(logicalType LogicalType) LogicalType {
	return duckdb_array_type_child_type(logicalType)
}

func ArrayTypeArraySize(logicalType LogicalType) uint64 {
	return duckdb_array_type_array_size(logicalType)
}

func MapTypeKeyType(logicalType LogicalType) LogicalType {
	return duckdb_map_type_key_type(logicalType)
}

func MapTypeValueType(logicalType LogicalType) LogicalType {
	return duckdb_map_type_value_type(logicalType)
}

func StructTypeChildCount(logicalType LogicalType) uint64 {
	return duckdb_struct_type_child_count(logicalType)
}

func StructTypeChildName(logicalType LogicalType, index uint64) string {
	return ownedString(duckdb_struct_type_child_name(logicalType, index))
}

func StructTypeChildType(logicalType LogicalType, index uint64) LogicalType {
	return duckdb_struct_type_child_type(logicalType, index)
}

func UnionTypeMemberCount(logicalType LogicalType) uint64 {
	return duckdb_union_type_member_count(logicalType)
}

func UnionTypeMemberName(logicalType LogicalType, index uint64) string {
	return ownedString(duckdb_union_type_member_name(logicalType, index))
}

func UnionTypeMemberType(logicalType LogicalType, index uint64) LogicalType {
	return duckdb_union_type_member_type(logicalType, index)
}

func DestroyLogicalType(logicalType *LogicalType) {
	duckdb_destroy_logical_type(logicalType)
}

// Data Chunk / Vector API

func CreateDataChunk(types *LogicalType, columnCount uint64) DataChunk {
	return duckdb_create_data_chunk(types, columnCount)
}

func DestroyDataChunk(chunk *DataChunk) {
	duckdb_destroy_data_chunk(chunk)
}

func DataChunkReset(chunk DataChunk) {
	duckdb_data_chunk_reset(chunk)
}

func DataChunkGetSize(chunk DataChunk) uint64 {
	return duckdb_data_chunk_get_size(chunk)
}

func DataChunkSetSize(chunk DataChunk, size uint64) {
	duckdb_data_chunk_set_size(chunk, size)
}

func DataChunkGetColumnCount(chunk DataChunk) uint64 {
	return duckdb_data_chunk_get_column_count(chunk)
}

func DataChunkGetVector(chunk DataChunk, colIdx uint64) Vector {
	return duckdb_data_chunk_get_vector(chunk, colIdx)
}

func VectorGetColumnType(vector Vector) LogicalType {
	return duckdb_vector_get_column_type(vector)
}

func VectorGetData(vector Vector) uintptr {
	return duckdb_vector_get_data(vector)
}

func VectorGetValidity(vector Vector) *uint64 {
	return duckdb_vector_get_validity(vector)
}

func VectorEnsureValidityWritable(vector Vector) {
	duckdb_vector_ensure_validity_writable(vector)
}

func VectorAssignStringElement(vector Vector, index uint64, str string) {
	duckdb_vector_assign_string_element(vector, index, str)
}

func VectorAssignStringElementLen(vector Vector, index uint64, str string, strLen uint64) {
	duckdb_vector_assign_string_element_len(vector, index, str, strLen)
}

func ListVectorGetChild(vector Vector) Vector {
	return duckdb_list_vector_get_child(vector)
}

func ListVectorGetSize(vector Vector) uint64 {
	return duckdb_list_vector_get_size(vector)
}

func ListVectorSetSize(vector Vector, size uint64) int32 {
	return duckdb_list_vector_set_size(vector, size)
}

func ListVectorReserve(vector Vector, requiredCapacity uint64) int32 {
	return duckdb_list_vector_reserve(vector, requiredCapacity)
}

func StructVectorGetChild(vector Vector, index uint64) Vector {
	return duckdb_struct_vector_get_child(vector, index)
}

func ArrayVectorGetChild(vector Vector) Vector {
	return duckdb_array_vector_get_child(vector)
}

func ValidityRowIsValid(validity *uint64, row uint64) bool {
	return duckdb_validity_row_is_valid(validity, row)
}

func ValiditySetRowValidity(validity *uint64, row uint64, valid bool) {
	duckdb_validity_set_row_validity(validity, row, valid)
}

func ValiditySetRowInvalid(validity *uint64, row uint64) {
	duckdb_validity_set_row_invalid(validity, row)
}

func ValiditySetRowValid(validity *uint64, row uint64) {
	duckdb_validity_set_row_valid(validity, row)
}

func VectorSize() uint64 {
	return duckdb_vector_size()
}

// Memory

func Free(ptr uintptr) {
	duckdb_free(ptr)
}

func Malloc(size uint64) uintptr {
	return duckdb_malloc(size)
}

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

// String helpers for duckdb_string_t in vectors.
// duckdb_string_t is a 16-byte union: if length <= 12, the string is inlined;
// otherwise bytes 4..8 contain a pointer to the string data.
// purego-gen cannot generate this type (union), so we handle it manually.

const duckdbStringInlineLimit = 12

// ReadStringFromVector reads a duckdb_string_t value at the given pointer offset.
func ReadStringFromVector(base uintptr, row uint64) string {
	// #nosec G103 -- required for reading vector data from C memory
	ptr := unsafe.Add(unsafe.Pointer(nil), base+uintptr(row)*16)
	length := *(*uint32)(ptr)
	if length <= duckdbStringInlineLimit {
		data := unsafe.Slice((*byte)(unsafe.Add(ptr, 4)), int(length))
		return string(data)
	}
	strPtr := *(*uintptr)(unsafe.Add(ptr, 8))
	data := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), strPtr)), int(length))
	return string(data)
}

// ReadBlobFromVector reads a duckdb_string_t value as bytes at the given pointer offset.
func ReadBlobFromVector(base uintptr, row uint64) []byte {
	// #nosec G103 -- required for reading vector data from C memory
	ptr := unsafe.Add(unsafe.Pointer(nil), base+uintptr(row)*16)
	length := *(*uint32)(ptr)
	if length <= duckdbStringInlineLimit {
		src := unsafe.Slice((*byte)(unsafe.Add(ptr, 4)), int(length))
		dst := make([]byte, len(src))
		copy(dst, src)
		return dst
	}
	strPtr := *(*uintptr)(unsafe.Add(ptr, 8))
	src := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), strPtr)), int(length))
	dst := make([]byte, len(src))
	copy(dst, src)
	return dst
}
