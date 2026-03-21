package sqlite3

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"fmt"
	"io"
	"math"
	"net/url"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unsafe"

	"github.com/johejo/purego-gen/sqlite3/sqlite3sys"
)

const driverName = "sqlite3"

// Hook operation types passed to SetUpdateHook callbacks.
const (
	OpInsert = int(sqlite3sys.SQLITE_INSERT)
	OpUpdate = int(sqlite3sys.SQLITE_UPDATE)
	OpDelete = int(sqlite3sys.SQLITE_DELETE)
)

func init() {
	sql.Register(driverName, &SQLiteDriver{})
}

type ErrNo int
type ErrNoExtended int

type Error struct {
	Code         ErrNo
	ExtendedCode ErrNoExtended
	err          string
}

func (err ErrNo) Error() string {
	return sqliteErrorString(int32(err))
}

func (err ErrNoExtended) Error() string {
	return sqliteErrorString(int32(err) & 0xff)
}

func (err Error) Error() string {
	if err.err != "" {
		return err.err
	}
	return sqliteErrorString(int32(err.Code))
}

type SQLiteDriver struct {
	ConnectHook func(*SQLiteConn) error
}

type connector struct {
	driver *SQLiteDriver
	dsn    connectionConfig
}

type SQLiteConn struct {
	db     *sqlite3sys.DB
	config connectionConfig

	mu     sync.Mutex
	closed bool

	registryMu sync.Mutex
	nextID     uintptr
	scalars    map[uintptr]*scalarFunction
	collations map[uintptr]*collationFunction

	// pinned hook callbacks to prevent GC of closures passed to purego.NewCallback
	updateHookCb   func(uintptr, int32, uintptr, uintptr, int64)
	commitHookCb   func(uintptr) int32
	rollbackHookCb func(uintptr)
}

type SQLiteStmt struct {
	conn      *SQLiteConn
	stmt      *sqlite3sys.Stmt
	ephemeral bool
	closed    bool
}

type SQLiteRows struct {
	stmt      *SQLiteStmt
	ctx       context.Context
	closeOnce sync.Once
	closed    bool
	names     []string
	declTypes []string
}

type SQLiteTx struct {
	conn *SQLiteConn
}

type sqliteResult struct {
	lastInsertID int64
	rowsAffected int64
}

type connectionConfig struct {
	filename    string
	flags       int32
	busyTimeout int32
	foreignKeys *bool
	journalMode string
	synchronous string
	txLock      string
	location    *time.Location
}

type scalarFunction struct {
	value      reflect.Value
	args       []func(*sqlite3sys.Value) (reflect.Value, error)
	returnFunc func(*sqlite3sys.Context, []reflect.Value)
}

type collationFunction struct {
	compare func(string, string) int
}

var (
	_ driver.Driver             = (*SQLiteDriver)(nil)
	_ driver.DriverContext      = (*SQLiteDriver)(nil)
	_ driver.Connector          = (*connector)(nil)
	_ driver.Conn               = (*SQLiteConn)(nil)
	_ driver.ConnPrepareContext = (*SQLiteConn)(nil)
	_ driver.ExecerContext      = (*SQLiteConn)(nil)
	_ driver.QueryerContext     = (*SQLiteConn)(nil)
	_ driver.ConnBeginTx        = (*SQLiteConn)(nil)
	_ driver.NamedValueChecker  = (*SQLiteConn)(nil)
	_ driver.Pinger             = (*SQLiteConn)(nil)
	_ driver.SessionResetter    = (*SQLiteConn)(nil)
	_ driver.Validator          = (*SQLiteConn)(nil)
	_ driver.Stmt               = (*SQLiteStmt)(nil)
	_ driver.StmtExecContext    = (*SQLiteStmt)(nil)
	_ driver.StmtQueryContext   = (*SQLiteStmt)(nil)
	_ driver.NamedValueChecker  = (*SQLiteStmt)(nil)
	_ driver.Rows               = (*SQLiteRows)(nil)
)

func (d *SQLiteDriver) Open(name string) (driver.Conn, error) {
	connector, err := d.OpenConnector(name)
	if err != nil {
		return nil, err
	}
	return connector.Connect(context.Background())
}

func (d *SQLiteDriver) OpenConnector(name string) (driver.Connector, error) {
	cfg, err := parseDSN(name)
	if err != nil {
		return nil, err
	}
	return &connector{driver: d, dsn: cfg}, nil
}

func (c *connector) Connect(_ context.Context) (driver.Conn, error) {
	if err := sqlite3sys.Load(); err != nil {
		return nil, err
	}

	conn := &SQLiteConn{
		config:     c.dsn,
		scalars:    make(map[uintptr]*scalarFunction),
		collations: make(map[uintptr]*collationFunction),
	}

	result := sqlite3sys.OpenV2(c.dsn.filename, c.dsn.flags, "", &conn.db)
	if result != sqlite3sys.SQLITE_OK {
		defer conn.forceClose()
		return nil, conn.errorFromResult(result)
	}

	if c.dsn.busyTimeout > 0 {
		if result := sqlite3sys.BusyTimeout(conn.db, c.dsn.busyTimeout); result != sqlite3sys.SQLITE_OK {
			defer conn.forceClose()
			return nil, conn.errorFromResult(result)
		}
	}
	if err := conn.applyPragmas(); err != nil {
		defer conn.forceClose()
		return nil, err
	}
	if c.driver != nil && c.driver.ConnectHook != nil {
		if err := c.driver.ConnectHook(conn); err != nil {
			defer conn.forceClose()
			return nil, err
		}
	}

	return conn, nil
}

