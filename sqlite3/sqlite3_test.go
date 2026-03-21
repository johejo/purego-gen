package sqlite3_test

import (
	"context"
	"database/sql"
	"errors"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	sqlite3 "github.com/johejo/purego-gen/sqlite3"
)

func TestDriverOpenPingCRUDAndNamedParams(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "test.db")
	db, err := sql.Open("sqlite3", "file:"+dbPath+"?mode=rwc&_foreign_keys=on")
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	defer db.Close()

	ctx := context.Background()
	if err := db.PingContext(ctx); err != nil {
		t.Fatalf("PingContext: %v", err)
	}

	if _, err := db.ExecContext(ctx, "CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT NOT NULL)"); err != nil {
		t.Fatalf("CREATE TABLE: %v", err)
	}

	result, err := db.ExecContext(
		ctx,
		"INSERT INTO items(name) VALUES(:name)",
		sql.Named("name", "alice"),
	)
	if err != nil {
		t.Fatalf("INSERT: %v", err)
	}

	lastInsertID, err := result.LastInsertId()
	if err != nil {
		t.Fatalf("LastInsertId: %v", err)
	}
	if lastInsertID != 1 {
		t.Fatalf("LastInsertId = %d, want 1", lastInsertID)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		t.Fatalf("RowsAffected: %v", err)
	}
	if rowsAffected != 1 {
		t.Fatalf("RowsAffected = %d, want 1", rowsAffected)
	}

	var name string
	if err := db.QueryRowContext(ctx, "SELECT name FROM items WHERE id = ?", 1).Scan(&name); err != nil {
		t.Fatalf("SELECT name: %v", err)
	}
	if name != "alice" {
		t.Fatalf("SELECT name = %q, want %q", name, "alice")
	}
}

func TestDriverConnectHookAndRegistrationAPIs(t *testing.T) {
	driver := &sqlite3.SQLiteDriver{
		ConnectHook: func(conn *sqlite3.SQLiteConn) error {
			if err := conn.RegisterFunc("purego_upper", func(value string) string {
				return strings.ToUpper(value)
			}, true); err != nil {
				return err
			}
			return nil
		},
	}

	connector, err := driver.OpenConnector("file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("OpenConnector: %v", err)
	}

	db := sql.OpenDB(connector)
	defer db.Close()

	conn, err := db.Conn(context.Background())
	if err != nil {
		t.Fatalf("db.Conn: %v", err)
	}
	defer conn.Close()

	if err := conn.Raw(func(driverConn any) error {
		sqliteConn := driverConn.(*sqlite3.SQLiteConn)
		return sqliteConn.RegisterCollation("purego_len", func(left string, right string) int {
			if len(left) < len(right) {
				return -1
			}
			if len(left) > len(right) {
				return 1
			}
			return strings.Compare(left, right)
		})
	}); err != nil {
		t.Fatalf("RegisterCollation: %v", err)
	}

	var got string
	if err := conn.QueryRowContext(
		context.Background(),
		"SELECT purego_upper('hello')",
	).Scan(&got); err != nil {
		t.Fatalf("SELECT purego_upper: %v", err)
	}
	if got != "HELLO" {
		t.Fatalf("purego_upper = %q, want %q", got, "HELLO")
	}

	rows, err := conn.QueryContext(
		context.Background(),
		"WITH items(value) AS (VALUES ('bbb'), ('a'), ('cc')) "+
			"SELECT value FROM items ORDER BY value COLLATE purego_len",
	)
	if err != nil {
		t.Fatalf("SELECT COLLATE: %v", err)
	}
	defer rows.Close()

	var values []string
	for rows.Next() {
		var value string
		if err := rows.Scan(&value); err != nil {
			t.Fatalf("rows.Scan: %v", err)
		}
		values = append(values, value)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows.Err: %v", err)
	}

	want := []string{"a", "cc", "bbb"}
	if strings.Join(values, ",") != strings.Join(want, ",") {
		t.Fatalf("ordered values = %#v, want %#v", values, want)
	}
}

