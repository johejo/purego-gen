package fixture

import (
	"fmt"
	"runtime"
	"testing"
	"unicode/utf16"
	"unsafe"

	"github.com/ebitengine/purego"
	"github.com/johejo/purego-gen/tests/testruntime"
)

type sqliteConnection struct {
	handle     uintptr
	db         *sqlite3
	closed     bool
	useCloseV2 bool
}

type sqliteStatement struct {
	db        *sqlite3
	handle    *sqlite3_stmt
	finalized bool
}

func sqliteErrmsg(db *sqlite3) string {
	if db == nil {
		return ""
	}
	return sqlite3_errmsg(db)
}

func openSQLiteConnection(t *testing.T) *sqliteConnection {
	t.Helper()

	libraryPath := testruntime.ResolveLibraryPathFromLibDirEnv(
		t,
		"PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR",
		"sqlite3",
	)

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		t.Fatalf("open library: %v", err)
	}

	connection := &sqliteConnection{handle: handle}
	t.Cleanup(func() {
		if closeErr := connection.close(); closeErr != nil {
			t.Errorf("close sqlite connection: %v", closeErr)
		}
	})

	if err := sqlite3_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if got := sqlite3_libversion(); got == "" {
		t.Fatal("sqlite3_libversion() returned empty string")
	}

	openResult := sqlite3_open(":memory:", &connection.db)
	if openResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_open(:memory:) = %d, want %d, errmsg=%q",
			openResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if connection.db == nil {
		t.Fatal("sqlite3_open returned nil database handle")
	}

	return connection
}

func openSQLiteConnectionV2(
	t *testing.T,
	filename string,
	flags int32,
	vfsName string,
) *sqliteConnection {
	t.Helper()

	libraryPath := testruntime.ResolveLibraryPathFromLibDirEnv(
		t,
		"PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR",
		"sqlite3",
	)

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		t.Fatalf("open library: %v", err)
	}

	connection := &sqliteConnection{handle: handle, useCloseV2: true}
	t.Cleanup(func() {
		if closeErr := connection.close(); closeErr != nil {
			t.Errorf("close sqlite connection: %v", closeErr)
		}
	})

	if err := sqlite3_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if got := sqlite3_libversion(); got == "" {
		t.Fatal("sqlite3_libversion() returned empty string")
	}

	openResult := sqlite3_open_v2(
		filename,
		&connection.db,
		flags,
		vfsName,
	)
	if openResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_open_v2(%q) = %d, want %d, errmsg=%q",
			filename,
			openResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if connection.db == nil {
		t.Fatal("sqlite3_open_v2 returned nil database handle")
	}

	return connection
}

func (connection *sqliteConnection) Close(t *testing.T) {
	t.Helper()

	if err := connection.close(); err != nil {
		t.Fatal(err)
	}
}

func (connection *sqliteConnection) close() error {
	if connection == nil || connection.closed {
		return nil
	}

	if connection.db != nil {
		closeResult := int32(0)
		closeName := "sqlite3_close"
		if connection.useCloseV2 {
			closeResult = sqlite3_close_v2(connection.db)
			closeName = "sqlite3_close_v2"
		} else {
			closeResult = sqlite3_close(connection.db)
		}
		if closeResult != SQLITE_OK {
			return fmt.Errorf(
				"%s() = %d, want %d, errmsg=%q",
				closeName,
				closeResult,
				SQLITE_OK,
				sqliteErrmsg(connection.db),
			)
		}
		connection.db = nil
	}

	if connection.handle != 0 {
		if err := purego.Dlclose(connection.handle); err != nil {
			return fmt.Errorf("close library: %w", err)
		}
		connection.handle = 0
	}

	connection.closed = true
	return nil
}

func prepareSQLiteStatement(
	t *testing.T,
	db *sqlite3,
	sql string,
) *sqliteStatement {
	t.Helper()

	statement := &sqliteStatement{db: db}
	prepareResult := sqlite3_prepare_v2(
		db,
		sql,
		-1,
		&statement.handle,
		0,
	)
	if prepareResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_prepare_v2(%q) = %d, want %d, errmsg=%q",
			sql,
			prepareResult,
			SQLITE_OK,
			sqliteErrmsg(db),
		)
	}
	if statement.handle == nil {
		t.Fatalf("sqlite3_prepare_v2(%q) returned nil statement handle", sql)
	}

	t.Cleanup(func() {
		if finalizeErr := statement.finalize(); finalizeErr != nil {
			t.Errorf("finalize sqlite statement: %v", finalizeErr)
		}
	})

	return statement
}