func (c *connector) Driver() driver.Driver {
	if c.driver != nil {
		return c.driver
	}
	return &SQLiteDriver{}
}

func (c *SQLiteConn) Prepare(query string) (driver.Stmt, error) {
	return c.PrepareContext(context.Background(), query)
}

func (c *SQLiteConn) PrepareContext(ctx context.Context, query string) (driver.Stmt, error) {
	if err := c.checkUsable(); err != nil {
		return nil, err
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}

	stmt := &SQLiteStmt{conn: c}
	result := sqlite3sys.PrepareV2(c.db, query, &stmt.stmt)
	if result != sqlite3sys.SQLITE_OK {
		return nil, c.errorFromContext(result, ctx)
	}
	return stmt, nil
}

func (c *SQLiteConn) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return nil
	}
	c.closed = true

	result := sqlite3sys.CloseV2(c.db)
	c.db = nil
	if result != sqlite3sys.SQLITE_OK {
		return c.errorFromResult(result)
	}
	return nil
}

func (c *SQLiteConn) forceClose() {
	if c.db == nil {
		return
	}
	_ = sqlite3sys.CloseV2(c.db)
	c.db = nil
	c.closed = true
}

func (c *SQLiteConn) Begin() (driver.Tx, error) {
	return c.BeginTx(context.Background(), driver.TxOptions{})
}

func (c *SQLiteConn) BeginTx(ctx context.Context, opts driver.TxOptions) (driver.Tx, error) {
	if err := c.checkUsable(); err != nil {
		return nil, err
	}
	if opts.ReadOnly {
		return nil, fmt.Errorf("sqlite3: read-only transactions are not supported")
	}
	if opts.Isolation != driver.IsolationLevel(sql.LevelDefault) &&
		opts.Isolation != driver.IsolationLevel(sql.LevelSerializable) {
		return nil, fmt.Errorf("sqlite3: unsupported isolation level %d", opts.Isolation)
	}

	beginSQL := "BEGIN"
	switch c.config.txLock {
	case "", "deferred":
	case "immediate":
		beginSQL = "BEGIN IMMEDIATE"
	case "exclusive":
		beginSQL = "BEGIN EXCLUSIVE"
	default:
		return nil, fmt.Errorf("sqlite3: unsupported _txlock value %q", c.config.txLock)
	}

	if _, err := c.execTransient(ctx, beginSQL, nil); err != nil {
		return nil, err
	}
	return &SQLiteTx{conn: c}, nil
}

func (c *SQLiteConn) Ping(ctx context.Context) error {
	_, err := c.execTransient(ctx, "SELECT 1", nil)
	return err
}

func (c *SQLiteConn) ResetSession(context.Context) error {
	if c.closed {
		return driver.ErrBadConn
	}
	return nil
}

func (c *SQLiteConn) IsValid() bool {
	return !c.closed && c.db != nil
}

func (c *SQLiteConn) CheckNamedValue(nv *driver.NamedValue) error {
	value, err := normalizeValue(nv.Value)
	if err != nil {
		return err
	}
	nv.Value = value
	return nil
}

func (c *SQLiteConn) ExecContext(
	ctx context.Context,
	query string,
	args []driver.NamedValue,
) (driver.Result, error) {
	return c.execTransient(ctx, query, args)
}

func (c *SQLiteConn) QueryContext(
	ctx context.Context,
	query string,
	args []driver.NamedValue,
) (driver.Rows, error) {
	if err := c.checkUsable(); err != nil {
		return nil, err
	}
	stmt, err := c.prepareEphemeral(ctx, query)
	if err != nil {
		return nil, err
	}
	if err := stmt.bindNamedValues(args); err != nil {
		_ = stmt.Close()
		return nil, err
	}
	rows, err := stmt.newRows(ctx)
	if err != nil {
		_ = stmt.Close()
		return nil, err
	}
	return rows, nil
}

func (c *SQLiteConn) RegisterFunc(name string, fn any, pure bool) error {
	compiled, err := compileScalarFunction(fn)
	if err != nil {
		return err
	}

	id := c.nextRegistryID()
	c.registryMu.Lock()
	c.scalars[id] = compiled
	c.registryMu.Unlock()

	flags := int32(sqlite3sys.SQLITE_UTF8)
	if pure {
		flags |= sqlite3sys.SQLITE_DETERMINISTIC
	}
	result := sqlite3sys.CreateFunctionV2Callbacks(
		c.db,
		name,
		int32(len(compiled.args)),
		flags,
		id,
		func(ctx *sqlite3sys.Context, argc int32, values **sqlite3sys.Value) {
			c.invokeScalar(ctx, argc, values)
		},
		func(userData uintptr) {
			c.unregisterScalar(userData)
		},
	)
	if result != sqlite3sys.SQLITE_OK {
		c.unregisterScalar(id)
		return c.errorFromResult(result)
	}
	return nil
}

func (c *SQLiteConn) RegisterCollation(name string, cmp func(string, string) int) error {
	if cmp == nil {
		return fmt.Errorf("sqlite3: collation comparator must not be nil")
	}

	id := c.nextRegistryID()
	c.registryMu.Lock()
	c.collations[id] = &collationFunction{compare: cmp}
	c.registryMu.Unlock()

	result := sqlite3sys.CreateCollationV2Callbacks(
		c.db,
		name,
		sqlite3sys.SQLITE_UTF8,
		id,
		func(userData uintptr, leftLen int32, left uintptr, rightLen int32, right uintptr) int32 {
			fn := c.lookupCollation(userData)
			if fn == nil {
				return 0
			}
			leftBytes := rawBytes(left, leftLen)
			rightBytes := rawBytes(right, rightLen)
			return int32(fn.compare(string(leftBytes), string(rightBytes)))
		},
		func(userData uintptr) {
			c.unregisterCollation(userData)
		},
	)
	if result != sqlite3sys.SQLITE_OK {
		c.unregisterCollation(id)
		return c.errorFromResult(result)
	}
	return nil
}

