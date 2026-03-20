package duckdb

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"fmt"
	"io"
	"math"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unsafe"

	"github.com/johejo/purego-gen/duckdb/internal/raw"
)

const driverName = "duckdb"

func init() {
	sql.Register(driverName, &DuckDBDriver{})
}

type DuckDBDriver struct{}

type connector struct {
	driver *DuckDBDriver
	dsn    string
}

type DuckDBConn struct {
	db   raw.Database
	conn raw.Connection

	mu     sync.Mutex
	closed bool
}

type DuckDBStmt struct {
	conn      *DuckDBConn
	stmt      raw.PreparedStatement
	ephemeral bool
	closed    bool
}

type DuckDBRows struct {
	result    raw.Result
	conn      *DuckDBConn
	stmt      *DuckDBStmt
	ctx       context.Context
	closeOnce sync.Once
	closed    bool
	names     []string
	types     []int32

	// current chunk state
	chunk       raw.DataChunk
	chunkSize   uint64
	chunkRow    uint64
	columnCount uint64
}

type DuckDBTx struct {
	conn *DuckDBConn
}

type duckdbResult struct {
	rowsAffected int64
}

var (
	_ driver.Driver             = (*DuckDBDriver)(nil)
	_ driver.DriverContext      = (*DuckDBDriver)(nil)
	_ driver.Connector          = (*connector)(nil)
	_ driver.Conn               = (*DuckDBConn)(nil)
	_ driver.ConnPrepareContext = (*DuckDBConn)(nil)
	_ driver.ExecerContext      = (*DuckDBConn)(nil)
	_ driver.QueryerContext     = (*DuckDBConn)(nil)
	_ driver.ConnBeginTx        = (*DuckDBConn)(nil)
	_ driver.Pinger             = (*DuckDBConn)(nil)
	_ driver.Stmt               = (*DuckDBStmt)(nil)
	_ driver.StmtExecContext    = (*DuckDBStmt)(nil)
	_ driver.StmtQueryContext   = (*DuckDBStmt)(nil)
	_ driver.Rows               = (*DuckDBRows)(nil)
)

func (d *DuckDBDriver) Open(name string) (driver.Conn, error) {
	c, err := d.OpenConnector(name)
	if err != nil {
		return nil, err
	}
	return c.Connect(context.Background())
}

func (d *DuckDBDriver) OpenConnector(name string) (driver.Connector, error) {
	return &connector{driver: d, dsn: name}, nil
}

func (c *connector) Connect(_ context.Context) (driver.Conn, error) {
	if err := raw.Load(); err != nil {
		return nil, err
	}

	conn := &DuckDBConn{}

	dsn := c.dsn
	if dsn == "" {
		dsn = ":memory:"
	}

	if state := raw.Open(dsn, &conn.db); state != raw.DuckDBSuccess {
		return nil, fmt.Errorf("duckdb: failed to open database %q", dsn)
	}

	if state := raw.Connect(conn.db, &conn.conn); state != raw.DuckDBSuccess {
		raw.Close(&conn.db)
		return nil, fmt.Errorf("duckdb: failed to connect to database")
	}

	return conn, nil
}

func (c *connector) Driver() driver.Driver {
	if c.driver != nil {
		return c.driver
	}
	return &DuckDBDriver{}
}

func (c *DuckDBConn) Prepare(query string) (driver.Stmt, error) {
	return c.PrepareContext(context.Background(), query)
}

func (c *DuckDBConn) PrepareContext(ctx context.Context, query string) (driver.Stmt, error) {
	if err := c.checkUsable(); err != nil {
		return nil, err
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}

	stmt := &DuckDBStmt{conn: c}
	if state := raw.Prepare(c.conn, query, &stmt.stmt); state != raw.DuckDBSuccess {
		errMsg := raw.PrepareError(stmt.stmt)
		raw.DestroyPrepare(&stmt.stmt)
		return nil, fmt.Errorf("duckdb: prepare: %s", errMsg)
	}
	return stmt, nil
}

func (c *DuckDBConn) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return nil
	}
	c.closed = true

	raw.Disconnect(&c.conn)
	raw.Close(&c.db)
	return nil
}

func (c *DuckDBConn) Begin() (driver.Tx, error) {
	return c.BeginTx(context.Background(), driver.TxOptions{})
}

