package sqlite3sys_test

import (
	"bytes"
	"testing"

	"github.com/johejo/purego-gen/sqlite3/sqlite3sys"
)

func openTestDB(t *testing.T) *sqlite3sys.DB {
	t.Helper()
	if err := sqlite3sys.Load(); err != nil {
		t.Fatalf("Load: %v", err)
	}
	var db *sqlite3sys.DB
	rc := sqlite3sys.OpenV2(":memory:", sqlite3sys.SQLITE_OPEN_READWRITE|sqlite3sys.SQLITE_OPEN_CREATE|sqlite3sys.SQLITE_OPEN_MEMORY, "", &db)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("OpenV2: rc=%d", rc)
	}
	t.Cleanup(func() { sqlite3sys.CloseV2(db) })
	return db
}

func execSQL(t *testing.T, db *sqlite3sys.DB, sql string) {
	t.Helper()
	var stmt *sqlite3sys.Stmt
	rc := sqlite3sys.PrepareV2(db, sql, &stmt)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("PrepareV2(%q): rc=%d err=%s", sql, rc, sqlite3sys.Errmsg(db))
	}
	defer sqlite3sys.Finalize(stmt)
	rc = sqlite3sys.Step(stmt)
	if rc != sqlite3sys.SQLITE_DONE && rc != sqlite3sys.SQLITE_ROW {
		t.Fatalf("Step(%q): rc=%d err=%s", sql, rc, sqlite3sys.Errmsg(db))
	}
}

func TestExpandedSQL(t *testing.T) {
	db := openTestDB(t)

	var stmt *sqlite3sys.Stmt
	rc := sqlite3sys.PrepareV2(db, "SELECT ? + ?", &stmt)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("PrepareV2: rc=%d", rc)
	}
	defer sqlite3sys.Finalize(stmt)

	if rc = sqlite3sys.BindInt64(stmt, 1, 10); rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BindInt64(1): rc=%d", rc)
	}
	if rc = sqlite3sys.BindInt64(stmt, 2, 20); rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BindInt64(2): rc=%d", rc)
	}

	got := sqlite3sys.ExpandedSQL(stmt)
	if got != "SELECT 10 + 20" {
		t.Fatalf("ExpandedSQL = %q, want %q", got, "SELECT 10 + 20")
	}
}

func TestBackup(t *testing.T) {
	src := openTestDB(t)
	execSQL(t, src, "CREATE TABLE items(id INTEGER PRIMARY KEY, val TEXT)")
	execSQL(t, src, "INSERT INTO items(val) VALUES('hello')")
	execSQL(t, src, "INSERT INTO items(val) VALUES('world')")

	dst := openTestDB(t)

	backup := sqlite3sys.BackupInit(dst, "main", src, "main")
	if backup == nil {
		t.Fatalf("BackupInit returned nil: %s", sqlite3sys.Errmsg(dst))
	}

	rc := sqlite3sys.BackupStep(backup, -1)
	if rc != sqlite3sys.SQLITE_DONE {
		t.Fatalf("BackupStep: rc=%d, want SQLITE_DONE(%d)", rc, sqlite3sys.SQLITE_DONE)
	}

	remaining := sqlite3sys.BackupRemaining(backup)
	if remaining != 0 {
		t.Fatalf("BackupRemaining = %d, want 0", remaining)
	}
	pagecount := sqlite3sys.BackupPagecount(backup)
	if pagecount <= 0 {
		t.Fatalf("BackupPagecount = %d, want > 0", pagecount)
	}

	rc = sqlite3sys.BackupFinish(backup)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BackupFinish: rc=%d", rc)
	}

	// Verify data in destination.
	var stmt *sqlite3sys.Stmt
	rc = sqlite3sys.PrepareV2(dst, "SELECT count(*) FROM items", &stmt)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("PrepareV2 on dst: rc=%d err=%s", rc, sqlite3sys.Errmsg(dst))
	}
	defer sqlite3sys.Finalize(stmt)
	rc = sqlite3sys.Step(stmt)
	if rc != sqlite3sys.SQLITE_ROW {
		t.Fatalf("Step: rc=%d", rc)
	}
	count := sqlite3sys.ColumnInt(stmt, 0)
	if count != 2 {
		t.Fatalf("count(*) = %d, want 2", count)
	}
}