func (statement *sqliteStatement) Finalize(t *testing.T) {
	t.Helper()

	if err := statement.finalize(); err != nil {
		t.Fatal(err)
	}
}

func (statement *sqliteStatement) finalize() error {
	if statement == nil || statement.finalized || statement.handle == nil {
		return nil
	}

	finalizeResult := sqlite3_finalize(statement.handle)
	if finalizeResult != SQLITE_OK {
		return fmt.Errorf(
			"sqlite3_finalize() = %d, want %d, errmsg=%q",
			finalizeResult,
			SQLITE_OK,
			sqliteErrmsg(statement.db),
		)
	}

	statement.handle = nil
	statement.finalized = true
	return nil
}

func mustExecSQLite(t *testing.T, db *sqlite3, sql string) {
	t.Helper()

	execResult := sqlite3_exec(
		db,
		sql,
		sqlite3_callback(0),
		0,
		0,
	)
	if execResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_exec(%q) = %d, want %d, errmsg=%q",
			sql,
			execResult,
			SQLITE_OK,
			sqliteErrmsg(db),
		)
	}
}

func cString(ptr *byte) string {
	if ptr == nil {
		return ""
	}
	length := 0
	for *(*byte)(unsafe.Add(unsafe.Pointer(ptr), length)) != 0 {
		length++
	}
	return string(unsafe.Slice(ptr, length))
}

func cStringFromUintptr(ptr uintptr) string {
	if ptr == 0 {
		return ""
	}
	pointerData := *(*unsafe.Pointer)(unsafe.Pointer(&ptr))
	return cString((*byte)(pointerData))
}

func cStringArray(values uintptr, count int32) []string {
	if values == 0 || count <= 0 {
		return nil
	}
	pointerData := *(*unsafe.Pointer)(unsafe.Pointer(&values))
	pointers := unsafe.Slice((**byte)(pointerData), int(count))
	result := make([]string, len(pointers))
	for index, pointer := range pointers {
		result[index] = cString(pointer)
	}
	return result
}

func cBytesString(ptr uintptr, length int32) string {
	if ptr == 0 || length <= 0 {
		return ""
	}
	pointerData := *(*unsafe.Pointer)(unsafe.Pointer(&ptr))
	return string(unsafe.Slice((*byte)(pointerData), int(length)))
}

func sqliteUTF16CString(text string) []uint16 {
	encoded := utf16.Encode([]rune(text))
	return append(encoded, 0)
}

func sqliteUTF16CStringPointer(text string) ([]uint16, uintptr) {
	encoded := sqliteUTF16CString(text)
	return encoded, uintptr(unsafe.Pointer(&encoded[0]))
}

func sqliteUTF16BytesString(ptr uintptr, length int32) string {
	if ptr == 0 || length <= 0 {
		return ""
	}
	pointerData := *(*unsafe.Pointer)(unsafe.Pointer(&ptr))
	return string(utf16.Decode(unsafe.Slice((*uint16)(pointerData), int(length)/2)))
}

func sqliteValueArray(values **sqlite3_value, count int32) []*sqlite3_value {
	if values == nil || count <= 0 {
		return nil
	}
	return unsafe.Slice(values, int(count))
}

func sqliteCompareByLengthThenLex(leftText string, rightText string) int32 {
	switch {
	case len(leftText) < len(rightText):
		return -1
	case len(leftText) > len(rightText):
		return 1
	case leftText < rightText:
		return -1
	case leftText > rightText:
		return 1
	default:
		return 0
	}
}

func collectFirstColumnTextRows(
	t *testing.T,
	db *sqlite3,
	statement *sqliteStatement,
) []string {
	t.Helper()

	var rows []string
	for {
		stepResult := sqlite3_step(statement.handle)
		switch stepResult {
		case SQLITE_ROW:
			rows = append(rows, sqlite3_column_text(statement.handle, 0))
		case SQLITE_DONE:
			return rows
		default:
			t.Fatalf(
				"sqlite3_step() = %d, want %d or %d, errmsg=%q",
				stepResult,
				SQLITE_ROW,
				SQLITE_DONE,
				sqliteErrmsg(db),
			)
		}
	}
}

func TestGeneratedBindingsReadTextResultsFromLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	statement := prepareSQLiteStatement(t, connection.db, "SELECT 'hello-from-sqlite'")

	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := sqlite3_column_text(statement.handle, 0); got != "hello-from-sqlite" {
		t.Fatalf("sqlite3_column_text(stmt, 0) = %q, want %q", got, "hello-from-sqlite")
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}
}