func (c *DuckDBConn) BeginTx(ctx context.Context, opts driver.TxOptions) (driver.Tx, error) {
	if err := c.checkUsable(); err != nil {
		return nil, err
	}
	if opts.ReadOnly {
		return nil, fmt.Errorf("duckdb: read-only transactions are not supported")
	}
	if opts.Isolation != driver.IsolationLevel(sql.LevelDefault) &&
		opts.Isolation != driver.IsolationLevel(sql.LevelSerializable) {
		return nil, fmt.Errorf("duckdb: unsupported isolation level %d", opts.Isolation)
	}

	if _, err := c.execTransient(ctx, "BEGIN TRANSACTION", nil); err != nil {
		return nil, err
	}
	return &DuckDBTx{conn: c}, nil
}

func (c *DuckDBConn) Ping(ctx context.Context) error {
	_, err := c.execTransient(ctx, "SELECT 1", nil)
	return err
}

func (c *DuckDBConn) ExecContext(
	ctx context.Context,
	query string,
	args []driver.NamedValue,
) (driver.Result, error) {
	if len(args) == 0 {
		return c.execDirect(ctx, query)
	}
	return c.execTransient(ctx, query, args)
}

func (c *DuckDBConn) QueryContext(
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
	rows, err := stmt.queryBound(ctx)
	if err != nil {
		_ = stmt.Close()
		return nil, err
	}
	return rows, nil
}

func (c *DuckDBConn) CheckNamedValue(nv *driver.NamedValue) error {
	value, err := normalizeValue(nv.Value)
	if err != nil {
		return err
	}
	nv.Value = value
	return nil
}

func (tx *DuckDBTx) Commit() error {
	_, err := tx.conn.execDirect(context.Background(), "COMMIT")
	return err
}

func (tx *DuckDBTx) Rollback() error {
	_, err := tx.conn.execDirect(context.Background(), "ROLLBACK")
	return err
}

func (s *DuckDBStmt) Close() error {
	if s.closed {
		return nil
	}
	s.closed = true
	raw.DestroyPrepare(&s.stmt)
	return nil
}

func (s *DuckDBStmt) NumInput() int {
	return int(raw.Nparams(s.stmt))
}

func (s *DuckDBStmt) Exec(args []driver.Value) (driver.Result, error) {
	return s.ExecContext(context.Background(), valuesToNamedValues(args))
}

func (s *DuckDBStmt) Query(args []driver.Value) (driver.Rows, error) {
	return s.QueryContext(context.Background(), valuesToNamedValues(args))
}

func (s *DuckDBStmt) ExecContext(
	ctx context.Context,
	args []driver.NamedValue,
) (driver.Result, error) {
	if err := s.bindNamedValues(args); err != nil {
		return nil, err
	}
	return s.execBound(ctx)
}

func (s *DuckDBStmt) QueryContext(
	ctx context.Context,
	args []driver.NamedValue,
) (driver.Rows, error) {
	if err := s.bindNamedValues(args); err != nil {
		return nil, err
	}
	return s.queryBound(ctx)
}

func (r *DuckDBRows) Columns() []string {
	out := make([]string, len(r.names))
	copy(out, r.names)
	return out
}

func (r *DuckDBRows) Close() error {
	var err error
	r.closeOnce.Do(func() {
		r.closed = true
		r.destroyChunk()
		raw.DestroyResult(&r.result)
		if r.stmt != nil && r.stmt.ephemeral {
			err = r.stmt.Close()
		}
	})
	return err
}

func (r *DuckDBRows) Next(dest []driver.Value) error {
	if r.closed {
		return io.EOF
	}

	for {
		if r.chunk != 0 && r.chunkRow < r.chunkSize {
			for col := uint64(0); col < r.columnCount; col++ {
				val, err := r.readValue(col, r.chunkRow)
				if err != nil {
					return err
				}
				dest[col] = val
			}
			r.chunkRow++
			return nil
		}

		r.destroyChunk()

		r.chunk = raw.FetchChunk(r.result)
		if r.chunk == 0 {
			_ = r.Close()
			return io.EOF
		}
		r.chunkSize = raw.DataChunkGetSize(r.chunk)
		r.chunkRow = 0

		if r.chunkSize == 0 {
			r.destroyChunk()
			_ = r.Close()
			return io.EOF
		}
	}
}