func (tx *SQLiteTx) Commit() error {
	_, err := tx.conn.execTransient(context.Background(), "COMMIT", nil)
	return err
}

func (tx *SQLiteTx) Rollback() error {
	_, err := tx.conn.execTransient(context.Background(), "ROLLBACK", nil)
	return err
}

func (s *SQLiteStmt) Close() error {
	if s.closed {
		return nil
	}
	s.closed = true

	result := sqlite3sys.Finalize(s.stmt)
	s.stmt = nil
	if result != sqlite3sys.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	return nil
}

func (s *SQLiteStmt) NumInput() int {
	return int(sqlite3sys.BindParameterCount(s.stmt))
}

func (s *SQLiteStmt) Exec(args []driver.Value) (driver.Result, error) {
	return s.ExecContext(context.Background(), valuesToNamedValues(args))
}

func (s *SQLiteStmt) Query(args []driver.Value) (driver.Rows, error) {
	return s.QueryContext(context.Background(), valuesToNamedValues(args))
}

func (s *SQLiteStmt) CheckNamedValue(nv *driver.NamedValue) error {
	return s.conn.CheckNamedValue(nv)
}

func (s *SQLiteStmt) ExecContext(
	ctx context.Context,
	args []driver.NamedValue,
) (driver.Result, error) {
	if err := s.bindNamedValues(args); err != nil {
		return nil, err
	}
	result, err := s.execBound(ctx)
	if resetErr := s.resetForReuse(); err == nil && resetErr != nil {
		err = resetErr
	}
	return result, err
}

func (s *SQLiteStmt) QueryContext(
	ctx context.Context,
	args []driver.NamedValue,
) (driver.Rows, error) {
	if err := s.bindNamedValues(args); err != nil {
		return nil, err
	}
	return s.newRows(ctx)
}

func (r *SQLiteRows) Columns() []string {
	out := make([]string, len(r.names))
	copy(out, r.names)
	return out
}

func (r *SQLiteRows) Close() error {
	var err error
	r.closeOnce.Do(func() {
		r.closed = true
		if r.stmt.ephemeral {
			err = r.stmt.Close()
			return
		}
		err = r.stmt.resetForReuse()
	})
	return err
}

func (r *SQLiteRows) Next(dest []driver.Value) error {
	if r.closed {
		return io.EOF
	}

	cancel := interruptWatcher(r.ctx, r.stmt.conn.db)
	result := sqlite3sys.Step(r.stmt.stmt)
	interrupted := cancel.stop()

	switch result {
	case sqlite3sys.SQLITE_ROW:
		for index := range dest {
			value, err := r.columnValue(index)
			if err != nil {
				return err
			}
			dest[index] = value
		}
		return nil
	case sqlite3sys.SQLITE_DONE:
		_ = r.Close()
		return io.EOF
	case sqlite3sys.SQLITE_INTERRUPT:
		if interrupted && r.ctx != nil && r.ctx.Err() != nil {
			_ = r.Close()
			return r.ctx.Err()
		}
		fallthrough
	default:
		err := r.stmt.conn.errorFromResult(result)
		_ = r.Close()
		return err
	}
}

func (r *SQLiteRows) ColumnTypeDatabaseTypeName(index int) string {
	return normalizeDeclType(r.declTypes[index])
}

func (r *SQLiteRows) ColumnTypeScanType(index int) reflect.Type {
	switch databaseType := r.ColumnTypeDatabaseTypeName(index); databaseType {
	case "INT", "INTEGER", "BIGINT":
		return reflect.TypeOf(int64(0))
	case "REAL", "DOUBLE", "FLOAT", "NUMERIC", "DECIMAL":
		return reflect.TypeOf(float64(0))
	case "BLOB":
		return reflect.TypeOf([]byte(nil))
	case "DATE", "DATETIME", "TIMESTAMP":
		return reflect.TypeOf(time.Time{})
	default:
		return reflect.TypeOf("")
	}
}

func (r *SQLiteRows) ColumnTypeLength(int) (int64, bool)  { return 0, false }
func (r *SQLiteRows) ColumnTypeNullable(int) (bool, bool) { return true, false }
func (r *SQLiteRows) ColumnTypePrecisionScale(int) (int64, int64, bool) {
	return 0, 0, false
}

func (r *SQLiteRows) columnValue(index int) (driver.Value, error) {
	column := int32(index)
	switch sqlite3sys.ColumnType(r.stmt.stmt, column) {
	case sqlite3sys.SQLITE_INTEGER:
		return sqlite3sys.ColumnInt64(r.stmt.stmt, column), nil
	case sqlite3sys.SQLITE_FLOAT:
		return sqlite3sys.ColumnDouble(r.stmt.stmt, column), nil
	case sqlite3sys.SQLITE_TEXT:
		text := sqlite3sys.ColumnText(r.stmt.stmt, column)
		if r.stmt.conn.config.location != nil && looksLikeTimeType(r.declTypes[index]) {
			parsed, ok := parseSQLiteTime(text, r.stmt.conn.config.location)
			if ok {
				return parsed, nil
			}
		}
		return text, nil
	case sqlite3sys.SQLITE_BLOB:
		return sqlite3sys.ColumnBlobBytes(r.stmt.stmt, column), nil
	case sqlite3sys.SQLITE_NULL:
		return nil, nil
	default:
		return sqlite3sys.ColumnText(r.stmt.stmt, column), nil
	}
}