func TestGeneratedBindingsExecuteSqliteExecCallbackWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	var callbackValues []string
	var callbackNames []string
	execResult := sqlite3_exec_callbacks(
		connection.db,
		"SELECT 'row-value' AS greeting",
		func(_ uintptr, count int32, values uintptr, names uintptr) int32 {
			callbackValues = cStringArray(values, count)
			callbackNames = cStringArray(names, count)
			return 0
		},
		0,
		0,
	)
	if execResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_exec() = %d, want %d, errmsg=%q",
			execResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if len(callbackValues) != 1 || callbackValues[0] != "row-value" {
		t.Fatalf("sqlite3_exec() callback values = %#v, want %#v", callbackValues, []string{"row-value"})
	}
	if len(callbackNames) != 1 || callbackNames[0] != "greeting" {
		t.Fatalf("sqlite3_exec() callback names = %#v, want %#v", callbackNames, []string{"greeting"})
	}
}

func TestGeneratedBindingsBindTextWithTransientDestructorInLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	statement := prepareSQLiteStatement(t, connection.db, "SELECT ?1")

	bindResult := sqlite3_bind_text(
		statement.handle,
		1,
		"bound-text",
		-1,
		SQLITE_TRANSIENT,
	)
	if bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_text() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := sqlite3_column_text(statement.handle, 0); got != "bound-text" {
		t.Fatalf("sqlite3_column_text(stmt, 0) = %q, want %q", got, "bound-text")
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}
}

func TestGeneratedBindingsOpenV2CloseV2AndBusyTimeoutWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnectionV2(
		t,
		"file:purego-driver-open-v2?mode=memory&cache=private",
		SQLITE_OPEN_READWRITE|
			SQLITE_OPEN_CREATE|
			SQLITE_OPEN_URI|
			SQLITE_OPEN_FULLMUTEX,
		"unix",
	)

	busyTimeoutResult := sqlite3_busy_timeout(connection.db, 25)
	if busyTimeoutResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_busy_timeout() = %d, want %d, errmsg=%q",
			busyTimeoutResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	connection.Close(t)
}

func TestGeneratedBindingsDriverValueBindingsWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	statement := prepareSQLiteStatement(t, connection.db, "SELECT ?1, ?2, ?3, ?4")

	const wantInt64 sqlite3_int64 = 922337203685477000
	const wantDouble = 3.25
	blobValue := []byte("blob-value")

	if bindResult := sqlite3_bind_int64(statement.handle, 1, wantInt64); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_int64() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if bindResult := sqlite3_bind_double(statement.handle, 2, wantDouble); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_double() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if bindResult := sqlite3_bind_blob_bytes(
		statement.handle,
		3,
		blobValue,
		SQLITE_TRANSIENT,
	); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_blob() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if bindResult := sqlite3_bind_null(statement.handle, 4); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_null() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	if got := sqlite3_column_count(statement.handle); got != 4 {
		t.Fatalf("sqlite3_column_count(stmt) = %d, want %d", got, 4)
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}

	if got := sqlite3_column_type(statement.handle, 0); got != SQLITE_INTEGER {
		t.Fatalf("sqlite3_column_type(stmt, 0) = %d, want %d", got, SQLITE_INTEGER)
	}
	if got := sqlite3_column_int64(statement.handle, 0); got != wantInt64 {
		t.Fatalf("sqlite3_column_int64(stmt, 0) = %d, want %d", got, wantInt64)
	}
	if got := sqlite3_column_type(statement.handle, 1); got != SQLITE_FLOAT {
		t.Fatalf("sqlite3_column_type(stmt, 1) = %d, want %d", got, SQLITE_FLOAT)
	}
	if got := sqlite3_column_double(statement.handle, 1); got != wantDouble {
		t.Fatalf("sqlite3_column_double(stmt, 1) = %v, want %v", got, wantDouble)
	}
	if got := sqlite3_column_type(statement.handle, 2); got != SQLITE_BLOB {
		t.Fatalf("sqlite3_column_type(stmt, 2) = %d, want %d", got, SQLITE_BLOB)
	}
	blobPointer := sqlite3_column_blob(statement.handle, 2)
	blobBytes := sqlite3_column_bytes(statement.handle, 2)
	if got := cBytesString(blobPointer, blobBytes); got != string(blobValue) {
		t.Fatalf("sqlite3_column_blob(stmt, 2) = %q, want %q", got, string(blobValue))
	}
	if got := sqlite3_column_type(statement.handle, 3); got != SQLITE_NULL {
		t.Fatalf("sqlite3_column_type(stmt, 3) = %d, want %d", got, SQLITE_NULL)
	}
	if got := sqlite3_column_bytes(statement.handle, 3); got != 0 {
		t.Fatalf("sqlite3_column_bytes(stmt, 3) = %d, want %d", got, 0)
	}
	if got := sqlite3_column_blob(statement.handle, 3); got != 0 {
		t.Fatalf("sqlite3_column_blob(stmt, 3) = %#x, want 0", got)
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}
}