func TestDriverLocParsesTimestampColumns(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "time.db")
	db, err := sql.Open("sqlite3", "file:"+dbPath+"?mode=rwc&loc=UTC")
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	defer db.Close()

	ctx := context.Background()
	if _, err := db.ExecContext(ctx, "CREATE TABLE events(ts TIMESTAMP NOT NULL)"); err != nil {
		t.Fatalf("CREATE TABLE: %v", err)
	}
	if _, err := db.ExecContext(ctx, "INSERT INTO events(ts) VALUES(?)", "2026-03-18 10:20:30"); err != nil {
		t.Fatalf("INSERT: %v", err)
	}

	var got time.Time
	if err := db.QueryRowContext(ctx, "SELECT ts FROM events").Scan(&got); err != nil {
		t.Fatalf("SELECT ts: %v", err)
	}

	want := time.Date(2026, 3, 18, 10, 20, 30, 0, time.UTC)
	if !got.Equal(want) {
		t.Fatalf("timestamp = %v, want %v", got, want)
	}
}

func TestDriverContextCancellationInterruptsLongQuery(t *testing.T) {
	driver := &sqlite3.SQLiteDriver{
		ConnectHook: func(conn *sqlite3.SQLiteConn) error {
			return conn.RegisterFunc("purego_slow", func(value int64) int64 {
				time.Sleep(1 * time.Millisecond)
				return value
			}, true)
		},
	}

	connector, err := driver.OpenConnector("file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("OpenConnector: %v", err)
	}

	db := sql.OpenDB(connector)
	defer db.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Millisecond)
	defer cancel()

	rows, err := db.QueryContext(
		ctx,
		"WITH RECURSIVE cnt(x) AS ("+
			"SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 1000"+
			") SELECT sum(purego_slow(x)) FROM cnt",
	)
	if err != nil {
		t.Fatalf("QueryContext: %v", err)
	}
	defer rows.Close()

	var total int64
	scanErr := error(nil)
	if rows.Next() {
		scanErr = rows.Scan(&total)
	}
	if scanErr == nil {
		scanErr = rows.Err()
	}
	if !errors.Is(scanErr, context.DeadlineExceeded) && !errors.Is(scanErr, context.Canceled) {
		t.Fatalf("scan/query error = %v, want context cancellation", scanErr)
	}
}