func (r *DuckDBRows) ColumnTypeDatabaseTypeName(index int) string {
	switch r.types[index] {
	case raw.DUCKDB_TYPE_BOOLEAN:
		return "BOOLEAN"
	case raw.DUCKDB_TYPE_TINYINT:
		return "TINYINT"
	case raw.DUCKDB_TYPE_SMALLINT:
		return "SMALLINT"
	case raw.DUCKDB_TYPE_INTEGER:
		return "INTEGER"
	case raw.DUCKDB_TYPE_BIGINT:
		return "BIGINT"
	case raw.DUCKDB_TYPE_UTINYINT:
		return "UTINYINT"
	case raw.DUCKDB_TYPE_USMALLINT:
		return "USMALLINT"
	case raw.DUCKDB_TYPE_UINTEGER:
		return "UINTEGER"
	case raw.DUCKDB_TYPE_UBIGINT:
		return "UBIGINT"
	case raw.DUCKDB_TYPE_FLOAT:
		return "FLOAT"
	case raw.DUCKDB_TYPE_DOUBLE:
		return "DOUBLE"
	case raw.DUCKDB_TYPE_TIMESTAMP, raw.DUCKDB_TYPE_TIMESTAMP_S, raw.DUCKDB_TYPE_TIMESTAMP_MS, raw.DUCKDB_TYPE_TIMESTAMP_NS, raw.DUCKDB_TYPE_TIMESTAMP_TZ:
		return "TIMESTAMP"
	case raw.DUCKDB_TYPE_DATE:
		return "DATE"
	case raw.DUCKDB_TYPE_TIME, raw.DUCKDB_TYPE_TIME_TZ:
		return "TIME"
	case raw.DUCKDB_TYPE_INTERVAL:
		return "INTERVAL"
	case raw.DUCKDB_TYPE_HUGEINT:
		return "HUGEINT"
	case raw.DUCKDB_TYPE_VARCHAR:
		return "VARCHAR"
	case raw.DUCKDB_TYPE_BLOB:
		return "BLOB"
	case raw.DUCKDB_TYPE_DECIMAL:
		return "DECIMAL"
	default:
		return "UNKNOWN"
	}
}

func (r *DuckDBRows) ColumnTypeScanType(index int) reflect.Type {
	switch r.types[index] {
	case raw.DUCKDB_TYPE_BOOLEAN:
		return reflect.TypeOf(false)
	case raw.DUCKDB_TYPE_TINYINT, raw.DUCKDB_TYPE_SMALLINT, raw.DUCKDB_TYPE_INTEGER, raw.DUCKDB_TYPE_BIGINT:
		return reflect.TypeOf(int64(0))
	case raw.DUCKDB_TYPE_UTINYINT, raw.DUCKDB_TYPE_USMALLINT, raw.DUCKDB_TYPE_UINTEGER, raw.DUCKDB_TYPE_UBIGINT:
		return reflect.TypeOf(int64(0))
	case raw.DUCKDB_TYPE_FLOAT, raw.DUCKDB_TYPE_DOUBLE:
		return reflect.TypeOf(float64(0))
	case raw.DUCKDB_TYPE_TIMESTAMP, raw.DUCKDB_TYPE_TIMESTAMP_S, raw.DUCKDB_TYPE_TIMESTAMP_MS, raw.DUCKDB_TYPE_TIMESTAMP_NS, raw.DUCKDB_TYPE_TIMESTAMP_TZ,
		raw.DUCKDB_TYPE_DATE, raw.DUCKDB_TYPE_TIME, raw.DUCKDB_TYPE_TIME_TZ:
		return reflect.TypeOf(time.Time{})
	case raw.DUCKDB_TYPE_BLOB:
		return reflect.TypeOf([]byte(nil))
	case raw.DUCKDB_TYPE_VARCHAR:
		return reflect.TypeOf("")
	default:
		return reflect.TypeOf("")
	}
}

// vectorPtr converts a uintptr data base + byte offset into an unsafe.Pointer.
func vectorPtr(data uintptr, byteOffset uintptr) unsafe.Pointer {
	return unsafe.Add(unsafe.Pointer(nil), data+byteOffset)
}