func TestGeneratedBindingsResetAndClearBindingsWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	statement := prepareSQLiteStatement(t, connection.db, "SELECT ?1, ?2")

	if bindResult := sqlite3_bind_int64(statement.handle, 1, 42); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_int64() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if bindResult := sqlite3_bind_text(
		statement.handle,
		2,
		"first-pass",
		-1,
		SQLITE_TRANSIENT,
	); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_text() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first pass = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := sqlite3_column_int64(statement.handle, 0); got != 42 {
		t.Fatalf("sqlite3_column_int64(stmt, 0) = %d, want %d", got, 42)
	}
	if got := sqlite3_column_text(statement.handle, 1); got != "first-pass" {
		t.Fatalf("sqlite3_column_text(stmt, 1) = %q, want %q", got, "first-pass")
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() first pass second call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}

	if resetResult := sqlite3_reset(statement.handle); resetResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_reset() after first pass = %d, want %d, errmsg=%q",
			resetResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() second pass = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := sqlite3_column_int64(statement.handle, 0); got != 42 {
		t.Fatalf("sqlite3_column_int64(stmt, 0) second pass = %d, want %d", got, 42)
	}
	if got := sqlite3_column_text(statement.handle, 1); got != "first-pass" {
		t.Fatalf("sqlite3_column_text(stmt, 1) second pass = %q, want %q", got, "first-pass")
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second pass second call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}

	if resetResult := sqlite3_reset(statement.handle); resetResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_reset() before clear_bindings = %d, want %d, errmsg=%q",
			resetResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if clearResult := sqlite3_clear_bindings(statement.handle); clearResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_clear_bindings() = %d, want %d, errmsg=%q",
			clearResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if bindResult := sqlite3_bind_null(statement.handle, 1); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_null() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if bindResult := sqlite3_bind_double(statement.handle, 2, 7.5); bindResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_double() = %d, want %d, errmsg=%q",
			bindResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() third pass = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := sqlite3_column_type(statement.handle, 0); got != SQLITE_NULL {
		t.Fatalf("sqlite3_column_type(stmt, 0) third pass = %d, want %d", got, SQLITE_NULL)
	}
	if got := sqlite3_column_type(statement.handle, 1); got != SQLITE_FLOAT {
		t.Fatalf("sqlite3_column_type(stmt, 1) third pass = %d, want %d", got, SQLITE_FLOAT)
	}
	if got := sqlite3_column_double(statement.handle, 1); got != 7.5 {
		t.Fatalf("sqlite3_column_double(stmt, 1) third pass = %v, want %v", got, 7.5)
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() third pass second call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}
}

func TestGeneratedBindingsChangesRowIDAndExtendedErrcodeWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	createResult := sqlite3_exec(
		connection.db,
		"CREATE TABLE driver_metrics(id INTEGER PRIMARY KEY, value TEXT)",
		0,
		0,
		0,
	)
	if createResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_exec(CREATE TABLE) = %d, want %d, errmsg=%q",
			createResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	insertResult := sqlite3_exec(
		connection.db,
		"INSERT INTO driver_metrics(value) VALUES ('one'), ('two')",
		0,
		0,
		0,
	)
	if insertResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_exec(INSERT) = %d, want %d, errmsg=%q",
			insertResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if got := sqlite3_changes64(connection.db); got != 2 {
		t.Fatalf("sqlite3_changes64() = %d, want %d", got, 2)
	}
	if got := sqlite3_last_insert_rowid(connection.db); got != 2 {
		t.Fatalf("sqlite3_last_insert_rowid() = %d, want %d", got, 2)
	}

	execResult := sqlite3_exec(
		connection.db,
		"SELECT * FROM missing_table",
		0,
		0,
		0,
	)
	if execResult == SQLITE_OK {
		t.Fatal("sqlite3_exec(missing table) returned SQLITE_OK, want failure")
	}
	if got := sqlite3_extended_errcode(connection.db); got != execResult {
		t.Fatalf("sqlite3_extended_errcode() = %d, want %d", got, execResult)
	}
}