func TestDriverReturnsSQLiteErrorValues(t *testing.T) {
	db, err := sql.Open("sqlite3", "file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	defer db.Close()

	_, err = db.ExecContext(context.Background(), "SELECT * FROM missing_table")
	if err == nil {
		t.Fatal("ExecContext returned nil error for missing table")
	}

	var sqliteErr sqlite3.Error
	if !errors.As(err, &sqliteErr) {
		t.Fatalf("errors.As(%v, *sqlite3.Error) = false", err)
	}
	if sqliteErr.Code == 0 {
		t.Fatalf("sqlite error code = 0, want non-zero (%v)", sqliteErr)
	}
}

func TestUpdateHook(t *testing.T) {
	var mu sync.Mutex
	var events []struct {
		op        int
		dbName    string
		tableName string
		rowID     int64
	}

	driver := &sqlite3.SQLiteDriver{
		ConnectHook: func(conn *sqlite3.SQLiteConn) error {
			conn.SetUpdateHook(func(op int, dbName, tableName string, rowID int64) {
				mu.Lock()
				defer mu.Unlock()
				events = append(events, struct {
					op        int
					dbName    string
					tableName string
					rowID     int64
				}{op, dbName, tableName, rowID})
			})
			return nil
		},
	}

	connector, err := driver.OpenConnector("file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("OpenConnector: %v", err)
	}

	db := sql.OpenDB(connector)
	defer db.Close()

	ctx := context.Background()
	if _, err := db.ExecContext(ctx, "CREATE TABLE hook_test(id INTEGER PRIMARY KEY, name TEXT)"); err != nil {
		t.Fatalf("CREATE TABLE: %v", err)
	}
	if _, err := db.ExecContext(ctx, "INSERT INTO hook_test(name) VALUES('alice')"); err != nil {
		t.Fatalf("INSERT: %v", err)
	}

	mu.Lock()
	count := len(events)
	mu.Unlock()
	if count == 0 {
		t.Fatal("update hook was not called after INSERT")
	}

	mu.Lock()
	last := events[count-1]
	mu.Unlock()
	if last.op != sqlite3.OpInsert {
		t.Fatalf("update hook op = %d, want OpInsert (%d)", last.op, sqlite3.OpInsert)
	}
	if last.tableName != "hook_test" {
		t.Fatalf("update hook table = %q, want %q", last.tableName, "hook_test")
	}
	if last.rowID != 1 {
		t.Fatalf("update hook rowID = %d, want 1", last.rowID)
	}
}

func TestCommitHook(t *testing.T) {
	var mu sync.Mutex
	var commitCount int

	driver := &sqlite3.SQLiteDriver{
		ConnectHook: func(conn *sqlite3.SQLiteConn) error {
			conn.SetCommitHook(func() int {
				mu.Lock()
				defer mu.Unlock()
				commitCount++
				return 0
			})
			return nil
		},
	}

	connector, err := driver.OpenConnector("file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("OpenConnector: %v", err)
	}

	db := sql.OpenDB(connector)
	defer db.Close()

	ctx := context.Background()
	if _, err := db.ExecContext(ctx, "CREATE TABLE commit_test(id INTEGER PRIMARY KEY)"); err != nil {
		t.Fatalf("CREATE TABLE: %v", err)
	}

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("BeginTx: %v", err)
	}
	if _, err := tx.ExecContext(ctx, "INSERT INTO commit_test(id) VALUES(1)"); err != nil {
		t.Fatalf("INSERT: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("Commit: %v", err)
	}

	mu.Lock()
	got := commitCount
	mu.Unlock()
	if got == 0 {
		t.Fatal("commit hook was not called after COMMIT")
	}
}

func TestRollbackHook(t *testing.T) {
	var mu sync.Mutex
	var rollbackCount int

	driver := &sqlite3.SQLiteDriver{
		ConnectHook: func(conn *sqlite3.SQLiteConn) error {
			conn.SetRollbackHook(func() {
				mu.Lock()
				defer mu.Unlock()
				rollbackCount++
			})
			return nil
		},
	}

	connector, err := driver.OpenConnector("file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("OpenConnector: %v", err)
	}

	db := sql.OpenDB(connector)
	defer db.Close()

	ctx := context.Background()
	if _, err := db.ExecContext(ctx, "CREATE TABLE rollback_test(id INTEGER PRIMARY KEY)"); err != nil {
		t.Fatalf("CREATE TABLE: %v", err)
	}

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("BeginTx: %v", err)
	}
	if _, err := tx.ExecContext(ctx, "INSERT INTO rollback_test(id) VALUES(1)"); err != nil {
		t.Fatalf("INSERT: %v", err)
	}
	if err := tx.Rollback(); err != nil {
		t.Fatalf("Rollback: %v", err)
	}

	mu.Lock()
	got := rollbackCount
	mu.Unlock()
	if got == 0 {
		t.Fatal("rollback hook was not called after ROLLBACK")
	}
}

func TestHookClearWithNil(t *testing.T) {
	var mu sync.Mutex
	var called bool

	driver := &sqlite3.SQLiteDriver{
		ConnectHook: func(conn *sqlite3.SQLiteConn) error {
			conn.SetUpdateHook(func(op int, dbName, tableName string, rowID int64) {
				mu.Lock()
				defer mu.Unlock()
				called = true
			})
			// Immediately clear the hook.
			conn.SetUpdateHook(nil)
			return nil
		},
	}

	connector, err := driver.OpenConnector("file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("OpenConnector: %v", err)
	}

	db := sql.OpenDB(connector)
	defer db.Close()

	ctx := context.Background()
	if _, err := db.ExecContext(ctx, "CREATE TABLE nil_test(id INTEGER PRIMARY KEY)"); err != nil {
		t.Fatalf("CREATE TABLE: %v", err)
	}
	if _, err := db.ExecContext(ctx, "INSERT INTO nil_test(id) VALUES(1)"); err != nil {
		t.Fatalf("INSERT: %v", err)
	}

	mu.Lock()
	wasCalled := called
	mu.Unlock()
	if wasCalled {
		t.Fatal("update hook was called after being cleared with nil")
	}
}
