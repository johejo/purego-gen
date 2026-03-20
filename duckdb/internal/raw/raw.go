//go:generate ../../../scripts/uv-run-python-src.sh -m purego_gen gen --config ./config.json --out ./generated.go

package raw

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
	Database          = purego_type_duckdb_database
	Connection        = purego_type_duckdb_connection
	PreparedStatement = purego_type_duckdb_prepared_statement
	Config            = purego_type_duckdb_config
	DataChunk         = purego_type_duckdb_data_chunk
	Vector            = purego_type_duckdb_vector
	LogicalType       = purego_type_duckdb_logical_type
	Result            = purego_type_duckdb_result
	Timestamp         = purego_type_duckdb_timestamp
	Date              = purego_type_duckdb_date
	Time              = purego_type_duckdb_time
	DateStruct        = purego_type_duckdb_date_struct
	TimeStruct        = purego_type_duckdb_time_struct
	TimestampStruct   = purego_type_duckdb_timestamp_struct
	Interval          = purego_type_duckdb_interval
	Hugeint           = purego_type_duckdb_hugeint
	Blob              = purego_type_duckdb_blob
	DuckDBString      = purego_type_duckdb_string
	Decimal           = purego_type_duckdb_decimal
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
		if err := purego_duckdb_register_functions(handle); err != nil {
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

// Lifecycle

func Open(path string, db *Database) int32 {
	return purego_func_duckdb_open(path, uintptr(unsafe.Pointer(db)))
}

func OpenExt(path string, db *Database, config Config, outError *uintptr) int32 {
	return purego_func_duckdb_open_ext(path, uintptr(unsafe.Pointer(db)), config, uintptr(unsafe.Pointer(outError)))
}

func Close(db *Database) {
	purego_func_duckdb_close(uintptr(unsafe.Pointer(db)))
}

func Connect(db Database, conn *Connection) int32 {
	return purego_func_duckdb_connect(db, uintptr(unsafe.Pointer(conn)))
}

func Disconnect(conn *Connection) {
	purego_func_duckdb_disconnect(uintptr(unsafe.Pointer(conn)))
}

func Interrupt(conn Connection) {
	purego_func_duckdb_interrupt(conn)
}

func LibraryVersion() string {
	return purego_func_duckdb_library_version()
}

// Config

func CreateConfig(config *Config) int32 {
	return purego_func_duckdb_create_config(uintptr(unsafe.Pointer(config)))
}

func SetConfig(config Config, name string, option string) int32 {
	return purego_func_duckdb_set_config(config, name, option)
}

func DestroyConfig(config *Config) {
	purego_func_duckdb_destroy_config(uintptr(unsafe.Pointer(config)))
}

// Query

func Query(conn Connection, query string, result *Result) int32 {
	return purego_func_duckdb_query(conn, query, uintptr(unsafe.Pointer(result)))
}

func DestroyResult(result *Result) {
	purego_func_duckdb_destroy_result(uintptr(unsafe.Pointer(result)))
}

func ResultError(result *Result) string {
	return purego_func_duckdb_result_error(uintptr(unsafe.Pointer(result)))
}

func ResultReturnType(result Result) int32 {
	return purego_func_duckdb_result_return_type(result)
}

func RowsChanged(result *Result) uint64 {
	return purego_func_duckdb_rows_changed(uintptr(unsafe.Pointer(result)))
}

func ColumnCount(result *Result) uint64 {
	return purego_func_duckdb_column_count(uintptr(unsafe.Pointer(result)))
}

func ColumnName(result *Result, col uint64) string {
	return purego_func_duckdb_column_name(uintptr(unsafe.Pointer(result)), col)
}

func ColumnType(result *Result, col uint64) int32 {
	return purego_func_duckdb_column_type(uintptr(unsafe.Pointer(result)), col)
}

func ColumnLogicalType(result *Result, col uint64) LogicalType {
	return purego_func_duckdb_column_logical_type(uintptr(unsafe.Pointer(result)), col)
}

// Prepared Statements

func Prepare(conn Connection, query string, stmt *PreparedStatement) int32 {
	return purego_func_duckdb_prepare(conn, query, uintptr(unsafe.Pointer(stmt)))
}

func DestroyPrepare(stmt *PreparedStatement) {
	purego_func_duckdb_destroy_prepare(uintptr(unsafe.Pointer(stmt)))
}

func PrepareError(stmt PreparedStatement) string {
	return purego_func_duckdb_prepare_error(stmt)
}

func Nparams(stmt PreparedStatement) uint64 {
	return purego_func_duckdb_nparams(stmt)
}

func ParameterName(stmt PreparedStatement, index uint64) string {
	return purego_func_duckdb_parameter_name(stmt, index)
}

func BindParameterIndex(stmt PreparedStatement, name string) (uint64, int32) {
	var idx uint64
	state := purego_func_duckdb_bind_parameter_index(stmt, uintptr(unsafe.Pointer(&idx)), name)
	return idx, state
}

func ClearBindings(stmt PreparedStatement) int32 {
	return purego_func_duckdb_clear_bindings(stmt)
}

func ExecutePrepared(stmt PreparedStatement, result *Result) int32 {
	return purego_func_duckdb_execute_prepared(stmt, uintptr(unsafe.Pointer(result)))
}

func PreparedStatementType(stmt PreparedStatement) int32 {
	return purego_func_duckdb_prepared_statement_type(stmt)
}

// Binding

func BindBoolean(stmt PreparedStatement, idx uint64, val bool) int32 {
	return purego_func_duckdb_bind_boolean(stmt, idx, val)
}

func BindInt32(stmt PreparedStatement, idx uint64, val int32) int32 {
	return purego_func_duckdb_bind_int32(stmt, idx, val)
}

func BindInt64(stmt PreparedStatement, idx uint64, val int64) int32 {
	return purego_func_duckdb_bind_int64(stmt, idx, val)
}

func BindFloat(stmt PreparedStatement, idx uint64, val float32) int32 {
	return purego_func_duckdb_bind_float(stmt, idx, val)
}

func BindDouble(stmt PreparedStatement, idx uint64, val float64) int32 {
	return purego_func_duckdb_bind_double(stmt, idx, val)
}

func BindVarchar(stmt PreparedStatement, idx uint64, val string) int32 {
	return purego_func_duckdb_bind_varchar(stmt, idx, val)
}

func BindVarcharLength(stmt PreparedStatement, idx uint64, val string, length uint64) int32 {
	return purego_func_duckdb_bind_varchar_length(stmt, idx, val, length)
}

func BindBlob(stmt PreparedStatement, idx uint64, data []byte) int32 {
	ptr := uintptr(0)
	if len(data) > 0 {
		ptr = uintptr(unsafe.Pointer(&data[0]))
	}
	return purego_func_duckdb_bind_blob(stmt, idx, ptr, uint64(len(data)))
}

func BindNull(stmt PreparedStatement, idx uint64) int32 {
	return purego_func_duckdb_bind_null(stmt, idx)
}

func BindTimestamp(stmt PreparedStatement, idx uint64, val Timestamp) int32 {
	return purego_func_duckdb_bind_timestamp(stmt, idx, val)
}

// Data Chunk / Vector API

func FetchChunk(result Result) DataChunk {
	return purego_func_duckdb_fetch_chunk(result)
}

func DestroyDataChunk(chunk *DataChunk) {
	purego_func_duckdb_destroy_data_chunk(uintptr(unsafe.Pointer(chunk)))
}

func DataChunkGetSize(chunk DataChunk) uint64 {
	return purego_func_duckdb_data_chunk_get_size(chunk)
}

func DataChunkGetColumnCount(chunk DataChunk) uint64 {
	return purego_func_duckdb_data_chunk_get_column_count(chunk)
}

func DataChunkGetVector(chunk DataChunk, colIdx uint64) Vector {
	return purego_func_duckdb_data_chunk_get_vector(chunk, colIdx)
}

func VectorGetColumnType(vector Vector) LogicalType {
	return purego_func_duckdb_vector_get_column_type(vector)
}

func VectorGetData(vector Vector) uintptr {
	return purego_func_duckdb_vector_get_data(vector)
}

func VectorGetValidity(vector Vector) uintptr {
	return purego_func_duckdb_vector_get_validity(vector)
}

func ValidityRowIsValid(validity uintptr, row uint64) bool {
	return purego_func_duckdb_validity_row_is_valid(validity, row)
}

func VectorSize() uint64 {
	return purego_func_duckdb_vector_size()
}

// Logical Type

func GetTypeId(logicalType LogicalType) int32 {
	return purego_func_duckdb_get_type_id(logicalType)
}

func DecimalWidth(logicalType LogicalType) uint8 {
	return purego_func_duckdb_decimal_width(logicalType)
}

func DecimalScale(logicalType LogicalType) uint8 {
	return purego_func_duckdb_decimal_scale(logicalType)
}

func DestroyLogicalType(logicalType *LogicalType) {
	purego_func_duckdb_destroy_logical_type(uintptr(unsafe.Pointer(logicalType)))
}

// Memory

func Free(ptr uintptr) {
	purego_func_duckdb_free(ptr)
}

func Malloc(size uint64) uintptr {
	return purego_func_duckdb_malloc(size)
}

// Date/Time conversion

func FromDate(date Date) DateStruct {
	return purego_func_duckdb_from_date(date)
}

func FromTime(t Time) TimeStruct {
	return purego_func_duckdb_from_time(t)
}

func FromTimestamp(ts Timestamp) TimestampStruct {
	return purego_func_duckdb_from_timestamp(ts)
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

// DateStructFields extracts year, month, day from a DateStruct.
// The generated struct has unexported fields, so we use unsafe access.
func DateStructFields(d *DateStruct) (year int32, month int8, day int8) {
	p := unsafe.Pointer(d)
	year = *(*int32)(p)
	month = *(*int8)(unsafe.Add(p, 4))
	day = *(*int8)(unsafe.Add(p, 5))
	return
}

// TimeStructFields extracts hour, min, sec, micros from a TimeStruct.
func TimeStructFields(t *TimeStruct) (hour, min, sec int8, micros int32) {
	p := unsafe.Pointer(t)
	hour = *(*int8)(p)
	min = *(*int8)(unsafe.Add(p, 1))
	sec = *(*int8)(unsafe.Add(p, 2))
	micros = *(*int32)(unsafe.Add(p, 4))
	return
}
