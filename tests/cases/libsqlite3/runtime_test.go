package fixture

import (
	"fmt"
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
	"github.com/johejo/purego-gen/tests/testruntime"
)

type sqliteConnection struct {
	handle uintptr
	db     purego_type_sqlite3
	closed bool
}

type sqliteStatement struct {
	db        purego_type_sqlite3
	handle    purego_type_sqlite3_stmt
	finalized bool
}

func sqliteErrmsg(db purego_type_sqlite3) string {
	if db == 0 {
		return ""
	}
	return purego_func_sqlite3_errmsg(db)
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

	if err := purego_sqlite3_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if got := purego_func_sqlite3_libversion(); got == "" {
		t.Fatal("sqlite3_libversion() returned empty string")
	}

	openResult := purego_func_sqlite3_open(":memory:", uintptr(unsafe.Pointer(&connection.db)))
	if openResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_open(:memory:) = %d, want %d, errmsg=%q",
			openResult,
			purego_const_SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if connection.db == 0 {
		t.Fatal("sqlite3_open returned nil database handle")
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

	if connection.db != 0 {
		closeResult := purego_func_sqlite3_close(connection.db)
		if closeResult != purego_const_SQLITE_OK {
			return fmt.Errorf(
				"sqlite3_close() = %d, want %d, errmsg=%q",
				closeResult,
				purego_const_SQLITE_OK,
				sqliteErrmsg(connection.db),
			)
		}
		connection.db = 0
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
	db purego_type_sqlite3,
	sql string,
) *sqliteStatement {
	t.Helper()

	statement := &sqliteStatement{db: db}
	prepareResult := purego_func_sqlite3_prepare_v2(
		db,
		sql,
		-1,
		uintptr(unsafe.Pointer(&statement.handle)),
		0,
	)
	if prepareResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_prepare_v2(%q) = %d, want %d, errmsg=%q",
			sql,
			prepareResult,
			purego_const_SQLITE_OK,
			sqliteErrmsg(db),
		)
	}
	if statement.handle == 0 {
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
	if statement == nil || statement.finalized || statement.handle == 0 {
		return nil
	}

	finalizeResult := purego_func_sqlite3_finalize(statement.handle)
	if finalizeResult != purego_const_SQLITE_OK {
		return fmt.Errorf(
			"sqlite3_finalize() = %d, want %d, errmsg=%q",
			finalizeResult,
			purego_const_SQLITE_OK,
			sqliteErrmsg(statement.db),
		)
	}

	statement.handle = 0
	statement.finalized = true
	return nil
}

func mustExecSQLite(t *testing.T, db purego_type_sqlite3, sql string) {
	t.Helper()

	execResult := purego_func_sqlite3_exec(
		db,
		sql,
		purego_type_sqlite3_callback(0),
		0,
		0,
	)
	if execResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_exec(%q) = %d, want %d, errmsg=%q",
			sql,
			execResult,
			purego_const_SQLITE_OK,
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
	return cString((*byte)(unsafe.Pointer(ptr)))
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
	return string(unsafe.Slice((*byte)(unsafe.Pointer(ptr)), int(length)))
}

func sqliteValueArray(values uintptr, count int32) []purego_type_sqlite3_value {
	if values == 0 || count <= 0 {
		return nil
	}
	pointerData := *(*unsafe.Pointer)(unsafe.Pointer(&values))
	return unsafe.Slice((*purego_type_sqlite3_value)(pointerData), int(count))
}

func collectFirstColumnTextRows(
	t *testing.T,
	db purego_type_sqlite3,
	statement *sqliteStatement,
) []string {
	t.Helper()

	var rows []string
	for {
		stepResult := purego_func_sqlite3_step(statement.handle)
		switch stepResult {
		case purego_const_SQLITE_ROW:
			rows = append(rows, purego_func_sqlite3_column_text(statement.handle, 0))
		case purego_const_SQLITE_DONE:
			return rows
		default:
			t.Fatalf(
				"sqlite3_step() = %d, want %d or %d, errmsg=%q",
				stepResult,
				purego_const_SQLITE_ROW,
				purego_const_SQLITE_DONE,
				sqliteErrmsg(db),
			)
		}
	}
}

func TestGeneratedBindingsReadTextResultsFromLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	statement := prepareSQLiteStatement(t, connection.db, "SELECT 'hello-from-sqlite'")

	if stepResult := purego_func_sqlite3_step(statement.handle); stepResult != purego_const_SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := purego_func_sqlite3_column_text(statement.handle, 0); got != "hello-from-sqlite" {
		t.Fatalf("sqlite3_column_text(stmt, 0) = %q, want %q", got, "hello-from-sqlite")
	}
	if stepResult := purego_func_sqlite3_step(statement.handle); stepResult != purego_const_SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}
}

