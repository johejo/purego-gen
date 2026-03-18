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

	"github.com/johejo/purego-gen/sqlite3/internal/raw"
)

const driverName = "sqlite3"

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
	db     raw.DB
	config connectionConfig

	mu     sync.Mutex
	closed bool

	registryMu sync.Mutex
	nextID     uintptr
	scalars    map[uintptr]*scalarFunction
	collations map[uintptr]*collationFunction
}

type SQLiteStmt struct {
	conn      *SQLiteConn
	stmt      raw.Stmt
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
	args       []func(raw.Value) (reflect.Value, error)
	returnFunc func(raw.Context, []reflect.Value)
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
	if err := raw.Load(); err != nil {
		return nil, err
	}

	conn := &SQLiteConn{
		config:     c.dsn,
		scalars:    make(map[uintptr]*scalarFunction),
		collations: make(map[uintptr]*collationFunction),
	}

	result := raw.OpenV2(c.dsn.filename, c.dsn.flags, "", &conn.db)
	if result != raw.SQLITE_OK {
		defer conn.forceClose()
		return nil, conn.errorFromResult(result)
	}

	if c.dsn.busyTimeout > 0 {
		if result := raw.BusyTimeout(conn.db, c.dsn.busyTimeout); result != raw.SQLITE_OK {
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
	result := raw.PrepareV2(c.db, query, &stmt.stmt)
	if result != raw.SQLITE_OK {
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

	result := raw.CloseV2(c.db)
	c.db = 0
	if result != raw.SQLITE_OK {
		return c.errorFromResult(result)
	}
	return nil
}

func (c *SQLiteConn) forceClose() {
	if c.db == 0 {
		return
	}
	_ = raw.CloseV2(c.db)
	c.db = 0
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
	return !c.closed && c.db != 0
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

	flags := int32(raw.SQLITE_UTF8)
	if pure {
		flags |= raw.SQLITE_DETERMINISTIC
	}
	result := raw.CreateFunctionV2Callbacks(
		c.db,
		name,
		int32(len(compiled.args)),
		flags,
		id,
		func(ctx raw.Context, argc int32, values uintptr) {
			c.invokeScalar(ctx, argc, values)
		},
		func(userData uintptr) {
			c.unregisterScalar(userData)
		},
	)
	if result != raw.SQLITE_OK {
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

	result := raw.CreateCollationV2Callbacks(
		c.db,
		name,
		raw.SQLITE_UTF8,
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
	if result != raw.SQLITE_OK {
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

	result := raw.Finalize(s.stmt)
	s.stmt = 0
	if result != raw.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	return nil
}

func (s *SQLiteStmt) NumInput() int {
	return int(raw.BindParameterCount(s.stmt))
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
	result := raw.Step(r.stmt.stmt)
	interrupted := cancel.stop()

	switch result {
	case raw.SQLITE_ROW:
		for index := range dest {
			value, err := r.columnValue(index)
			if err != nil {
				return err
			}
			dest[index] = value
		}
		return nil
	case raw.SQLITE_DONE:
		_ = r.Close()
		return io.EOF
	case raw.SQLITE_INTERRUPT:
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
	switch raw.ColumnType(r.stmt.stmt, column) {
	case raw.SQLITE_INTEGER:
		return raw.ColumnInt64(r.stmt.stmt, column), nil
	case raw.SQLITE_FLOAT:
		return raw.ColumnDouble(r.stmt.stmt, column), nil
	case raw.SQLITE_TEXT:
		text := raw.ColumnText(r.stmt.stmt, column)
		if r.stmt.conn.config.location != nil && looksLikeTimeType(r.declTypes[index]) {
			parsed, ok := parseSQLiteTime(text, r.stmt.conn.config.location)
			if ok {
				return parsed, nil
			}
		}
		return text, nil
	case raw.SQLITE_BLOB:
		return raw.ColumnBlobBytes(r.stmt.stmt, column), nil
	case raw.SQLITE_NULL:
		return nil, nil
	default:
		return raw.ColumnText(r.stmt.stmt, column), nil
	}
}

func (s *SQLiteStmt) bindNamedValues(args []driver.NamedValue) error {
	if err := s.conn.checkUsable(); err != nil {
		return err
	}
	if result := raw.Reset(s.stmt); result != raw.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	if result := raw.ClearBindings(s.stmt); result != raw.SQLITE_OK {
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
		if index := raw.BindParameterIndex(s.stmt, name); index != 0 {
			return index, nil
		}
	}
	return 0, fmt.Errorf("sqlite3: unknown named parameter %q", arg.Name)
}

func (s *SQLiteStmt) bindValue(index int32, value any) error {
	switch v := value.(type) {
	case nil:
		return s.bindResult(raw.BindNull(s.stmt, index))
	case int64:
		return s.bindResult(raw.BindInt64(s.stmt, index, v))
	case float64:
		return s.bindResult(raw.BindDouble(s.stmt, index, v))
	case bool:
		intValue := int64(0)
		if v {
			intValue = 1
		}
		return s.bindResult(raw.BindInt64(s.stmt, index, intValue))
	case string:
		return s.bindResult(raw.BindText(s.stmt, index, v, raw.SQLITE_TRANSIENT))
	case []byte:
		return s.bindResult(raw.BindBlobBytes(s.stmt, index, v, raw.SQLITE_TRANSIENT))
	case time.Time:
		return s.bindResult(raw.BindText(s.stmt, index, formatSQLiteTime(v), raw.SQLITE_TRANSIENT))
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
	if result != raw.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	return nil
}

func (s *SQLiteStmt) execBound(ctx context.Context) (driver.Result, error) {
	cancel := interruptWatcher(ctx, s.conn.db)
	for {
		result := raw.Step(s.stmt)
		switch result {
		case raw.SQLITE_ROW:
			continue
		case raw.SQLITE_DONE:
			cancel.stop()
			return sqliteResult{
				lastInsertID: raw.LastInsertRowid(s.conn.db),
				rowsAffected: raw.Changes64(s.conn.db),
			}, nil
		case raw.SQLITE_INTERRUPT:
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
	count := int(raw.ColumnCount(s.stmt))
	rows := &SQLiteRows{
		stmt:      s,
		ctx:       ctx,
		names:     make([]string, count),
		declTypes: make([]string, count),
	}
	for index := 0; index < count; index++ {
		column := int32(index)
		rows.names[index] = raw.ColumnName(s.stmt, column)
		rows.declTypes[index] = raw.ColumnDeclType(s.stmt, column)
	}
	return rows, nil
}

func (s *SQLiteStmt) resetForReuse() error {
	if s.closed || s.stmt == 0 {
		return nil
	}
	if result := raw.Reset(s.stmt); result != raw.SQLITE_OK {
		return s.conn.errorFromResult(result)
	}
	if result := raw.ClearBindings(s.stmt); result != raw.SQLITE_OK {
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
	if c.closed || c.db == 0 {
		return driver.ErrBadConn
	}
	return nil
}

func (c *SQLiteConn) errorFromContext(result int32, ctx context.Context) error {
	if result == raw.SQLITE_INTERRUPT && ctx != nil && ctx.Err() != nil {
		return ctx.Err()
	}
	return c.errorFromResult(result)
}

func (c *SQLiteConn) errorFromResult(result int32) error {
	if result == raw.SQLITE_OK {
		return nil
	}
	message := sqliteErrorString(result)
	if c != nil && c.db != 0 {
		if dbMessage := raw.Errmsg(c.db); dbMessage != "" {
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
		flags:    raw.SQLITE_OPEN_READWRITE | raw.SQLITE_OPEN_CREATE | raw.SQLITE_OPEN_FULLMUTEX,
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
				cfg.flags = raw.SQLITE_OPEN_READONLY | raw.SQLITE_OPEN_URI | raw.SQLITE_OPEN_FULLMUTEX
			case "rw":
				cfg.flags = raw.SQLITE_OPEN_READWRITE | raw.SQLITE_OPEN_URI | raw.SQLITE_OPEN_FULLMUTEX
			case "rwc":
				cfg.flags = raw.SQLITE_OPEN_READWRITE | raw.SQLITE_OPEN_CREATE | raw.SQLITE_OPEN_URI | raw.SQLITE_OPEN_FULLMUTEX
			case "memory":
				cfg.flags = raw.SQLITE_OPEN_READWRITE | raw.SQLITE_OPEN_CREATE | raw.SQLITE_OPEN_MEMORY | raw.SQLITE_OPEN_URI | raw.SQLITE_OPEN_FULLMUTEX
			default:
				return cfg, fmt.Errorf("sqlite3: unsupported mode %q", mode)
			}
			preserved[key] = value
		case "cache":
			preserved[key] = value
			cfg.flags |= raw.SQLITE_OPEN_URI
		default:
			preserved[key] = value
			if !strings.HasPrefix(key, "_") {
				cfg.flags |= raw.SQLITE_OPEN_URI
			}
		}
	}

	cfg.filename = rebuildFilename(base, preserved)
	if strings.HasPrefix(cfg.filename, "file:") {
		cfg.flags |= raw.SQLITE_OPEN_URI
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

	args := make([]func(raw.Value) (reflect.Value, error), fnType.NumIn())
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

func buildValueDecoder(target reflect.Type) (func(raw.Value) (reflect.Value, error), error) {
	switch {
	case target.Kind() == reflect.String:
		return func(value raw.Value) (reflect.Value, error) {
			return reflect.ValueOf(raw.ValueText(value)).Convert(target), nil
		}, nil
	case target.Kind() == reflect.Slice && target.Elem().Kind() == reflect.Uint8:
		return func(value raw.Value) (reflect.Value, error) {
			return reflect.ValueOf(raw.ValueBlobBytes(value)).Convert(target), nil
		}, nil
	case target.Kind() == reflect.Bool:
		return func(value raw.Value) (reflect.Value, error) {
			return reflect.ValueOf(raw.ValueInt64(value) != 0).Convert(target), nil
		}, nil
	case isSignedInt(target.Kind()):
		return func(value raw.Value) (reflect.Value, error) {
			return reflect.ValueOf(raw.ValueInt64(value)).Convert(target), nil
		}, nil
	case isUnsignedInt(target.Kind()):
		return func(value raw.Value) (reflect.Value, error) {
			number := raw.ValueInt64(value)
			if number < 0 {
				return reflect.Value{}, fmt.Errorf("negative value %d for unsigned integer", number)
			}
			return reflect.ValueOf(uint64(number)).Convert(target), nil
		}, nil
	case target.Kind() == reflect.Float32 || target.Kind() == reflect.Float64:
		return func(value raw.Value) (reflect.Value, error) {
			return reflect.ValueOf(raw.ValueDouble(value)).Convert(target), nil
		}, nil
	case target == reflect.TypeOf(time.Time{}):
		return func(value raw.Value) (reflect.Value, error) {
			text := raw.ValueText(value)
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

func buildReturnEncoder(fnType reflect.Type) (func(raw.Context, []reflect.Value), error) {
	switch fnType.NumOut() {
	case 0:
		return func(ctx raw.Context, _ []reflect.Value) {
			raw.ResultNull(ctx)
		}, nil
	case 1:
		return func(ctx raw.Context, results []reflect.Value) {
			encodeResultValue(ctx, results[0], nil)
		}, nil
	case 2:
		if !fnType.Out(1).Implements(reflect.TypeOf((*error)(nil)).Elem()) {
			return nil, fmt.Errorf("sqlite3: second return value must be error")
		}
		return func(ctx raw.Context, results []reflect.Value) {
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

func encodeResultValue(ctx raw.Context, value reflect.Value, err error) {
	if err != nil {
		raw.ResultError(ctx, err.Error())
		return
	}

	if !value.IsValid() {
		raw.ResultNull(ctx)
		return
	}
	if value.Kind() == reflect.Interface && !value.IsNil() {
		value = value.Elem()
	}
	if value.Kind() == reflect.Pointer {
		if value.IsNil() {
			raw.ResultNull(ctx)
			return
		}
		value = value.Elem()
	}

	switch {
	case value.Kind() == reflect.String:
		raw.ResultText(ctx, value.String(), raw.SQLITE_TRANSIENT)
	case value.Kind() == reflect.Slice && value.Type().Elem().Kind() == reflect.Uint8:
		raw.ResultBlobBytes(ctx, append([]byte(nil), value.Bytes()...), raw.SQLITE_TRANSIENT)
	case value.Kind() == reflect.Bool:
		boolValue := int64(0)
		if value.Bool() {
			boolValue = 1
		}
		raw.ResultInt64(ctx, boolValue)
	case isSignedInt(value.Kind()):
		raw.ResultInt64(ctx, value.Int())
	case isUnsignedInt(value.Kind()):
		raw.ResultInt64(ctx, int64(value.Uint()))
	case value.Kind() == reflect.Float32 || value.Kind() == reflect.Float64:
		raw.ResultDouble(ctx, value.Convert(reflect.TypeOf(float64(0))).Float())
	case value.Type() == reflect.TypeOf(time.Time{}):
		raw.ResultText(ctx, formatSQLiteTime(value.Interface().(time.Time)), raw.SQLITE_TRANSIENT)
	default:
		raw.ResultError(ctx, "unsupported Go return type")
	}
}

func (c *SQLiteConn) invokeScalar(ctx raw.Context, argc int32, values uintptr) {
	function := c.lookupScalar(raw.UserData(ctx))
	if function == nil {
		raw.ResultError(ctx, "sqlite3: function registry entry not found")
		return
	}
	if int(argc) != len(function.args) {
		raw.ResultError(ctx, "sqlite3: unexpected argument count")
		return
	}

	sqliteValues := unsafe.Slice((*raw.Value)(unsafe.Pointer(values)), int(argc))
	callArgs := make([]reflect.Value, len(sqliteValues))
	for index := range sqliteValues {
		decoded, err := function.args[index](sqliteValues[index])
		if err != nil {
			raw.ResultError(ctx, err.Error())
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

type cancelState struct {
	done        chan struct{}
	interrupted atomic.Bool
}

func interruptWatcher(ctx context.Context, db raw.DB) *cancelState {
	state := &cancelState{done: make(chan struct{})}
	if ctx == nil || ctx.Done() == nil || db == 0 {
		close(state.done)
		return state
	}
	go func() {
		select {
		case <-ctx.Done():
			state.interrupted.Store(true)
			raw.Interrupt(db)
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
	case raw.SQLITE_ERROR:
		return "SQL error or missing database"
	case raw.SQLITE_INTERNAL:
		return "internal logic error in SQLite"
	case raw.SQLITE_PERM:
		return "access permission denied"
	case raw.SQLITE_ABORT:
		return "callback requested abort"
	case raw.SQLITE_BUSY:
		return "database is locked"
	case raw.SQLITE_LOCKED:
		return "table is locked"
	case raw.SQLITE_NOMEM:
		return "out of memory"
	case raw.SQLITE_READONLY:
		return "attempt to write a readonly database"
	case raw.SQLITE_INTERRUPT:
		return "operation interrupted"
	case raw.SQLITE_IOERR:
		return "disk I/O error"
	case raw.SQLITE_CORRUPT:
		return "database disk image is malformed"
	case raw.SQLITE_NOTFOUND:
		return "unknown opcode"
	case raw.SQLITE_FULL:
		return "database or disk is full"
	case raw.SQLITE_CANTOPEN:
		return "unable to open database file"
	case raw.SQLITE_PROTOCOL:
		return "locking protocol error"
	case raw.SQLITE_EMPTY:
		return "database is empty"
	case raw.SQLITE_SCHEMA:
		return "database schema changed"
	case raw.SQLITE_TOOBIG:
		return "string or blob too big"
	case raw.SQLITE_CONSTRAINT:
		return "constraint failed"
	case raw.SQLITE_MISMATCH:
		return "datatype mismatch"
	case raw.SQLITE_MISUSE:
		return "library routine called out of sequence"
	case raw.SQLITE_NOLFS:
		return "large file support unavailable"
	case raw.SQLITE_AUTH:
		return "authorization denied"
	case raw.SQLITE_FORMAT:
		return "auxiliary database format error"
	case raw.SQLITE_RANGE:
		return "bind or column index out of range"
	case raw.SQLITE_NOTADB:
		return "file is not a database"
	default:
		return fmt.Sprintf("sqlite result code %d", code)
	}
}

func rawBytes(ptr uintptr, length int32) []byte {
	if ptr == 0 || length <= 0 {
		return nil
	}
	return unsafe.Slice((*byte)(unsafe.Pointer(ptr)), int(length))
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