func (s *SQLiteStmt) bindNamedValues(args []driver.NamedValue) error {
	if err := s.conn.checkUsable(); err != nil {
		return err
	}
	if result := sqlite3sys.Reset(s.stmt); result != sqlite3sys.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	if result := sqlite3sys.ClearBindings(s.stmt); result != sqlite3sys.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	for _, arg := range args {
		index, err := s.resolveIndex(arg)
		if err != nil {
			return err
		}
		if err := s.bindValue(index, arg.Value); err != nil {
			return err
		}
	}
	return nil
}

func (s *SQLiteStmt) resolveIndex(arg driver.NamedValue) (int32, error) {
	if arg.Name == "" {
		return int32(arg.Ordinal), nil
	}

	candidates := []string{arg.Name, ":" + arg.Name, "@" + arg.Name, "$" + arg.Name}
	for _, name := range candidates {
		if index := sqlite3sys.BindParameterIndex(s.stmt, name); index != 0 {
			return index, nil
		}
	}
	return 0, fmt.Errorf("sqlite3: unknown named parameter %q", arg.Name)
}

func (s *SQLiteStmt) bindValue(index int32, value any) error {
	switch v := value.(type) {
	case nil:
		return s.bindResult(sqlite3sys.BindNull(s.stmt, index))
	case int64:
		return s.bindResult(sqlite3sys.BindInt64(s.stmt, index, v))
	case float64:
		return s.bindResult(sqlite3sys.BindDouble(s.stmt, index, v))
	case bool:
		intValue := int64(0)
		if v {
			intValue = 1
		}
		return s.bindResult(sqlite3sys.BindInt64(s.stmt, index, intValue))
	case string:
		return s.bindResult(sqlite3sys.BindText(s.stmt, index, v, sqlite3sys.SQLITE_TRANSIENT))
	case []byte:
		return s.bindResult(sqlite3sys.BindBlobBytes(s.stmt, index, v, sqlite3sys.SQLITE_TRANSIENT))
	case time.Time:
		return s.bindResult(sqlite3sys.BindText(s.stmt, index, formatSQLiteTime(v), sqlite3sys.SQLITE_TRANSIENT))
	default:
		normalized, err := normalizeValue(v)
		if err != nil {
			return err
		}
		if normalized == value {
			return fmt.Errorf("sqlite3: unsupported bind parameter type %T", value)
		}
		return s.bindValue(index, normalized)
	}
}

func (s *SQLiteStmt) bindResult(result int32) error {
	if result != sqlite3sys.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	return nil
}

func (s *SQLiteStmt) execBound(ctx context.Context) (driver.Result, error) {
	cancel := interruptWatcher(ctx, s.conn.db)
	for {
		result := sqlite3sys.Step(s.stmt)
		switch result {
		case sqlite3sys.SQLITE_ROW:
			continue
		case sqlite3sys.SQLITE_DONE:
			cancel.stop()
			return sqliteResult{
				lastInsertID: sqlite3sys.LastInsertRowid(s.conn.db),
				rowsAffected: sqlite3sys.Changes64(s.conn.db),
			}, nil
		case sqlite3sys.SQLITE_INTERRUPT:
			if cancel.stop() && ctx != nil && ctx.Err() != nil {
				return nil, ctx.Err()
			}
			return nil, s.conn.errorFromResult(result)
		default:
			cancel.stop()
			return nil, s.conn.errorFromResult(result)
		}
	}
}

func (s *SQLiteStmt) newRows(ctx context.Context) (*SQLiteRows, error) {
	count := int(sqlite3sys.ColumnCount(s.stmt))
	rows := &SQLiteRows{
		stmt:      s,
		ctx:       ctx,
		names:     make([]string, count),
		declTypes: make([]string, count),
	}
	for index := 0; index < count; index++ {
		column := int32(index)
		rows.names[index] = sqlite3sys.ColumnName(s.stmt, column)
		rows.declTypes[index] = sqlite3sys.ColumnDeclType(s.stmt, column)
	}
	return rows, nil
}

func (s *SQLiteStmt) resetForReuse() error {
	if s.closed || s.stmt == nil {
		return nil
	}
	if result := sqlite3sys.Reset(s.stmt); result != sqlite3sys.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	if result := sqlite3sys.ClearBindings(s.stmt); result != sqlite3sys.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	if s.ephemeral {
		return s.Close()
	}
	return nil
}

func (c *SQLiteConn) prepareEphemeral(ctx context.Context, query string) (*SQLiteStmt, error) {
	stmtValue, err := c.PrepareContext(ctx, query)
	if err != nil {
		return nil, err
	}
	stmt := stmtValue.(*SQLiteStmt)
	stmt.ephemeral = true
	return stmt, nil
}

func (c *SQLiteConn) execTransient(
	ctx context.Context,
	query string,
	args []driver.NamedValue,
) (driver.Result, error) {
	stmt, err := c.prepareEphemeral(ctx, query)
	if err != nil {
		return nil, err
	}
	defer stmt.Close()

	if err := stmt.bindNamedValues(args); err != nil {
		return nil, err
	}
	return stmt.execBound(ctx)
}

func (c *SQLiteConn) applyPragmas() error {
	if c.config.foreignKeys != nil {
		value := "OFF"
		if *c.config.foreignKeys {
			value = "ON"
		}
		if _, err := c.execTransient(context.Background(), "PRAGMA foreign_keys = "+value, nil); err != nil {
			return err
		}
	}
	if c.config.journalMode != "" {
		if _, err := c.execTransient(
			context.Background(),
			"PRAGMA journal_mode = "+c.config.journalMode,
			nil,
		); err != nil {
			return err
		}
	}
	if c.config.synchronous != "" {
		if _, err := c.execTransient(
			context.Background(),
			"PRAGMA synchronous = "+c.config.synchronous,
			nil,
		); err != nil {
			return err
		}
	}
	return nil
}