func TestGeneratedBindingsRegisterScalarFunctionWithDestructorInLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0x51ca1a)
	var observedUserData uintptr
	var observedArg string
	destroyCount := 0
	destroyArg := uintptr(0)

	registerResult := sqlite3_create_function_v2_callbacks(
		connection.db,
		"purego_echo",
		1,
		SQLITE_UTF8,
		appData,
		func(
			context *sqlite3_context,
			count int32,
			values **sqlite3_value,
		) {
			sqliteValues := sqliteValueArray(values, count)
			if len(sqliteValues) != 1 {
				sqlite3_result_int(context, int32(len(sqliteValues)))
				return
			}

			observedUserData = sqlite3_user_data(context)
			observedArg = sqlite3_value_text(sqliteValues[0])
			sqlite3_result_text(
				context,
				observedArg+"-from-callback",
				-1,
				SQLITE_TRANSIENT,
			)
		},
		nil,
		nil,
		func(userData uintptr) {
			destroyCount++
			destroyArg = userData
		},
	)
	if registerResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_function_v2() = %d, want %d, errmsg=%q",
			registerResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	statement := prepareSQLiteStatement(t, connection.db, "SELECT purego_echo('callback-value')")
	rows := collectFirstColumnTextRows(t, connection.db, statement)
	statement.Finalize(t)

	if len(rows) != 1 || rows[0] != "callback-value-from-callback" {
		t.Fatalf(
			"SELECT purego_echo(...) rows = %#v, want %#v",
			rows,
			[]string{"callback-value-from-callback"},
		)
	}
	if observedUserData != appData {
		t.Fatalf("sqlite3_user_data() = %#x, want %#x", observedUserData, appData)
	}
	if observedArg != "callback-value" {
		t.Fatalf("sqlite3_value_text() = %q, want %q", observedArg, "callback-value")
	}

	connection.Close(t)

	if destroyCount != 1 {
		t.Fatalf("function xDestroy count = %d, want %d", destroyCount, 1)
	}
	if destroyArg != appData {
		t.Fatalf("function xDestroy arg = %#x, want %#x", destroyArg, appData)
	}
}

func TestGeneratedBindingsRegisterScalarFunctionWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0x51ca2b)
	var observedUserData uintptr
	var observedArg string

	registerResult := sqlite3_create_function_callbacks(
		connection.db,
		"purego_echo_basic",
		1,
		SQLITE_UTF8,
		appData,
		func(
			context *sqlite3_context,
			count int32,
			values **sqlite3_value,
		) {
			sqliteValues := sqliteValueArray(values, count)
			if len(sqliteValues) != 1 {
				sqlite3_result_int(context, int32(len(sqliteValues)))
				return
			}

			observedUserData = sqlite3_user_data(context)
			observedArg = sqlite3_value_text(sqliteValues[0])
			sqlite3_result_text(
				context,
				observedArg+"-from-function",
				-1,
				SQLITE_TRANSIENT,
			)
		},
		nil,
		nil,
	)
	if registerResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_function() = %d, want %d, errmsg=%q",
			registerResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	statement := prepareSQLiteStatement(t, connection.db, "SELECT purego_echo_basic('callback-value')")
	rows := collectFirstColumnTextRows(t, connection.db, statement)
	statement.Finalize(t)

	if len(rows) != 1 || rows[0] != "callback-value-from-function" {
		t.Fatalf(
			"SELECT purego_echo_basic(...) rows = %#v, want %#v",
			rows,
			[]string{"callback-value-from-function"},
		)
	}
	if observedUserData != appData {
		t.Fatalf("sqlite3_user_data() = %#x, want %#x", observedUserData, appData)
	}
	if observedArg != "callback-value" {
		t.Fatalf("sqlite3_value_text() = %q, want %q", observedArg, "callback-value")
	}
}

