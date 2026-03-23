package sqlite3sys

// --- Changes/rowid ---

func Changes(db *DB) int32                { return sqlite3_changes(db) }
func Changes64(db *DB) int64              { return sqlite3_changes64(db) }
func TotalChanges(db *DB) int32           { return sqlite3_total_changes(db) }
func TotalChanges64(db *DB) int64         { return sqlite3_total_changes64(db) }
func LastInsertRowid(db *DB) int64        { return sqlite3_last_insert_rowid(db) }
func SetLastInsertRowid(db *DB, id int64) { sqlite3_set_last_insert_rowid(db, id) }
func UserData(ctx *Context) uintptr       { return sqlite3_user_data(ctx) }
func AggregateContext(ctx *Context, nBytes int32) uintptr {
	return sqlite3_aggregate_context(ctx, nBytes)
}

// --- Function/collation registration ---

func CreateFunctionV2Callbacks(
	db *DB,
	name string,
	nArg int32,
	textRep int32,
	app uintptr,
	xFunc func(*Context, int32, **Value),
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_function_v2_callbacks(
		db,
		name,
		nArg,
		textRep,
		app,
		xFunc,
		nil,
		nil,
		xDestroy,
	)
}

func CreateAggregateFunctionV2Callbacks(
	db *DB,
	name string,
	nArg int32,
	textRep int32,
	app uintptr,
	xStep func(*Context, int32, **Value),
	xFinal func(*Context),
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_function_v2_callbacks(
		db,
		name,
		nArg,
		textRep,
		app,
		nil,
		xStep,
		xFinal,
		xDestroy,
	)
}

func CreateWindowFunctionCallbacks(
	db *DB,
	name string,
	nArg int32,
	textRep int32,
	app uintptr,
	xStep func(*Context, int32, **Value),
	xFinal func(*Context),
	xValue func(*Context),
	xInverse func(*Context, int32, **Value),
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_window_function_callbacks(
		db,
		name,
		nArg,
		textRep,
		app,
		xStep,
		xFinal,
		xValue,
		xInverse,
		xDestroy,
	)
}

func CreateCollationV2Callbacks(
	db *DB,
	name string,
	textRep int32,
	app uintptr,
	xCompare func(uintptr, int32, uintptr, int32, uintptr) int32,
	xDestroy func(uintptr),
) int32 {
	return sqlite3_create_collation_v2_callbacks(
		db,
		name,
		textRep,
		app,
		xCompare,
		xDestroy,
	)
}

// --- Values ---

func ValueType(value *Value) int32        { return sqlite3_value_type(value) }
func ValueInt(value *Value) int32         { return sqlite3_value_int(value) }
func ValueInt64(value *Value) int64       { return sqlite3_value_int64(value) }
func ValueDouble(value *Value) float64    { return sqlite3_value_double(value) }
func ValueText(value *Value) string       { return sqlite3_value_text(value) }
func ValueNumericType(value *Value) int32 { return sqlite3_value_numeric_type(value) }
func ValueNochange(value *Value) int32    { return sqlite3_value_nochange(value) }
func ValueFrombind(value *Value) int32    { return sqlite3_value_frombind(value) }
func ValueSubtype(value *Value) uint32    { return sqlite3_value_subtype(value) }
func ValueDup(value *Value) *Value        { return sqlite3_value_dup(value) }
func ValueFree(value *Value)              { sqlite3_value_free(value) }
func ValueBlobBytes(value *Value) []byte {
	ptr := sqlite3_value_blob(value)
	length := sqlite3_value_bytes(value)
	return copyBytes(ptr, length)
}

// --- Results ---

func ResultNull(ctx *Context) { sqlite3_result_null(ctx) }
func ResultBlobBytes(ctx *Context, value []byte, destructor DestructorType) {
	sqlite3_result_blob_bytes(ctx, value, destructor)
}
func ResultDouble(ctx *Context, value float64) { sqlite3_result_double(ctx, value) }
func ResultInt(ctx *Context, value int32)      { sqlite3_result_int(ctx, value) }
func ResultInt64(ctx *Context, value int64)    { sqlite3_result_int64(ctx, value) }
func ResultText(ctx *Context, value string, destructor DestructorType) {
	sqlite3_result_text(ctx, value, -1, destructor)
}
func ResultError(ctx *Context, value string) { sqlite3_result_error(ctx, value, -1) }
func ResultValue(ctx *Context, value *Value) { sqlite3_result_value(ctx, value) }
func ResultZeroblob(ctx *Context, n int32)   { sqlite3_result_zeroblob(ctx, n) }
func ResultZeroblob64(ctx *Context, n uint64) int32 {
	return sqlite3_result_zeroblob64(ctx, n)
}
func ResultSubtype(ctx *Context, subtype uint32) { sqlite3_result_subtype(ctx, subtype) }
func ResultErrorToobig(ctx *Context)             { sqlite3_result_error_toobig(ctx) }
func ResultErrorNomem(ctx *Context)              { sqlite3_result_error_nomem(ctx) }
func ResultErrorCode(ctx *Context, code int32)   { sqlite3_result_error_code(ctx, code) }