func (r *DuckDBRows) readValue(col, row uint64) (driver.Value, error) {
	vector := raw.DataChunkGetVector(r.chunk, col)
	validity := raw.VectorGetValidity(vector)
	if validity != 0 && !raw.ValidityRowIsValid(validity, row) {
		return nil, nil
	}

	data := raw.VectorGetData(vector)

	switch r.types[col] {
	case raw.DUCKDB_TYPE_BOOLEAN:
		val := *(*bool)(vectorPtr(data, uintptr(row)))
		return val, nil
	case raw.DUCKDB_TYPE_TINYINT:
		val := *(*int8)(vectorPtr(data, uintptr(row)))
		return int64(val), nil
	case raw.DUCKDB_TYPE_SMALLINT:
		val := *(*int16)(vectorPtr(data, uintptr(row)*2))
		return int64(val), nil
	case raw.DUCKDB_TYPE_INTEGER:
		val := *(*int32)(vectorPtr(data, uintptr(row)*4))
		return int64(val), nil
	case raw.DUCKDB_TYPE_BIGINT:
		val := *(*int64)(vectorPtr(data, uintptr(row)*8))
		return val, nil
	case raw.DUCKDB_TYPE_UTINYINT:
		val := *(*uint8)(vectorPtr(data, uintptr(row)))
		return int64(val), nil
	case raw.DUCKDB_TYPE_USMALLINT:
		val := *(*uint16)(vectorPtr(data, uintptr(row)*2))
		return int64(val), nil
	case raw.DUCKDB_TYPE_UINTEGER:
		val := *(*uint32)(vectorPtr(data, uintptr(row)*4))
		return int64(val), nil
	case raw.DUCKDB_TYPE_UBIGINT:
		val := *(*uint64)(vectorPtr(data, uintptr(row)*8))
		return int64(val), nil
	case raw.DUCKDB_TYPE_FLOAT:
		val := *(*float32)(vectorPtr(data, uintptr(row)*4))
		return float64(val), nil
	case raw.DUCKDB_TYPE_DOUBLE:
		val := *(*float64)(vectorPtr(data, uintptr(row)*8))
		return val, nil
	case raw.DUCKDB_TYPE_VARCHAR:
		return raw.ReadStringFromVector(data, row), nil
	case raw.DUCKDB_TYPE_BLOB:
		return raw.ReadBlobFromVector(data, row), nil
	case raw.DUCKDB_TYPE_TIMESTAMP, raw.DUCKDB_TYPE_TIMESTAMP_TZ:
		ts := *(*raw.Timestamp)(vectorPtr(data, uintptr(row)*8))
		return timestampToTime(ts), nil
	case raw.DUCKDB_TYPE_TIMESTAMP_S:
		seconds := *(*int64)(vectorPtr(data, uintptr(row)*8))
		return time.Unix(seconds, 0).UTC(), nil
	case raw.DUCKDB_TYPE_TIMESTAMP_MS:
		millis := *(*int64)(vectorPtr(data, uintptr(row)*8))
		return time.Unix(millis/1000, (millis%1000)*int64(time.Millisecond)).UTC(), nil
	case raw.DUCKDB_TYPE_TIMESTAMP_NS:
		nanos := *(*int64)(vectorPtr(data, uintptr(row)*8))
		return time.Unix(0, nanos).UTC(), nil
	case raw.DUCKDB_TYPE_DATE:
		date := *(*raw.Date)(vectorPtr(data, uintptr(row)*4))
		ds := raw.FromDate(date)
		year, month, day := raw.DateStructFields(&ds)
		return time.Date(int(year), time.Month(month), int(day), 0, 0, 0, 0, time.UTC), nil
	case raw.DUCKDB_TYPE_TIME, raw.DUCKDB_TYPE_TIME_TZ:
		t := *(*raw.Time)(vectorPtr(data, uintptr(row)*8))
		ts := raw.FromTime(t)
		hour, min, sec, micros := raw.TimeStructFields(&ts)
		return time.Date(0, 1, 1, int(hour), int(min), int(sec), int(micros)*1000, time.UTC), nil
	case raw.DUCKDB_TYPE_HUGEINT:
		hi := *(*raw.Hugeint)(vectorPtr(data, uintptr(row)*16))
		return hugeintToString(hi), nil
	case raw.DUCKDB_TYPE_DECIMAL:
		return readDecimalValue(vector, data, row), nil
	default:
		return fmt.Sprintf("unsupported type %d", r.types[col]), nil
	}
}

func (r *DuckDBRows) destroyChunk() {
	if r.chunk != 0 {
		raw.DestroyDataChunk(&r.chunk)
		r.chunk = 0
	}
}

func (s *DuckDBStmt) bindNamedValues(args []driver.NamedValue) error {
	if err := s.conn.checkUsable(); err != nil {
		return err
	}
	if state := raw.ClearBindings(s.stmt); state != raw.DuckDBSuccess {
		return fmt.Errorf("duckdb: clear bindings failed")
	}
	for _, arg := range args {
		idx, err := s.resolveIndex(arg)
		if err != nil {
			return err
		}
		if err := s.bindValue(idx, arg.Value); err != nil {
			return err
		}
	}
	return nil
}