func TestGeneratedBindingsRegisterScalarFunction16WithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0x51ca16)
	var observedUserData uintptr
	var observedArg string

	scalarCallback := purego.NewCallback(func(
		context *sqlite3_context,
		count int32,
		values **sqlite3_value,
	) {
		sqliteValues := sqliteValueArray(values, count)
		if len(sqliteValues) != 1 {
			sqlite3_result_int(context, int32(len(sqliteValues)))
			return
		}

		observedUserData = sqlite3_user_data(context)
		observedArg = sqlite3_value_text(sqliteValues[0])
		sqlite3_result_text(
			context,
			observedArg+"-from-function16",
			-1,
			SQLITE_TRANSIENT,
		)
	})

	functionName, functionNamePtr := sqliteUTF16CStringPointer("purego_echo16")
	registerResult := sqlite3_create_function16(
		connection.db,
		functionNamePtr,
		1,
		SQLITE_UTF16,
		appData,
		scalarCallback,
		0,
		0,
	)
	runtime.KeepAlive(functionName)
	if registerResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_function16() = %d, want %d, errmsg=%q",
			registerResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	statement := prepareSQLiteStatement(t, connection.db, "SELECT purego_echo16('callback-value')")
	rows := collectFirstColumnTextRows(t, connection.db, statement)
	statement.Finalize(t)

	if len(rows) != 1 || rows[0] != "callback-value-from-function16" {
		t.Fatalf(
			"SELECT purego_echo16(...) rows = %#v, want %#v",
			rows,
			[]string{"callback-value-from-function16"},
		)
	}
	if observedUserData != appData {
		t.Fatalf("sqlite3_user_data() = %#x, want %#x", observedUserData, appData)
	}
	if observedArg != "callback-value" {
		t.Fatalf("sqlite3_value_text() = %q, want %q", observedArg, "callback-value")
	}
}

func TestGeneratedBindingsRegisterCollationWithDestructorInLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0xc011a710)
	compareCount := 0
	destroyCount := 0
	destroyArg := uintptr(0)
	compareAppDataMismatch := false

	registerResult := sqlite3_create_collation_v2_callbacks(
		connection.db,
		"purego_len",
		SQLITE_UTF8,
		appData,
		func(
			userData uintptr,
			leftLength int32,
			left uintptr,
			rightLength int32,
			right uintptr,
		) int32 {
			compareCount++
			if userData != appData {
				compareAppDataMismatch = true
			}

			leftText := cBytesString(left, leftLength)
			rightText := cBytesString(right, rightLength)
			return sqliteCompareByLengthThenLex(leftText, rightText)
		},
		func(userData uintptr) {
			destroyCount++
			destroyArg = userData
		},
	)
	if registerResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_collation_v2() = %d, want %d, errmsg=%q",
			registerResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	statement := prepareSQLiteStatement(
		t,
		connection.db,
		"WITH items(value) AS (VALUES ('bbb'), ('a'), ('cc')) "+
			"SELECT value FROM items ORDER BY value COLLATE purego_len",
	)
	rows := collectFirstColumnTextRows(t, connection.db, statement)
	statement.Finalize(t)

	wantRows := []string{"a", "cc", "bbb"}
	if len(rows) != len(wantRows) {
		t.Fatalf("collation rows len = %d, want %d (%#v)", len(rows), len(wantRows), rows)
	}
	for index, want := range wantRows {
		if rows[index] != want {
			t.Fatalf("collation rows[%d] = %q, want %q (%#v)", index, rows[index], want, rows)
		}
	}
	if compareCount == 0 {
		t.Fatal("collation callback was not invoked")
	}
	if compareAppDataMismatch {
		t.Fatal("collation callback received unexpected app data")
	}

	connection.Close(t)

	if destroyCount != 1 {
		t.Fatalf("collation xDestroy count = %d, want %d", destroyCount, 1)
	}
	if destroyArg != appData {
		t.Fatalf("collation xDestroy arg = %#x, want %#x", destroyArg, appData)
	}
}

func TestGeneratedBindingsRegisterCollationWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0xc011a701)
	compareCount := 0
	compareAppDataMismatch := false

	registerResult := sqlite3_create_collation_callbacks(
		connection.db,
		"purego_len_basic",
		SQLITE_UTF8,
		appData,
		func(
			userData uintptr,
			leftLength int32,
			left uintptr,
			rightLength int32,
			right uintptr,
		) int32 {
			compareCount++
			if userData != appData {
				compareAppDataMismatch = true
			}

			leftText := cBytesString(left, leftLength)
			rightText := cBytesString(right, rightLength)
			return sqliteCompareByLengthThenLex(leftText, rightText)
		},
	)
	if registerResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_collation() = %d, want %d, errmsg=%q",
			registerResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	statement := prepareSQLiteStatement(
		t,
		connection.db,
		"WITH items(value) AS (VALUES ('bbb'), ('a'), ('cc')) "+
			"SELECT value FROM items ORDER BY value COLLATE purego_len_basic",
	)
	rows := collectFirstColumnTextRows(t, connection.db, statement)
	statement.Finalize(t)

	wantRows := []string{"a", "cc", "bbb"}
	if len(rows) != len(wantRows) {
		t.Fatalf("collation rows len = %d, want %d (%#v)", len(rows), len(wantRows), rows)
	}
	for index, want := range wantRows {
		if rows[index] != want {
			t.Fatalf("collation rows[%d] = %q, want %q (%#v)", index, rows[index], want, rows)
		}
	}
	if compareCount == 0 {
		t.Fatal("collation callback was not invoked")
	}
	if compareAppDataMismatch {
		t.Fatal("collation callback received unexpected app data")
	}
}