func (c *SQLiteConn) checkUsable() error {
	if c.closed || c.db == nil {
		return driver.ErrBadConn
	}
	return nil
}

func (c *SQLiteConn) errorFromContext(result int32, ctx context.Context) error {
	if result == sqlite3sys.SQLITE_INTERRUPT && ctx != nil && ctx.Err() != nil {
		return ctx.Err()
	}
	return c.errorFromResult(result)
}

func (c *SQLiteConn) errorFromResult(result int32) error {
	if result == sqlite3sys.SQLITE_OK {
		return nil
	}
	message := sqliteErrorString(result)
	if c != nil && c.db != nil {
		if dbMessage := sqlite3sys.Errmsg(c.db); dbMessage != "" {
			message = dbMessage
		}
	}
	return Error{
		Code:         ErrNo(result & 0xff),
		ExtendedCode: ErrNoExtended(result),
		err:          message,
	}
}

func (r sqliteResult) LastInsertId() (int64, error) { return r.lastInsertID, nil }
func (r sqliteResult) RowsAffected() (int64, error) { return r.rowsAffected, nil }

func parseDSN(name string) (connectionConfig, error) {
	cfg := connectionConfig{
		filename: name,
		flags:    sqlite3sys.SQLITE_OPEN_READWRITE | sqlite3sys.SQLITE_OPEN_CREATE | sqlite3sys.SQLITE_OPEN_FULLMUTEX,
		txLock:   "deferred",
	}
	if name == "" {
		cfg.filename = ":memory:"
	}

	base, query := splitDSN(name)
	values, err := url.ParseQuery(query)
	if err != nil {
		return cfg, fmt.Errorf("sqlite3: parse dsn query: %w", err)
	}

	preserved := url.Values{}
	for key, value := range values {
		switch key {
		case "_busy_timeout", "_timeout":
			timeoutValue := firstValue(value)
			timeout, err := strconv.Atoi(timeoutValue)
			if err != nil {
				return cfg, fmt.Errorf("sqlite3: invalid busy timeout %q", timeoutValue)
			}
			cfg.busyTimeout = int32(timeout)
		case "_foreign_keys", "_fk":
			parsed, err := parseBoolOption(firstValue(value))
			if err != nil {
				return cfg, err
			}
			cfg.foreignKeys = &parsed
		case "_journal_mode", "_journal":
			cfg.journalMode = strings.ToUpper(firstValue(value))
		case "_synchronous", "_sync":
			cfg.synchronous = strings.ToUpper(firstValue(value))
		case "_txlock":
			cfg.txLock = strings.ToLower(firstValue(value))
		case "loc", "_loc":
			location, err := parseLocation(firstValue(value))
			if err != nil {
				return cfg, err
			}
			cfg.location = location
		case "mode":
			mode := strings.ToLower(firstValue(value))
			switch mode {
			case "ro":
				cfg.flags = sqlite3sys.SQLITE_OPEN_READONLY | sqlite3sys.SQLITE_OPEN_URI | sqlite3sys.SQLITE_OPEN_FULLMUTEX
			case "rw":
				cfg.flags = sqlite3sys.SQLITE_OPEN_READWRITE | sqlite3sys.SQLITE_OPEN_URI | sqlite3sys.SQLITE_OPEN_FULLMUTEX
			case "rwc":
				cfg.flags = sqlite3sys.SQLITE_OPEN_READWRITE | sqlite3sys.SQLITE_OPEN_CREATE | sqlite3sys.SQLITE_OPEN_URI | sqlite3sys.SQLITE_OPEN_FULLMUTEX
			case "memory":
				cfg.flags = sqlite3sys.SQLITE_OPEN_READWRITE | sqlite3sys.SQLITE_OPEN_CREATE | sqlite3sys.SQLITE_OPEN_MEMORY | sqlite3sys.SQLITE_OPEN_URI | sqlite3sys.SQLITE_OPEN_FULLMUTEX
			default:
				return cfg, fmt.Errorf("sqlite3: unsupported mode %q", mode)
			}
			preserved[key] = value
		case "cache":
			preserved[key] = value
			cfg.flags |= sqlite3sys.SQLITE_OPEN_URI
		default:
			preserved[key] = value
			if !strings.HasPrefix(key, "_") {
				cfg.flags |= sqlite3sys.SQLITE_OPEN_URI
			}
		}
	}

	cfg.filename = rebuildFilename(base, preserved)
	if strings.HasPrefix(cfg.filename, "file:") {
		cfg.flags |= sqlite3sys.SQLITE_OPEN_URI
	}
	return cfg, nil
}

func splitDSN(name string) (string, string) {
	if idx := strings.IndexByte(name, '?'); idx >= 0 {
		return name[:idx], name[idx+1:]
	}
	return name, ""
}

func rebuildFilename(base string, query url.Values) string {
	if len(query) == 0 {
		return base
	}
	encoded := query.Encode()
	if strings.HasPrefix(base, "file:") {
		return base + "?" + encoded
	}
	if base == ":memory:" {
		return "file::memory:?" + encoded
	}
	return "file:" + base + "?" + encoded
}

func parseBoolOption(value string) (bool, error) {
	switch strings.ToLower(value) {
	case "1", "true", "yes", "on":
		return true, nil
	case "0", "false", "no", "off":
		return false, nil
	default:
		return false, fmt.Errorf("sqlite3: invalid boolean value %q", value)
	}
}