func (s *DuckDBStmt) resolveIndex(arg driver.NamedValue) (uint64, error) {
	if arg.Name == "" {
		return uint64(arg.Ordinal), nil
	}
	idx, state := raw.BindParameterIndex(s.stmt, arg.Name)
	if state != raw.DuckDBSuccess {
		// Try with $ prefix
		idx, state = raw.BindParameterIndex(s.stmt, "$"+arg.Name)
		if state != raw.DuckDBSuccess {
			return 0, fmt.Errorf("duckdb: unknown named parameter %q", arg.Name)
		}
	}
	return idx, nil
}

func (s *DuckDBStmt) bindValue(idx uint64, value any) error {
	var state int32
	switch v := value.(type) {
	case nil:
		state = raw.BindNull(s.stmt, idx)
	case bool:
		state = raw.BindBoolean(s.stmt, idx, v)
	case int64:
		state = raw.BindInt64(s.stmt, idx, v)
	case float64:
		state = raw.BindDouble(s.stmt, idx, v)
	case string:
		state = raw.BindVarchar(s.stmt, idx, v)
	case []byte:
		state = raw.BindBlob(s.stmt, idx, v)
	case time.Time:
		ts := timeToTimestamp(v)
		state = raw.BindTimestamp(s.stmt, idx, ts)
	default:
		normalized, err := normalizeValue(v)
		if err != nil {
			return err
		}
		if normalized == value {
			return fmt.Errorf("duckdb: unsupported bind parameter type %T", value)
		}
		return s.bindValue(idx, normalized)
	}
	if state != raw.DuckDBSuccess {
		return fmt.Errorf("duckdb: bind parameter %d failed", idx)
	}
	return nil
}

func (s *DuckDBStmt) execBound(ctx context.Context) (driver.Result, error) {
	var result raw.Result

	cancel := interruptWatcher(ctx, s.conn.conn)
	state := raw.ExecutePrepared(s.stmt, &result)
	cancel.stop()

	if state != raw.DuckDBSuccess {
		errMsg := raw.ResultError(&result)
		raw.DestroyResult(&result)
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, fmt.Errorf("duckdb: exec: %s", errMsg)
	}

	rowsAffected := int64(raw.RowsChanged(&result))
	raw.DestroyResult(&result)
	return duckdbResult{rowsAffected: rowsAffected}, nil
}

func (s *DuckDBStmt) queryBound(ctx context.Context) (*DuckDBRows, error) {
	rows := &DuckDBRows{
		conn: s.conn,
		stmt: s,
		ctx:  ctx,
	}

	cancel := interruptWatcher(ctx, s.conn.conn)
	state := raw.ExecutePrepared(s.stmt, &rows.result)
	cancel.stop()

	if state != raw.DuckDBSuccess {
		errMsg := raw.ResultError(&rows.result)
		raw.DestroyResult(&rows.result)
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, fmt.Errorf("duckdb: query: %s", errMsg)
	}

	colCount := raw.ColumnCount(&rows.result)
	rows.columnCount = colCount
	rows.names = make([]string, colCount)
	rows.types = make([]int32, colCount)
	for i := uint64(0); i < colCount; i++ {
		rows.names[i] = raw.ColumnName(&rows.result, i)
		rows.types[i] = raw.ColumnType(&rows.result, i)
	}

	return rows, nil
}

func (c *DuckDBConn) prepareEphemeral(ctx context.Context, query string) (*DuckDBStmt, error) {
	stmtValue, err := c.PrepareContext(ctx, query)
	if err != nil {
		return nil, err
	}
	stmt := stmtValue.(*DuckDBStmt)
	stmt.ephemeral = true
	return stmt, nil
}