func TestGeneratedBindingsRegisterCollation16WithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0xc011a716)
	compareCount := 0
	compareAppDataMismatch := false

	compareCallback := purego.NewCallback(func(
		userData uintptr,
		leftLength int32,
		left uintptr,
		rightLength int32,
		right uintptr,
	) int32 {
		compareCount++
		if userData != appData {
			compareAppDataMismatch = true
		}

		leftText := sqliteUTF16BytesString(left, leftLength)
		rightText := sqliteUTF16BytesString(right, rightLength)
		return sqliteCompareByLengthThenLex(leftText, rightText)
	})

	collationName, collationNamePtr := sqliteUTF16CStringPointer("purego_len16")
	registerResult := sqlite3_create_collation16(
		connection.db,
		collationNamePtr,
		SQLITE_UTF16,
		appData,
		compareCallback,
	)
	runtime.KeepAlive(collationName)
	if registerResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_collation16() = %d, want %d, errmsg=%q",
			registerResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	statement := prepareSQLiteStatement(
		t,
		connection.db,
		"WITH items(value) AS (VALUES ('bbb'), ('a'), ('cc')) "+
			"SELECT value FROM items ORDER BY value COLLATE purego_len16",
	)
	rows := collectFirstColumnTextRows(t, connection.db, statement)
	statement.Finalize(t)

	wantRows := []string{"a", "cc", "bbb"}
	if len(rows) != len(wantRows) {
		t.Fatalf("collation rows len = %d, want %d (%#v)", len(rows), len(wantRows), rows)
	}
	for index, want := range wantRows {
		if rows[index] != want {
			t.Fatalf("collation rows[%d] = %q, want %q (%#v)", index, rows[index], want, rows)
		}
	}
	if compareCount == 0 {
		t.Fatal("collation callback was not invoked")
	}
	if compareAppDataMismatch {
		t.Fatal("collation callback received unexpected app data")
	}
}

func TestGeneratedBindingsCommitHookWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	mustExecSQLite(t, connection.db, "CREATE TABLE commit_events(value INTEGER)")

	const appData = uintptr(0xc01117)
	commitCount := 0
	appDataMismatch := false

	previousHook := sqlite3_commit_hook_callbacks(
		connection.db,
		func(userData uintptr) int32 {
			commitCount++
			if userData != appData {
				appDataMismatch = true
			}
			return 0
		},
		appData,
	)
	if previousHook != 0 {
		t.Fatalf("sqlite3_commit_hook() previous hook = %#x, want 0", previousHook)
	}

	mustExecSQLite(
		t,
		connection.db,
		"BEGIN; INSERT INTO commit_events(value) VALUES (1); COMMIT;",
	)

	if commitCount != 1 {
		t.Fatalf("commit hook count = %d, want %d", commitCount, 1)
	}
	if appDataMismatch {
		t.Fatal("commit hook received unexpected app data")
	}
}

func TestGeneratedBindingsRollbackHookWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	mustExecSQLite(t, connection.db, "CREATE TABLE rollback_events(value INTEGER)")

	const appData = uintptr(0x7011ba)
	rollbackCount := 0
	appDataMismatch := false

	previousHook := sqlite3_rollback_hook_callbacks(
		connection.db,
		func(userData uintptr) {
			rollbackCount++
			if userData != appData {
				appDataMismatch = true
			}
		},
		appData,
	)
	if previousHook != 0 {
		t.Fatalf("sqlite3_rollback_hook() previous hook = %#x, want 0", previousHook)
	}

	mustExecSQLite(
		t,
		connection.db,
		"BEGIN; INSERT INTO rollback_events(value) VALUES (1); ROLLBACK;",
	)

	if rollbackCount != 1 {
		t.Fatalf("rollback hook count = %d, want %d", rollbackCount, 1)
	}
	if appDataMismatch {
		t.Fatal("rollback hook received unexpected app data")
	}
}

func TestGeneratedBindingsUpdateHookWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	mustExecSQLite(t, connection.db, "CREATE TABLE update_events(value INTEGER)")

	const appData = uintptr(0x0ada7a)
	updateCount := 0
	appDataMismatch := false
	var gotOperation int32
	var gotDatabaseName string
	var gotTableName string
	var gotRowID sqlite3_int64

	previousHook := sqlite3_update_hook_callbacks(
		connection.db,
		func(
			userData uintptr,
			operation int32,
			databaseName uintptr,
			tableName uintptr,
			rowID sqlite3_int64,
		) {
			updateCount++
			if userData != appData {
				appDataMismatch = true
			}
			gotOperation = operation
			gotDatabaseName = cStringFromUintptr(databaseName)
			gotTableName = cStringFromUintptr(tableName)
			gotRowID = rowID
		},
		appData,
	)
	if previousHook != 0 {
		t.Fatalf("sqlite3_update_hook() previous hook = %#x, want 0", previousHook)
	}

	mustExecSQLite(t, connection.db, "INSERT INTO update_events(value) VALUES (42)")

	if updateCount != 1 {
		t.Fatalf("update hook count = %d, want %d", updateCount, 1)
	}
	if appDataMismatch {
		t.Fatal("update hook received unexpected app data")
	}
	if gotOperation != SQLITE_INSERT {
		t.Fatalf("update hook operation = %d, want %d", gotOperation, SQLITE_INSERT)
	}
	if gotDatabaseName != "main" {
		t.Fatalf("update hook database = %q, want %q", gotDatabaseName, "main")
	}
	if gotTableName != "update_events" {
		t.Fatalf("update hook table = %q, want %q", gotTableName, "update_events")
	}
	if gotRowID != 1 {
		t.Fatalf("update hook rowid = %d, want %d", gotRowID, 1)
	}
}

func TestGeneratedBindingsProgressHandlerWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0x9015aa)
	progressCount := 0
	appDataMismatch := false

	sqlite3_progress_handler_callbacks(
		connection.db,
		1,
		func(userData uintptr) int32 {
			progressCount++
			if userData != appData {
				appDataMismatch = true
			}
			return 0
		},
		appData,
	)

	statement := prepareSQLiteStatement(
		t,
		connection.db,
		"WITH RECURSIVE cnt(x) AS ("+
			"SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 200"+
			") SELECT sum(x) FROM cnt",
	)
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() progress query = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := sqlite3_column_int(statement.handle, 0); got != 20100 {
		t.Fatalf("progress query sum = %d, want %d", got, 20100)
	}
	if stepResult := sqlite3_step(statement.handle); stepResult != SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() progress query second call = %d, want %d, errmsg=%q",
			stepResult,
			SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}

	if progressCount == 0 {
		t.Fatal("progress handler was not invoked")
	}
	if appDataMismatch {
		t.Fatal("progress handler received unexpected app data")
	}
}

func TestGeneratedBindingsTraceV2WithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0x7ace02)
	sawStmtEvent := false
	sawRowEvent := false
	traceCount := 0
	appDataMismatch := false

	traceResult := sqlite3_trace_v2_callbacks(
		connection.db,
		SQLITE_TRACE_STMT|SQLITE_TRACE_ROW,
		func(event uint32, context uintptr, _ uintptr, _ uintptr) int32 {
			traceCount++
			if context != appData {
				appDataMismatch = true
			}
			if event == SQLITE_TRACE_STMT {
				sawStmtEvent = true
			}
			if event == SQLITE_TRACE_ROW {
				sawRowEvent = true
			}
			return 0
		},
		appData,
	)
	if traceResult != SQLITE_OK {
		t.Fatalf(
			"sqlite3_trace_v2() = %d, want %d, errmsg=%q",
			traceResult,
			SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}

	statement := prepareSQLiteStatement(t, connection.db, "SELECT 'trace-value'")
	rows := collectFirstColumnTextRows(t, connection.db, statement)
	statement.Finalize(t)

	if len(rows) != 1 || rows[0] != "trace-value" {
		t.Fatalf("trace query rows = %#v, want %#v", rows, []string{"trace-value"})
	}
	if traceCount == 0 {
		t.Fatal("trace callback was not invoked")
	}
	if !sawStmtEvent {
		t.Fatal("trace callback did not observe SQLITE_TRACE_STMT")
	}
	if !sawRowEvent {
		t.Fatal("trace callback did not observe SQLITE_TRACE_ROW")
	}
	if appDataMismatch {
		t.Fatal("trace callback received unexpected context pointer")
	}
}