func parseLocation(value string) (*time.Location, error) {
	if value == "" {
		return nil, nil
	}
	if value == "auto" {
		return time.Local, nil
	}
	location, err := time.LoadLocation(value)
	if err != nil {
		return nil, fmt.Errorf("sqlite3: load location %q: %w", value, err)
	}
	return location, nil
}

func firstValue(values []string) string {
	if len(values) == 0 {
		return ""
	}
	return values[0]
}

func valuesToNamedValues(args []driver.Value) []driver.NamedValue {
	out := make([]driver.NamedValue, len(args))
	for index, arg := range args {
		out[index] = driver.NamedValue{Ordinal: index + 1, Value: arg}
	}
	return out
}

func normalizeValue(value any) (any, error) {
	switch v := value.(type) {
	case nil, int64, float64, bool, string, []byte, time.Time:
		return v, nil
	case int:
		return int64(v), nil
	case int8:
		return int64(v), nil
	case int16:
		return int64(v), nil
	case int32:
		return int64(v), nil
	case uint:
		if uint64(v) > math.MaxInt64 {
			return nil, fmt.Errorf("sqlite3: uint value %d overflows int64", v)
		}
		return int64(v), nil
	case uint8:
		return int64(v), nil
	case uint16:
		return int64(v), nil
	case uint32:
		return int64(v), nil
	case uint64:
		if v > math.MaxInt64 {
			return nil, fmt.Errorf("sqlite3: uint64 value %d overflows int64", v)
		}
		return int64(v), nil
	case float32:
		return float64(v), nil
	case driver.Valuer:
		resolved, err := v.Value()
		if err != nil {
			return nil, err
		}
		return normalizeValue(resolved)
	default:
		return nil, fmt.Errorf("sqlite3: unsupported value type %T", value)
	}
}

func compileScalarFunction(fn any) (*scalarFunction, error) {
	value := reflect.ValueOf(fn)
	if !value.IsValid() || value.Kind() != reflect.Func {
		return nil, fmt.Errorf("sqlite3: RegisterFunc expects a function, got %T", fn)
	}

	fnType := value.Type()
	if fnType.IsVariadic() {
		return nil, fmt.Errorf("sqlite3: variadic functions are not supported")
	}

	args := make([]func(*sqlite3sys.Value) (reflect.Value, error), fnType.NumIn())
	for index := range args {
		decoder, err := buildValueDecoder(fnType.In(index))
		if err != nil {
			return nil, fmt.Errorf("sqlite3: argument %d: %w", index, err)
		}
		args[index] = decoder
	}

	returnFunc, err := buildReturnEncoder(fnType)
	if err != nil {
		return nil, err
	}

	return &scalarFunction{
		value:      value,
		args:       args,
		returnFunc: returnFunc,
	}, nil
}

func buildValueDecoder(target reflect.Type) (func(*sqlite3sys.Value) (reflect.Value, error), error) {
	switch {
	case target.Kind() == reflect.String:
		return func(value *sqlite3sys.Value) (reflect.Value, error) {
			return reflect.ValueOf(sqlite3sys.ValueText(value)).Convert(target), nil
		}, nil
	case target.Kind() == reflect.Slice && target.Elem().Kind() == reflect.Uint8:
		return func(value *sqlite3sys.Value) (reflect.Value, error) {
			return reflect.ValueOf(sqlite3sys.ValueBlobBytes(value)).Convert(target), nil
		}, nil
	case target.Kind() == reflect.Bool:
		return func(value *sqlite3sys.Value) (reflect.Value, error) {
			return reflect.ValueOf(sqlite3sys.ValueInt64(value) != 0).Convert(target), nil
		}, nil
	case isSignedInt(target.Kind()):
		return func(value *sqlite3sys.Value) (reflect.Value, error) {
			return reflect.ValueOf(sqlite3sys.ValueInt64(value)).Convert(target), nil
		}, nil
	case isUnsignedInt(target.Kind()):
		return func(value *sqlite3sys.Value) (reflect.Value, error) {
			number := sqlite3sys.ValueInt64(value)
			if number < 0 {
				return reflect.Value{}, fmt.Errorf("negative value %d for unsigned integer", number)
			}
			return reflect.ValueOf(uint64(number)).Convert(target), nil
		}, nil
	case target.Kind() == reflect.Float32 || target.Kind() == reflect.Float64:
		return func(value *sqlite3sys.Value) (reflect.Value, error) {
			return reflect.ValueOf(sqlite3sys.ValueDouble(value)).Convert(target), nil
		}, nil
	case target == reflect.TypeOf(time.Time{}):
		return func(value *sqlite3sys.Value) (reflect.Value, error) {
			text := sqlite3sys.ValueText(value)
			parsed, ok := parseSQLiteTime(text, time.Local)
			if !ok {
				return reflect.Value{}, fmt.Errorf("cannot parse %q as time.Time", text)
			}
			return reflect.ValueOf(parsed), nil
		}, nil
	default:
		return nil, fmt.Errorf("unsupported function argument type %s", target)
	}
}

func buildReturnEncoder(fnType reflect.Type) (func(*sqlite3sys.Context, []reflect.Value), error) {
	switch fnType.NumOut() {
	case 0:
		return func(ctx *sqlite3sys.Context, _ []reflect.Value) {
			sqlite3sys.ResultNull(ctx)
		}, nil
	case 1:
		return func(ctx *sqlite3sys.Context, results []reflect.Value) {
			encodeResultValue(ctx, results[0], nil)
		}, nil
	case 2:
		if !fnType.Out(1).Implements(reflect.TypeOf((*error)(nil)).Elem()) {
			return nil, fmt.Errorf("sqlite3: second return value must be error")
		}
		return func(ctx *sqlite3sys.Context, results []reflect.Value) {
			var err error
			if !results[1].IsNil() {
				err = results[1].Interface().(error)
			}
			encodeResultValue(ctx, results[0], err)
		}, nil
	default:
		return nil, fmt.Errorf("sqlite3: functions may return at most value or value,error")
	}
}

