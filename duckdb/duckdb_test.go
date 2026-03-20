package duckdb_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	_ "github.com/johejo/purego-gen/duckdb"
)

func TestDriverOpenPingCRUD(t *testing.T) {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		t.Fatal("Ping:", err)
	}

	if _, err := db.Exec("CREATE TABLE test (id INTEGER, name VARCHAR, value DOUBLE)"); err != nil {
		t.Fatal("CREATE:", err)
	}

	result, err := db.Exec("INSERT INTO test VALUES (1, 'hello', 3.14), (2, 'world', 2.72)")
	if err != nil {
		t.Fatal("INSERT:", err)
	}
	affected, err := result.RowsAffected()
	if err != nil {
		t.Fatal(err)
	}
	if affected != 2 {
		t.Fatalf("expected 2 rows affected, got %d", affected)
	}

	rows, err := db.Query("SELECT id, name, value FROM test ORDER BY id")
	if err != nil {
		t.Fatal("SELECT:", err)
	}
	defer rows.Close()

	type row struct {
		id    int64
		name  string
		value float64
	}
	var got []row
	for rows.Next() {
		var r row
		if err := rows.Scan(&r.id, &r.name, &r.value); err != nil {
			t.Fatal("Scan:", err)
		}
		got = append(got, r)
	}
	if err := rows.Err(); err != nil {
		t.Fatal("Rows.Err:", err)
	}

	if len(got) != 2 {
		t.Fatalf("expected 2 rows, got %d", len(got))
	}
	if got[0].id != 1 || got[0].name != "hello" || got[0].value != 3.14 {
		t.Fatalf("row 0: %+v", got[0])
	}
	if got[1].id != 2 || got[1].name != "world" || got[1].value != 2.72 {
		t.Fatalf("row 1: %+v", got[1])
	}

	// UPDATE
	if _, err := db.Exec("UPDATE test SET name = 'updated' WHERE id = 1"); err != nil {
		t.Fatal("UPDATE:", err)
	}

	var name string
	if err := db.QueryRow("SELECT name FROM test WHERE id = 1").Scan(&name); err != nil {
		t.Fatal("QueryRow:", err)
	}
	if name != "updated" {
		t.Fatalf("expected 'updated', got %q", name)
	}

	// DELETE
	if _, err := db.Exec("DELETE FROM test WHERE id = 2"); err != nil {
		t.Fatal("DELETE:", err)
	}

	var count int64
	if err := db.QueryRow("SELECT count(*) FROM test").Scan(&count); err != nil {
		t.Fatal("COUNT:", err)
	}
	if count != 1 {
		t.Fatalf("expected 1 row, got %d", count)
	}
}

func TestDriverPreparedStatements(t *testing.T) {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if _, err := db.Exec("CREATE TABLE typed (b BOOLEAN, i INTEGER, bi BIGINT, f FLOAT, d DOUBLE, s VARCHAR)"); err != nil {
		t.Fatal(err)
	}

	stmt, err := db.Prepare("INSERT INTO typed VALUES ($1, $2, $3, $4, $5, $6)")
	if err != nil {
		t.Fatal(err)
	}
	defer stmt.Close()

	if _, err := stmt.Exec(true, int64(42), int64(1234567890123), 3.14, 2.71828, "test string"); err != nil {
		t.Fatal(err)
	}

	var (
		b  bool
		i  int64
		bi int64
		f  float64
		d  float64
		s  string
	)
	if err := db.QueryRow("SELECT * FROM typed").Scan(&b, &i, &bi, &f, &d, &s); err != nil {
		t.Fatal(err)
	}
	if !b {
		t.Error("expected true")
	}
	if i != 42 {
		t.Errorf("expected 42, got %d", i)
	}
	if bi != 1234567890123 {
		t.Errorf("expected 1234567890123, got %d", bi)
	}
	if s != "test string" {
		t.Errorf("expected 'test string', got %q", s)
	}
}