func TestBlobReadWrite(t *testing.T) {
	db := openTestDB(t)
	execSQL(t, db, "CREATE TABLE blobs(id INTEGER PRIMARY KEY, data BLOB)")
	execSQL(t, db, "INSERT INTO blobs(id, data) VALUES(1, zeroblob(100))")

	var blob *sqlite3sys.Blob
	rc := sqlite3sys.BlobOpen(db, "main", "blobs", "data", 1, 1, &blob)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BlobOpen: rc=%d err=%s", rc, sqlite3sys.Errmsg(db))
	}
	defer sqlite3sys.BlobClose(blob)

	size := sqlite3sys.BlobBytes(blob)
	if size != 100 {
		t.Fatalf("BlobBytes = %d, want 100", size)
	}

	writeData := bytes.Repeat([]byte{0xAB}, 50)
	rc = sqlite3sys.BlobWriteBytes(blob, writeData, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BlobWriteBytes: rc=%d", rc)
	}

	readBuf := make([]byte, 50)
	rc = sqlite3sys.BlobReadBytes(blob, readBuf, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BlobReadBytes: rc=%d", rc)
	}
	if !bytes.Equal(readBuf, writeData) {
		t.Fatalf("BlobReadBytes returned %x, want %x", readBuf, writeData)
	}
}

func TestBlobReopen(t *testing.T) {
	db := openTestDB(t)
	execSQL(t, db, "CREATE TABLE blobs(id INTEGER PRIMARY KEY, data BLOB)")
	execSQL(t, db, "INSERT INTO blobs(id, data) VALUES(1, zeroblob(10))")
	execSQL(t, db, "INSERT INTO blobs(id, data) VALUES(2, zeroblob(10))")

	var blob *sqlite3sys.Blob
	rc := sqlite3sys.BlobOpen(db, "main", "blobs", "data", 1, 1, &blob)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BlobOpen: rc=%d", rc)
	}
	defer sqlite3sys.BlobClose(blob)

	data1 := []byte("AAAAAAAAAA")
	rc = sqlite3sys.BlobWriteBytes(blob, data1, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BlobWriteBytes row1: rc=%d", rc)
	}

	rc = sqlite3sys.BlobReopen(blob, 2)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BlobReopen: rc=%d", rc)
	}

	data2 := []byte("BBBBBBBBBB")
	rc = sqlite3sys.BlobWriteBytes(blob, data2, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("BlobWriteBytes row2: rc=%d", rc)
	}

	// Read back both rows via SQL.
	for _, tt := range []struct {
		id   int
		want []byte
	}{{1, data1}, {2, data2}} {
		var stmt *sqlite3sys.Stmt
		rc = sqlite3sys.PrepareV2(db, "SELECT data FROM blobs WHERE id = ?", &stmt)
		if rc != sqlite3sys.SQLITE_OK {
			t.Fatalf("PrepareV2 row%d: rc=%d", tt.id, rc)
		}
		sqlite3sys.BindInt(stmt, 1, int32(tt.id))
		rc = sqlite3sys.Step(stmt)
		if rc != sqlite3sys.SQLITE_ROW {
			t.Fatalf("Step row%d: rc=%d", tt.id, rc)
		}
		got := sqlite3sys.ColumnBlobBytes(stmt, 0)
		sqlite3sys.Finalize(stmt)
		if !bytes.Equal(got, tt.want) {
			t.Fatalf("row%d data = %q, want %q", tt.id, got, tt.want)
		}
	}
}

func TestTableColumnMetadata(t *testing.T) {
	db := openTestDB(t)
	execSQL(t, db, "CREATE TABLE meta(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE, value REAL)")

	tests := []struct {
		column     string
		dataType   string
		collSeq    string
		notNull    int32
		primaryKey int32
		autoinc    int32
	}{
		{"id", "INTEGER", "BINARY", 0, 1, 1},
		{"name", "TEXT", "NOCASE", 1, 0, 0},
		{"value", "REAL", "BINARY", 0, 0, 0},
	}
	for _, tt := range tests {
		dataType, collSeq, notNull, primaryKey, autoinc, rc := sqlite3sys.TableColumnMetadata(db, "main", "meta", tt.column)
		if rc != sqlite3sys.SQLITE_OK {
			t.Fatalf("TableColumnMetadata(%s): rc=%d", tt.column, rc)
		}
		if dataType != tt.dataType {
			t.Errorf("%s: dataType = %q, want %q", tt.column, dataType, tt.dataType)
		}
		if collSeq != tt.collSeq {
			t.Errorf("%s: collSeq = %q, want %q", tt.column, collSeq, tt.collSeq)
		}
		if notNull != tt.notNull {
			t.Errorf("%s: notNull = %d, want %d", tt.column, notNull, tt.notNull)
		}
		if primaryKey != tt.primaryKey {
			t.Errorf("%s: primaryKey = %d, want %d", tt.column, primaryKey, tt.primaryKey)
		}
		if autoinc != tt.autoinc {
			t.Errorf("%s: autoinc = %d, want %d", tt.column, autoinc, tt.autoinc)
		}
	}

	// Non-existent table should fail.
	_, _, _, _, _, rc := sqlite3sys.TableColumnMetadata(db, "main", "no_such_table", "x")
	if rc == sqlite3sys.SQLITE_OK {
		t.Fatal("TableColumnMetadata on non-existent table returned SQLITE_OK")
	}
}

