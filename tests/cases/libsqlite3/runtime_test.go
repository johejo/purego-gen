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

func TestGeneratedBindingsExecutePreparedStatementWithLibsqlite3(t *testing.T) {
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

	var stmt purego_type_sqlite3_stmt
	prepareResult := purego_func_sqlite3_prepare_v2(
		db,
		"SELECT 41 + 1",
		-1,
		uintptr(unsafe.Pointer(&stmt)),
		0,
	)
	if prepareResult != purego_const_SQLITE_OK {
		t.Fatalf(
			"sqlite3_prepare_v2() = %d, want %d, errmsg=%q",
			prepareResult,
			purego_const_SQLITE_OK,
			sqliteErrmsg(db),
		)
	}
	if stmt == 0 {
		t.Fatal("sqlite3_prepare_v2 returned nil statement handle")
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

	if stepResult := purego_func_sqlite3_step(stmt); stepResult != purego_const_SQLITE_ROW {
		t.Fatalf(
			"sqlite3_step() first call = %d, want %d, errmsg=%q",
			stepResult,
			purego_const_SQLITE_ROW,
			sqliteErrmsg(db),
		)
	}
	if got := purego_func_sqlite3_column_int(stmt, 0); got != 42 {
		t.Fatalf("sqlite3_column_int(stmt, 0) = %d, want 42", got)
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