func TestGeneratedBindingsExecuteSqliteExecCallbackWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	var callbackValues []string
	var callbackNames []string
	callback := purego_type_sqlite3_callback(
		purego.NewCallback(func(_ uintptr, count int32, values uintptr, names uintptr) int32 {
			callbackValues = cStringArray(values, count)
			callbackNames = cStringArray(names, count)
			return 0
		}),
	)

	execResult := purego_func_sqlite3_exec(
		connection.db,
		"SELECT 'row-value' AS greeting",
		callback,
		0,
		0,
	)
	if execResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_exec() = %d, want %d, errmsg=%q",
			execResult,
			purego_const_SQLITE_OK,
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

	bindResult := purego_func_sqlite3_bind_text(
		statement.handle,
		1,
		"bound-text",
		-1,
		purego_const_SQLITE_TRANSIENT,
	)
	if bindResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_bind_text() = %d, want %d, errmsg=%q",
			bindResult,
			purego_const_SQLITE_OK,
			sqliteErrmsg(connection.db),
		)
	}
	if stepResult := purego_func_sqlite3_step(statement.handle); stepResult != purego_const_SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := purego_func_sqlite3_column_text(statement.handle, 0); got != "bound-text" {
		t.Fatalf("sqlite3_column_text(stmt, 0) = %q, want %q", got, "bound-text")
	}
	if stepResult := purego_func_sqlite3_step(statement.handle); stepResult != purego_const_SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_DONE,
			sqliteErrmsg(connection.db),
		)
	}
}

func TestGeneratedBindingsRegisterScalarFunctionWithDestructorInLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0x51ca1a)
	var observedUserData uintptr
	var observedArg string
	destroyCount := 0
	destroyArg := uintptr(0)

	scalarCallback := purego.NewCallback(func(
		context purego_type_sqlite3_context,
		count int32,
		values uintptr,
	) {
		sqliteValues := sqliteValueArray(values, count)
		if len(sqliteValues) != 1 {
			purego_func_sqlite3_result_int(context, int32(len(sqliteValues)))
			return
		}

		observedUserData = purego_func_sqlite3_user_data(context)
		observedArg = purego_func_sqlite3_value_text(sqliteValues[0])
		purego_func_sqlite3_result_text(
			context,
			observedArg+"-from-callback",
			-1,
			purego_const_SQLITE_TRANSIENT,
		)
	})
	destroyCallback := purego.NewCallback(func(userData uintptr) {
		destroyCount++
		destroyArg = userData
	})

	registerResult := purego_func_sqlite3_create_function_v2(
		connection.db,
		"purego_echo",
		1,
		purego_const_SQLITE_UTF8,
		appData,
		scalarCallback,
		0,
		0,
		destroyCallback,
	)
	if registerResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_function_v2() = %d, want %d, errmsg=%q",
			registerResult,
			purego_const_SQLITE_OK,
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

func TestGeneratedBindingsRegisterCollationWithDestructorInLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)

	const appData = uintptr(0xc011a710)
	compareCount := 0
	destroyCount := 0
	destroyArg := uintptr(0)
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

		leftText := cBytesString(left, leftLength)
		rightText := cBytesString(right, rightLength)
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
	})
	destroyCallback := purego.NewCallback(func(userData uintptr) {
		destroyCount++
		destroyArg = userData
	})

	registerResult := purego_func_sqlite3_create_collation_v2(
		connection.db,
		"purego_len",
		purego_const_SQLITE_UTF8,
		appData,
		compareCallback,
		destroyCallback,
	)
	if registerResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_create_collation_v2() = %d, want %d, errmsg=%q",
			registerResult,
			purego_const_SQLITE_OK,
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

func TestGeneratedBindingsCommitHookWithLibsqlite3(t *testing.T) {
	connection := openSQLiteConnection(t)
	mustExecSQLite(t, connection.db, "CREATE TABLE commit_events(value INTEGER)")

	const appData = uintptr(0xc01117)
	commitCount := 0
	appDataMismatch := false

	previousHook := purego_func_sqlite3_commit_hook(
		connection.db,
		purego.NewCallback(func(userData uintptr) int32 {
			commitCount++
			if userData != appData {
				appDataMismatch = true
			}
			return 0
		}),
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

	previousHook := purego_func_sqlite3_rollback_hook(
		connection.db,
		purego.NewCallback(func(userData uintptr) {
			rollbackCount++
			if userData != appData {
				appDataMismatch = true
			}
		}),
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
	var gotRowID purego_type_sqlite3_int64

	previousHook := purego_func_sqlite3_update_hook(
		connection.db,
		purego.NewCallback(func(
			userData uintptr,
			operation int32,
			databaseName uintptr,
			tableName uintptr,
			rowID purego_type_sqlite3_int64,
		) {
			updateCount++
			if userData != appData {
				appDataMismatch = true
			}
			gotOperation = operation
			gotDatabaseName = cStringFromUintptr(databaseName)
			gotTableName = cStringFromUintptr(tableName)
			gotRowID = rowID
		}),
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
	if gotOperation != purego_const_SQLITE_INSERT {
		t.Fatalf("update hook operation = %d, want %d", gotOperation, purego_const_SQLITE_INSERT)
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

	purego_func_sqlite3_progress_handler(
		connection.db,
		1,
		purego.NewCallback(func(userData uintptr) int32 {
			progressCount++
			if userData != appData {
				appDataMismatch = true
			}
			return 0
		}),
		appData,
	)

	statement := prepareSQLiteStatement(
		t,
		connection.db,
		"WITH RECURSIVE cnt(x) AS ("+
			"SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 200"+
			") SELECT sum(x) FROM cnt",
	)
	if stepResult := purego_func_sqlite3_step(statement.handle); stepResult != purego_const_SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() progress query = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_ROW,
			sqliteErrmsg(connection.db),
		)
	}
	if got := purego_func_sqlite3_column_int(statement.handle, 0); got != 20100 {
		t.Fatalf("progress query sum = %d, want %d", got, 20100)
	}
	if stepResult := purego_func_sqlite3_step(statement.handle); stepResult != purego_const_SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() progress query second call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_DONE,
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
