//go:build purego_gen_case_runtime
// +build purego_gen_case_runtime

package fixture

import (
	"os"
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
)

func sqliteErrmsg(db purego_type_sqlite3) string {
	if db == 0 {
		return ""
	}
	return purego_func_sqlite3_errmsg(db)
}

func openSQLiteHandle(t *testing.T) (uintptr, purego_type_sqlite3) {
	t.Helper()

	libraryPath := os.Getenv("PUREGO_GEN_TEST_LIB")
	if libraryPath == "" {
		t.Fatal("PUREGO_GEN_TEST_LIB must be set")
	}

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		t.Fatalf("open library: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			t.Errorf("close library: %v", closeErr)
		}
	})

	if err := purego_sqlite3_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if got := purego_func_sqlite3_libversion(); got == "" {
		t.Fatal("sqlite3_libversion() returned empty string")
	}

	var db purego_type_sqlite3
	openResult := purego_func_sqlite3_open(":memory:", uintptr(unsafe.Pointer(&db)))
	if openResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_open(:memory:) = %d, want %d, errmsg=%q",
			openResult,
			purego_const_SQLITE_OK,
			sqliteErrmsg(db),
		)
	}
	if db == 0 {
		t.Fatal("sqlite3_open returned nil database handle")
	}

	t.Cleanup(func() {
		if db == 0 {
			return
		}
		if closeResult := purego_func_sqlite3_close(db); closeResult != purego_const_SQLITE_OK {
			t.Errorf(
				"sqlite3_close() = %d, want %d, errmsg=%q",
				closeResult,
				purego_const_SQLITE_OK,
				sqliteErrmsg(db),
			)
		}
	})

	return handle, db
}

func prepareSQLiteStatement(
	t *testing.T,
	db purego_type_sqlite3,
	sql string,
) purego_type_sqlite3_stmt {
	t.Helper()

	var stmt purego_type_sqlite3_stmt
	prepareResult := purego_func_sqlite3_prepare_v2(
		db,
		sql,
		-1,
		uintptr(unsafe.Pointer(&stmt)),
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
	if stmt == 0 {
		t.Fatalf("sqlite3_prepare_v2(%q) returned nil statement handle", sql)
	}

	t.Cleanup(func() {
		if stmt == 0 {
			return
		}
		if finalizeResult := purego_func_sqlite3_finalize(stmt); finalizeResult != purego_const_SQLITE_OK {
			t.Errorf(
				"sqlite3_finalize() = %d, want %d, errmsg=%q",
				finalizeResult,
				purego_const_SQLITE_OK,
				sqliteErrmsg(db),
			)
		}
	})

	return stmt
}

func cString(ptr *byte) string {
	if ptr == nil {
		return ""
	}
	length := 0
	for *(*byte)(unsafe.Pointer(uintptr(unsafe.Pointer(ptr)) + uintptr(length))) != 0 {
		length++
	}
	return string(unsafe.Slice(ptr, length))
}

func cStringArray(values uintptr, count int32) []string {
	if values == 0 || count <= 0 {
		return nil
	}
	pointers := unsafe.Slice((**byte)(unsafe.Pointer(values)), int(count))
	result := make([]string, len(pointers))
	for index, pointer := range pointers {
		result[index] = cString(pointer)
	}
	return result
}

func TestGeneratedBindingsReadTextResultsFromLibsqlite3(t *testing.T) {
	_, db := openSQLiteHandle(t)
	stmt := prepareSQLiteStatement(t, db, "SELECT 'hello-from-sqlite'")

	if stepResult := purego_func_sqlite3_step(stmt); stepResult != purego_const_SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_ROW,
			sqliteErrmsg(db),
		)
	}
	if got := purego_func_sqlite3_column_text(stmt, 0); got != "hello-from-sqlite" {
		t.Fatalf("sqlite3_column_text(stmt, 0) = %q, want %q", got, "hello-from-sqlite")
	}
	if stepResult := purego_func_sqlite3_step(stmt); stepResult != purego_const_SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_DONE,
			sqliteErrmsg(db),
		)
	}
}

func TestGeneratedBindingsExecuteSqliteExecCallbackWithLibsqlite3(t *testing.T) {
	_, db := openSQLiteHandle(t)

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
		db,
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
			sqliteErrmsg(db),
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
	_, db := openSQLiteHandle(t)
	stmt := prepareSQLiteStatement(t, db, "SELECT ?1")

	bindResult := purego_func_sqlite3_bind_text(
		stmt,
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
			sqliteErrmsg(db),
		)
	}
	if stepResult := purego_func_sqlite3_step(stmt); stepResult != purego_const_SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_ROW,
			sqliteErrmsg(db),
		)
	}
	if got := purego_func_sqlite3_column_text(stmt, 0); got != "bound-text" {
		t.Fatalf("sqlite3_column_text(stmt, 0) = %q, want %q", got, "bound-text")
	}
	if stepResult := purego_func_sqlite3_step(stmt); stepResult != purego_const_SQLITE_DONE {
		t.Fatalf(
			"sqlite3_step() second call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_DONE,
			sqliteErrmsg(db),
		)
	}
}