func TestSerializeDeserialize(t *testing.T) {
	src := openTestDB(t)
	execSQL(t, src, "CREATE TABLE sd(id INTEGER PRIMARY KEY, val TEXT)")
	execSQL(t, src, "INSERT INTO sd(val) VALUES('serialize_test')")

	data := sqlite3sys.Serialize(src, "main", 0)
	if data == nil {
		t.Fatal("Serialize returned nil")
	}
	if len(data) == 0 {
		t.Fatal("Serialize returned empty slice")
	}

	dst := openTestDB(t)
	rc := sqlite3sys.Deserialize(dst, "main", data, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("Deserialize: rc=%d", rc)
	}

	var stmt *sqlite3sys.Stmt
	rc = sqlite3sys.PrepareV2(dst, "SELECT val FROM sd", &stmt)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("PrepareV2 on dst: rc=%d err=%s", rc, sqlite3sys.Errmsg(dst))
	}
	defer sqlite3sys.Finalize(stmt)
	rc = sqlite3sys.Step(stmt)
	if rc != sqlite3sys.SQLITE_ROW {
		t.Fatalf("Step: rc=%d", rc)
	}
	got := sqlite3sys.ColumnText(stmt, 0)
	if got != "serialize_test" {
		t.Fatalf("val = %q, want %q", got, "serialize_test")
	}
}

func TestSerializeEmptyDB(t *testing.T) {
	db := openTestDB(t)
	data := sqlite3sys.Serialize(db, "main", 0)
	if data == nil {
		t.Fatal("Serialize of empty DB returned nil, want non-nil")
	}
}

func TestSerializeUnknownSchema(t *testing.T) {
	db := openTestDB(t)
	data := sqlite3sys.Serialize(db, "no_such_schema", 0)
	if data != nil {
		t.Fatalf("Serialize of unknown schema returned %d bytes, want nil", len(data))
	}
}

func TestStatus(t *testing.T) {
	db := openTestDB(t)
	// Ensure some memory is used.
	execSQL(t, db, "CREATE TABLE status_test(id INTEGER PRIMARY KEY)")

	current, highwater, rc := sqlite3sys.Status(sqlite3sys.SQLITE_STATUS_MEMORY_USED, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("Status: rc=%d", rc)
	}
	if current <= 0 {
		t.Fatalf("Status current = %d, want > 0", current)
	}
	if highwater < current {
		t.Fatalf("Status highwater = %d < current = %d", highwater, current)
	}

	current64, highwater64, rc := sqlite3sys.Status64(sqlite3sys.SQLITE_STATUS_MEMORY_USED, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("Status64: rc=%d", rc)
	}
	if current64 <= 0 {
		t.Fatalf("Status64 current = %d, want > 0", current64)
	}
	if highwater64 < current64 {
		t.Fatalf("Status64 highwater = %d < current = %d", highwater64, current64)
	}
}

func TestDBStatus(t *testing.T) {
	db := openTestDB(t)
	execSQL(t, db, "CREATE TABLE dbstatus_test(id INTEGER PRIMARY KEY, data TEXT)")
	execSQL(t, db, "INSERT INTO dbstatus_test(data) VALUES('test')")

	current, _, rc := sqlite3sys.DBStatus(db, sqlite3sys.SQLITE_DBSTATUS_CACHE_USED, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("DBStatus: rc=%d", rc)
	}
	if current <= 0 {
		t.Fatalf("DBStatus current = %d, want > 0", current)
	}

	current64, _, rc := sqlite3sys.DBStatus64(db, sqlite3sys.SQLITE_DBSTATUS_CACHE_USED, 0)
	if rc != sqlite3sys.SQLITE_OK {
		t.Fatalf("DBStatus64: rc=%d", rc)
	}
	if current64 <= 0 {
		t.Fatalf("DBStatus64 current = %d, want > 0", current64)
	}
}
