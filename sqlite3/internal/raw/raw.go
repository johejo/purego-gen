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
	DB             = purego_type_sqlite3
	Stmt           = purego_type_sqlite3_stmt
	Value          = purego_type_sqlite3_value
	Context        = purego_type_sqlite3_context
	Int64          = purego_type_sqlite3_int64
	DestructorType = purego_type_sqlite3_destructor_type
)

var (
	loadOnce sync.Once
	loadErr  error
	openV2Fn func(filename string, ppDB uintptr, flags int32, zVfs uintptr) int32
)

// Load resolves libsqlite3 and registers all required symbols once per process.
func Load() error {
	loadOnce.Do(func() {
		handle, err := openLibrary()
		if err != nil {
			loadErr = err
			return
		}
		if err := purego_sqlite3_register_functions(handle); err != nil {
			loadErr = err
			return
		}
		purego.RegisterLibFunc(&openV2Fn, handle, "sqlite3_open_v2")
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

func OpenV2(filename string, flags int32, vfs string, db *DB) int32 {
	if vfs != "" {
		return purego_func_sqlite3_open_v2(filename, uintptr(unsafe.Pointer(db)), flags, vfs)
	}
	return openV2Fn(filename, uintptr(unsafe.Pointer(db)), flags, 0)
}

func CloseV2(db DB) int32               { return purego_func_sqlite3_close_v2(db) }
func Errmsg(db DB) string               { return purego_func_sqlite3_errmsg(db) }
func ExtendedErrcode(db DB) int32       { return purego_func_sqlite3_extended_errcode(db) }
func BusyTimeout(db DB, ms int32) int32 { return purego_func_sqlite3_busy_timeout(db, ms) }

func PrepareV2(db DB, sql string, stmt *Stmt) int32 {
	return purego_func_sqlite3_prepare_v2(db, sql, -1, uintptr(unsafe.Pointer(stmt)), 0)
}

func Finalize(stmt Stmt) int32      { return purego_func_sqlite3_finalize(stmt) }
func Reset(stmt Stmt) int32         { return purego_func_sqlite3_reset(stmt) }
func ClearBindings(stmt Stmt) int32 { return purego_func_sqlite3_clear_bindings(stmt) }
func Step(stmt Stmt) int32          { return purego_func_sqlite3_step(stmt) }
func Interrupt(db DB)               { purego_func_sqlite3_interrupt(db) }

func BindParameterCount(stmt Stmt) int32 { return purego_func_sqlite3_bind_parameter_count(stmt) }
func BindParameterIndex(stmt Stmt, name string) int32 {
	return purego_func_sqlite3_bind_parameter_index(stmt, name)
}
func BindParameterName(stmt Stmt, index int32) string {
	return purego_func_sqlite3_bind_parameter_name(stmt, index)
}
func BindNull(stmt Stmt, index int32) int32 { return purego_func_sqlite3_bind_null(stmt, index) }
func BindBlobBytes(stmt Stmt, index int32, value []byte, destructor DestructorType) int32 {
	return purego_func_sqlite3_bind_blob_bytes(stmt, index, value, destructor)
}
func BindDouble(stmt Stmt, index int32, value float64) int32 {
	return purego_func_sqlite3_bind_double(stmt, index, value)
}
func BindInt64(stmt Stmt, index int32, value int64) int32 {
	return purego_func_sqlite3_bind_int64(stmt, index, value)
}
func BindText(stmt Stmt, index int32, value string, destructor DestructorType) int32 {
	return purego_func_sqlite3_bind_text(stmt, index, value, -1, destructor)
}

func ColumnCount(stmt Stmt) int32 { return purego_func_sqlite3_column_count(stmt) }
func ColumnType(stmt Stmt, index int32) int32 {
	return purego_func_sqlite3_column_type(stmt, index)
}
func ColumnBytes(stmt Stmt, index int32) int32 {
	return purego_func_sqlite3_column_bytes(stmt, index)
}
func ColumnInt64(stmt Stmt, index int32) int64 {
	return purego_func_sqlite3_column_int64(stmt, index)
}
func ColumnDouble(stmt Stmt, index int32) float64 {
	return purego_func_sqlite3_column_double(stmt, index)
}
func ColumnText(stmt Stmt, index int32) string { return purego_func_sqlite3_column_text(stmt, index) }
func ColumnName(stmt Stmt, index int32) string { return purego_func_sqlite3_column_name(stmt, index) }
func ColumnDeclType(stmt Stmt, index int32) string {
	return purego_func_sqlite3_column_decltype(stmt, index)
}
func ColumnBlobBytes(stmt Stmt, index int32) []byte {
	ptr := purego_func_sqlite3_column_blob(stmt, index)
	length := purego_func_sqlite3_column_bytes(stmt, index)
	return copyBytes(ptr, length)
}

func Changes64(db DB) int64        { return purego_func_sqlite3_changes64(db) }
func LastInsertRowid(db DB) int64  { return purego_func_sqlite3_last_insert_rowid(db) }
func UserData(ctx Context) uintptr { return purego_func_sqlite3_user_data(ctx) }

func CreateFunctionV2Callbacks(
	db DB,
	name string,
	nArg int32,
	textRep int32,
	app uintptr,
	xFunc func(Context, int32, uintptr),
	xDestroy func(uintptr),
) int32 {
	return purego_func_sqlite3_create_function_v2_callbacks(
		db,
		name,
		nArg,
		textRep,
		app,
		xFunc,
		0,
		0,
		xDestroy,
	)
}

func CreateCollationV2Callbacks(
	db DB,
	name string,
	textRep int32,
	app uintptr,
	xCompare func(uintptr, int32, uintptr, int32, uintptr) int32,
	xDestroy func(uintptr),
) int32 {
	return purego_func_sqlite3_create_collation_v2_callbacks(
		db,
		name,
		textRep,
		app,
		xCompare,
		xDestroy,
	)
}

func ValueType(value Value) int32     { return purego_func_sqlite3_value_type(value) }
func ValueInt64(value Value) int64    { return purego_func_sqlite3_value_int64(value) }
func ValueDouble(value Value) float64 { return purego_func_sqlite3_value_double(value) }
func ValueText(value Value) string    { return purego_func_sqlite3_value_text(value) }
func ValueBlobBytes(value Value) []byte {
	ptr := purego_func_sqlite3_value_blob(value)
	length := purego_func_sqlite3_value_bytes(value)
	return copyBytes(ptr, length)
}

func ResultNull(ctx Context) { purego_func_sqlite3_result_null(ctx) }
func ResultBlobBytes(ctx Context, value []byte, destructor DestructorType) {
	purego_func_sqlite3_result_blob_bytes(ctx, value, destructor)
}
func ResultDouble(ctx Context, value float64) { purego_func_sqlite3_result_double(ctx, value) }
func ResultInt64(ctx Context, value int64)    { purego_func_sqlite3_result_int64(ctx, value) }
func ResultText(ctx Context, value string, destructor DestructorType) {
	purego_func_sqlite3_result_text(ctx, value, -1, destructor)
}
func ResultError(ctx Context, value string) { purego_func_sqlite3_result_error(ctx, value, -1) }

func copyBytes(ptr uintptr, length int32) []byte {
	if ptr == 0 || length <= 0 {
		return nil
	}
	src := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), ptr)), int(length))
	dst := make([]byte, len(src))
	copy(dst, src)
	return dst
}