func (c *DuckDBConn) execTransient(
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

func (c *DuckDBConn) execDirect(ctx context.Context, query string) (driver.Result, error) {
	var result raw.Result

	cancel := interruptWatcher(ctx, c.conn)
	state := raw.Query(c.conn, query, &result)
	cancel.stop()

	if state != raw.DuckDBSuccess {
		errMsg := raw.ResultError(&result)
		raw.DestroyResult(&result)
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, fmt.Errorf("duckdb: exec: %s", errMsg)
	}

	rowsAffected := int64(raw.RowsChanged(&result))
	raw.DestroyResult(&result)
	return duckdbResult{rowsAffected: rowsAffected}, nil
}

func (c *DuckDBConn) checkUsable() error {
	if c.closed || c.conn == 0 {
		return driver.ErrBadConn
	}
	return nil
}

func (r duckdbResult) LastInsertId() (int64, error) { return 0, nil }
func (r duckdbResult) RowsAffected() (int64, error) { return r.rowsAffected, nil }

// interruptWatcher / cancelState

type cancelState struct {
	done        chan struct{}
	interrupted atomic.Bool
}

func interruptWatcher(ctx context.Context, conn raw.Connection) *cancelState {
	state := &cancelState{done: make(chan struct{})}
	if ctx == nil || ctx.Done() == nil || conn == 0 {
		close(state.done)
		return state
	}
	go func() {
		select {
		case <-ctx.Done():
			state.interrupted.Store(true)
			raw.Interrupt(conn)
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

// Value normalization

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
			return nil, fmt.Errorf("duckdb: uint value %d overflows int64", v)
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
			return nil, fmt.Errorf("duckdb: uint64 value %d overflows int64", v)
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
		return nil, fmt.Errorf("duckdb: unsupported value type %T", value)
	}
}

// Timestamp helpers

// duckdb epoch: 1970-01-01 00:00:00 UTC, stored as microseconds
func timestampToTime(ts raw.Timestamp) time.Time {
	micros := *(*int64)(unsafe.Pointer(&ts))
	seconds := micros / 1_000_000
	remainder := micros % 1_000_000
	if remainder < 0 {
		seconds--
		remainder += 1_000_000
	}
	return time.Unix(seconds, remainder*1000).UTC()
}

func timeToTimestamp(t time.Time) raw.Timestamp {
	micros := t.Unix()*1_000_000 + int64(t.Nanosecond())/1000
	var ts raw.Timestamp
	*(*int64)(unsafe.Pointer(&ts)) = micros
	return ts
}

// Hugeint helper
func hugeintToString(h raw.Hugeint) string {
	p := unsafe.Pointer(&h)
	upper := *(*int64)(unsafe.Add(p, 8))
	lower := *(*uint64)(p)
	if upper == 0 {
		return strconv.FormatUint(lower, 10)
	}
	if upper < 0 {
		// Handle negative: negate then format
		if lower == 0 {
			return "-" + strconv.FormatInt(-upper, 10) + "0000000000000000000"
		}
		// Two's complement negate: flip bits and add 1
		negLower := ^lower + 1
		negUpper := ^uint64(upper)
		if negLower == 0 {
			negUpper++
		}
		if negUpper == 0 {
			return "-" + strconv.FormatUint(negLower, 10)
		}
		return "-" + strconv.FormatUint(negUpper, 10) + fmt.Sprintf("%020d", negLower)
	}
	return strconv.FormatUint(uint64(upper), 10) + fmt.Sprintf("%020d", lower)
}

func readDecimalValue(vector raw.Vector, data uintptr, row uint64) driver.Value {
	logType := raw.VectorGetColumnType(vector)
	defer raw.DestroyLogicalType(&logType)
	typeID := raw.GetTypeId(logType)
	scale := raw.DecimalScale(logType)

	var intVal int64
	switch typeID {
	case raw.DUCKDB_TYPE_SMALLINT:
		intVal = int64(*(*int16)(vectorPtr(data, uintptr(row)*2)))
	case raw.DUCKDB_TYPE_INTEGER:
		intVal = int64(*(*int32)(vectorPtr(data, uintptr(row)*4)))
	case raw.DUCKDB_TYPE_BIGINT:
		intVal = *(*int64)(vectorPtr(data, uintptr(row)*8))
	case raw.DUCKDB_TYPE_HUGEINT:
		h := *(*raw.Hugeint)(vectorPtr(data, uintptr(row)*16))
		return hugeintToString(h) // Fallback: return as string
	default:
		return "0"
	}

	if scale == 0 {
		return intVal
	}

	negative := intVal < 0
	if negative {
		intVal = -intVal
	}
	divisor := int64(1)
	for i := uint8(0); i < scale; i++ {
		divisor *= 10
	}
	whole := intVal / divisor
	frac := intVal % divisor

	result := strings.Builder{}
	if negative {
		result.WriteByte('-')
	}
	result.WriteString(strconv.FormatInt(whole, 10))
	result.WriteByte('.')
	fracStr := strconv.FormatInt(frac, 10)
	for i := len(fracStr); i < int(scale); i++ {
		result.WriteByte('0')
	}
	result.WriteString(fracStr)
	return result.String()
}