func TestDriverTransactions(t *testing.T) {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if _, err := db.Exec("CREATE TABLE txtest (v INTEGER)"); err != nil {
		t.Fatal(err)
	}

	// Commit
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := tx.Exec("INSERT INTO txtest VALUES (1)"); err != nil {
		t.Fatal(err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}

	var count int64
	if err := db.QueryRow("SELECT count(*) FROM txtest").Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("expected 1, got %d", count)
	}

	// Rollback
	tx, err = db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := tx.Exec("INSERT INTO txtest VALUES (2)"); err != nil {
		t.Fatal(err)
	}
	if err := tx.Rollback(); err != nil {
		t.Fatal(err)
	}

	if err := db.QueryRow("SELECT count(*) FROM txtest").Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("after rollback: expected 1, got %d", count)
	}
}

func TestDriverNullHandling(t *testing.T) {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if _, err := db.Exec("CREATE TABLE nulls (i INTEGER, s VARCHAR)"); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("INSERT INTO nulls VALUES (NULL, 'hello'), (42, NULL)"); err != nil {
		t.Fatal(err)
	}

	rows, err := db.Query("SELECT i, s FROM nulls ORDER BY CASE WHEN i IS NULL THEN 0 ELSE 1 END")
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()

	// Row 1: i=NULL, s='hello'
	if !rows.Next() {
		t.Fatal("expected row 1")
	}
	var ni sql.NullInt64
	var ns sql.NullString
	if err := rows.Scan(&ni, &ns); err != nil {
		t.Fatal(err)
	}
	if ni.Valid {
		t.Error("expected i to be NULL")
	}
	if !ns.Valid || ns.String != "hello" {
		t.Errorf("expected s='hello', got %+v", ns)
	}

	// Row 2: i=42, s=NULL
	if !rows.Next() {
		t.Fatal("expected row 2")
	}
	if err := rows.Scan(&ni, &ns); err != nil {
		t.Fatal(err)
	}
	if !ni.Valid || ni.Int64 != 42 {
		t.Errorf("expected i=42, got %+v", ni)
	}
	if ns.Valid {
		t.Error("expected s to be NULL")
	}
}

func TestDriverBlobAndTimestamp(t *testing.T) {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if _, err := db.Exec("CREATE TABLE blobts (b BLOB, ts TIMESTAMP)"); err != nil {
		t.Fatal(err)
	}

	blob := []byte{0x00, 0x01, 0x02, 0xff, 0xfe, 0xfd}
	ts := time.Date(2024, 6, 15, 12, 30, 45, 123456000, time.UTC)

	if _, err := db.Exec("INSERT INTO blobts VALUES ($1, $2)", blob, ts); err != nil {
		t.Fatal(err)
	}

	var gotBlob []byte
	var gotTS time.Time
	if err := db.QueryRow("SELECT b, ts FROM blobts").Scan(&gotBlob, &gotTS); err != nil {
		t.Fatal(err)
	}

	if len(gotBlob) != len(blob) {
		t.Fatalf("blob length: expected %d, got %d", len(blob), len(gotBlob))
	}
	for i := range blob {
		if gotBlob[i] != blob[i] {
			t.Fatalf("blob[%d]: expected %x, got %x", i, blob[i], gotBlob[i])
		}
	}

	// DuckDB stores timestamps with microsecond precision
	expectedTS := time.Date(2024, 6, 15, 12, 30, 45, 123456000, time.UTC)
	if !gotTS.Equal(expectedTS) {
		t.Fatalf("timestamp: expected %v, got %v", expectedTS, gotTS)
	}
}

func TestDriverContextCancellation(t *testing.T) {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	// Generate a long-running query
	_, err = db.ExecContext(ctx, "SELECT * FROM generate_series(1, 100000000)")
	if err == nil {
		t.Fatal("expected error from cancelled context")
	}
	// The error should be context-related
	if ctx.Err() == nil {
		t.Fatal("expected context to be done")
	}
}

func TestDriverErrorPropagation(t *testing.T) {
	db, err := sql.Open("duckdb", "")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	_, err = db.Exec("SELECT * FROM nonexistent_table")
	if err == nil {
		t.Fatal("expected error")
	}
	if !containsString(err.Error(), "nonexistent_table") {
		t.Fatalf("error should mention table name: %v", err)
	}
}

func containsString(s, substr string) bool {
	return len(s) >= len(substr) && searchString(s, substr)
}

func searchString(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