func encodeResultValue(ctx *sqlite3sys.Context, value reflect.Value, err error) {
	if err != nil {
		sqlite3sys.ResultError(ctx, err.Error())
		return
	}

	if !value.IsValid() {
		sqlite3sys.ResultNull(ctx)
		return
	}
	if value.Kind() == reflect.Interface && !value.IsNil() {
		value = value.Elem()
	}
	if value.Kind() == reflect.Pointer {
		if value.IsNil() {
			sqlite3sys.ResultNull(ctx)
			return
		}
		value = value.Elem()
	}

	switch {
	case value.Kind() == reflect.String:
		sqlite3sys.ResultText(ctx, value.String(), sqlite3sys.SQLITE_TRANSIENT)
	case value.Kind() == reflect.Slice && value.Type().Elem().Kind() == reflect.Uint8:
		sqlite3sys.ResultBlobBytes(ctx, append([]byte(nil), value.Bytes()...), sqlite3sys.SQLITE_TRANSIENT)
	case value.Kind() == reflect.Bool:
		boolValue := int64(0)
		if value.Bool() {
			boolValue = 1
		}
		sqlite3sys.ResultInt64(ctx, boolValue)
	case isSignedInt(value.Kind()):
		sqlite3sys.ResultInt64(ctx, value.Int())
	case isUnsignedInt(value.Kind()):
		sqlite3sys.ResultInt64(ctx, int64(value.Uint()))
	case value.Kind() == reflect.Float32 || value.Kind() == reflect.Float64:
		sqlite3sys.ResultDouble(ctx, value.Convert(reflect.TypeOf(float64(0))).Float())
	case value.Type() == reflect.TypeOf(time.Time{}):
		sqlite3sys.ResultText(ctx, formatSQLiteTime(value.Interface().(time.Time)), sqlite3sys.SQLITE_TRANSIENT)
	default:
		sqlite3sys.ResultError(ctx, "unsupported Go return type")
	}
}

func (c *SQLiteConn) invokeScalar(ctx *sqlite3sys.Context, argc int32, values **sqlite3sys.Value) {
	function := c.lookupScalar(sqlite3sys.UserData(ctx))
	if function == nil {
		sqlite3sys.ResultError(ctx, "sqlite3: function registry entry not found")
		return
	}
	if int(argc) != len(function.args) {
		sqlite3sys.ResultError(ctx, "sqlite3: unexpected argument count")
		return
	}

	sqliteValues := unsafe.Slice(values, int(argc))
	callArgs := make([]reflect.Value, len(sqliteValues))
	for index := range sqliteValues {
		decoded, err := function.args[index](sqliteValues[index])
		if err != nil {
			sqlite3sys.ResultError(ctx, err.Error())
			return
		}
		callArgs[index] = decoded
	}

	results := function.value.Call(callArgs)
	function.returnFunc(ctx, results)
}

func (c *SQLiteConn) nextRegistryID() uintptr {
	c.registryMu.Lock()
	defer c.registryMu.Unlock()
	c.nextID++
	return c.nextID
}

func (c *SQLiteConn) lookupScalar(id uintptr) *scalarFunction {
	c.registryMu.Lock()
	defer c.registryMu.Unlock()
	return c.scalars[id]
}

func (c *SQLiteConn) unregisterScalar(id uintptr) {
	c.registryMu.Lock()
	defer c.registryMu.Unlock()
	delete(c.scalars, id)
}

func (c *SQLiteConn) lookupCollation(id uintptr) *collationFunction {
	c.registryMu.Lock()
	defer c.registryMu.Unlock()
	return c.collations[id]
}

func (c *SQLiteConn) unregisterCollation(id uintptr) {
	c.registryMu.Lock()
	defer c.registryMu.Unlock()
	delete(c.collations, id)
}

// SetUpdateHook registers or clears the update hook for this connection.
// The callback receives the operation type (SQLITE_INSERT, SQLITE_UPDATE, SQLITE_DELETE),
// the database name, table name, and the rowid of the affected row.
// Pass nil to clear a previously set hook.
func (c *SQLiteConn) SetUpdateHook(callback func(op int, dbName, tableName string, rowID int64)) {
	if callback == nil {
		c.updateHookCb = nil
		sqlite3sys.UpdateHook(c.db, nil, 0)
		return
	}
	cb := func(_ uintptr, op int32, dbNamePtr uintptr, tableNamePtr uintptr, rowID int64) {
		dbName := ptrToString(dbNamePtr)
		tableName := ptrToString(tableNamePtr)
		callback(int(op), dbName, tableName, rowID)
	}
	c.updateHookCb = cb
	sqlite3sys.UpdateHook(c.db, cb, 0)
}

// SetCommitHook registers or clears the commit hook for this connection.
// The callback is invoked when a transaction is about to be committed.
// Return non-zero to convert the commit into a rollback.
// Pass nil to clear a previously set hook.
func (c *SQLiteConn) SetCommitHook(callback func() int) {
	if callback == nil {
		c.commitHookCb = nil
		sqlite3sys.CommitHook(c.db, nil, 0)
		return
	}
	cb := func(_ uintptr) int32 {
		return int32(callback())
	}
	c.commitHookCb = cb
	sqlite3sys.CommitHook(c.db, cb, 0)
}

// SetRollbackHook registers or clears the rollback hook for this connection.
// The callback is invoked when a transaction is rolled back.
// Pass nil to clear a previously set hook.
func (c *SQLiteConn) SetRollbackHook(callback func()) {
	if callback == nil {
		c.rollbackHookCb = nil
		sqlite3sys.RollbackHook(c.db, nil, 0)
		return
	}
	cb := func(_ uintptr) {
		callback()
	}
	c.rollbackHookCb = cb
	sqlite3sys.RollbackHook(c.db, cb, 0)
}

type cancelState struct {
	done        chan struct{}
	interrupted atomic.Bool
}

func interruptWatcher(ctx context.Context, db *sqlite3sys.DB) *cancelState {
	state := &cancelState{done: make(chan struct{})}
	if ctx == nil || ctx.Done() == nil || db == nil {
		close(state.done)
		return state
	}
	go func() {
		select {
		case <-ctx.Done():
			state.interrupted.Store(true)
			sqlite3sys.Interrupt(db)
		case <-state.done:
		}
	}()
	return state
}

func (c *cancelState) stop() bool {
	select {
	case <-c.done:
	default:
		close(c.done)
	}
	return c.interrupted.Load()
}

func sqliteErrorString(code int32) string {
	switch code & 0xff {
	case sqlite3sys.SQLITE_ERROR:
		return "SQL error or missing database"
	case sqlite3sys.SQLITE_INTERNAL:
		return "internal logic error in SQLite"
	case sqlite3sys.SQLITE_PERM:
		return "access permission denied"
	case sqlite3sys.SQLITE_ABORT:
		return "callback requested abort"
	case sqlite3sys.SQLITE_BUSY:
		return "database is locked"
	case sqlite3sys.SQLITE_LOCKED:
		return "table is locked"
	case sqlite3sys.SQLITE_NOMEM:
		return "out of memory"
	case sqlite3sys.SQLITE_READONLY:
		return "attempt to write a readonly database"
	case sqlite3sys.SQLITE_INTERRUPT:
		return "operation interrupted"
	case sqlite3sys.SQLITE_IOERR:
		return "disk I/O error"
	case sqlite3sys.SQLITE_CORRUPT:
		return "database disk image is malformed"
	case sqlite3sys.SQLITE_NOTFOUND:
		return "unknown opcode"
	case sqlite3sys.SQLITE_FULL:
		return "database or disk is full"
	case sqlite3sys.SQLITE_CANTOPEN:
		return "unable to open database file"
	case sqlite3sys.SQLITE_PROTOCOL:
		return "locking protocol error"
	case sqlite3sys.SQLITE_EMPTY:
		return "database is empty"
	case sqlite3sys.SQLITE_SCHEMA:
		return "database schema changed"
	case sqlite3sys.SQLITE_TOOBIG:
		return "string or blob too big"
	case sqlite3sys.SQLITE_CONSTRAINT:
		return "constraint failed"
	case sqlite3sys.SQLITE_MISMATCH:
		return "datatype mismatch"
	case sqlite3sys.SQLITE_MISUSE:
		return "library routine called out of sequence"
	case sqlite3sys.SQLITE_NOLFS:
		return "large file support unavailable"
	case sqlite3sys.SQLITE_AUTH:
		return "authorization denied"
	case sqlite3sys.SQLITE_FORMAT:
		return "auxiliary database format error"
	case sqlite3sys.SQLITE_RANGE:
		return "bind or column index out of range"
	case sqlite3sys.SQLITE_NOTADB:
		return "file is not a database"
	default:
		return fmt.Sprintf("sqlite result code %d", code)
	}
}

func ptrToString(ptr uintptr) string {
	if ptr == 0 {
		return ""
	}
	base := unsafe.Add(unsafe.Pointer(nil), ptr)
	var length int
	for {
		if *(*byte)(unsafe.Add(base, length)) == 0 {
			break
		}
		length++
	}
	return string(unsafe.Slice((*byte)(base), length))
}

func rawBytes(ptr uintptr, length int32) []byte {
	if ptr == 0 || length <= 0 {
		return nil
	}
	return unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), ptr)), int(length))
}

func normalizeDeclType(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	value = strings.ToUpper(value)
	if index := strings.IndexByte(value, '('); index >= 0 {
		value = value[:index]
	}
	return strings.TrimSpace(value)
}

func looksLikeTimeType(value string) bool {
	normalized := normalizeDeclType(value)
	return normalized == "DATE" || normalized == "DATETIME" || normalized == "TIMESTAMP"
}

func parseSQLiteTime(value string, location *time.Location) (time.Time, bool) {
	layouts := []string{
		time.RFC3339Nano,
		"2006-01-02 15:04:05.999999999-07:00",
		"2006-01-02 15:04:05.999999999",
		"2006-01-02 15:04:05",
		"2006-01-02",
	}
	for _, layout := range layouts {
		var (
			parsed time.Time
			err    error
		)
		if strings.Contains(layout, "Z07:00") || strings.Contains(layout, "-07:00") {
			parsed, err = time.Parse(layout, value)
		} else {
			parsed, err = time.ParseInLocation(layout, value, location)
		}
		if err == nil {
			return parsed, true
		}
	}
	return time.Time{}, false
}

func formatSQLiteTime(value time.Time) string {
	return value.Format("2006-01-02 15:04:05.999999999-07:00")
}

func isSignedInt(kind reflect.Kind) bool {
	switch kind {
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return true
	default:
		return false
	}
}

func isUnsignedInt(kind reflect.Kind) bool {
	switch kind {
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return true
	default:
		return false
	}
}

func (e Error) Unwrap() error {
	return errors.New(e.Error())
}
