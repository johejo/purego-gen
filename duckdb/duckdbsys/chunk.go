package duckdbsys

// Data Chunk / Vector API

func CreateDataChunk(types *LogicalType, columnCount uint64) DataChunk {
	return duckdb_create_data_chunk(types, columnCount)
}

func DestroyDataChunk(chunk *DataChunk) {
	duckdb_destroy_data_chunk(chunk)
}

func DataChunkReset(chunk DataChunk) {
	duckdb_data_chunk_reset(chunk)
}

func DataChunkGetSize(chunk DataChunk) uint64 {
	return duckdb_data_chunk_get_size(chunk)
}

func DataChunkSetSize(chunk DataChunk, size uint64) {
	duckdb_data_chunk_set_size(chunk, size)
}

func DataChunkGetColumnCount(chunk DataChunk) uint64 {
	return duckdb_data_chunk_get_column_count(chunk)
}

func DataChunkGetVector(chunk DataChunk, colIdx uint64) Vector {
	return duckdb_data_chunk_get_vector(chunk, colIdx)
}

func VectorGetColumnType(vector Vector) LogicalType {
	return duckdb_vector_get_column_type(vector)
}

func VectorGetData(vector Vector) uintptr {
	return duckdb_vector_get_data(vector)
}

func VectorGetValidity(vector Vector) *uint64 {
	return duckdb_vector_get_validity(vector)
}

func VectorEnsureValidityWritable(vector Vector) {
	duckdb_vector_ensure_validity_writable(vector)
}

func VectorAssignStringElement(vector Vector, index uint64, str string) {
	duckdb_vector_assign_string_element(vector, index, str)
}

func VectorAssignStringElementLen(vector Vector, index uint64, str string, strLen uint64) {
	duckdb_vector_assign_string_element_len(vector, index, str, strLen)
}

func ListVectorGetChild(vector Vector) Vector {
	return duckdb_list_vector_get_child(vector)
}

func ListVectorGetSize(vector Vector) uint64 {
	return duckdb_list_vector_get_size(vector)
}

func ListVectorSetSize(vector Vector, size uint64) int32 {
	return duckdb_list_vector_set_size(vector, size)
}

func ListVectorReserve(vector Vector, requiredCapacity uint64) int32 {
	return duckdb_list_vector_reserve(vector, requiredCapacity)
}

func StructVectorGetChild(vector Vector, index uint64) Vector {
	return duckdb_struct_vector_get_child(vector, index)
}

func ArrayVectorGetChild(vector Vector) Vector {
	return duckdb_array_vector_get_child(vector)
}

func ValidityRowIsValid(validity *uint64, row uint64) bool {
	return duckdb_validity_row_is_valid(validity, row)
}

func ValiditySetRowValidity(validity *uint64, row uint64, valid bool) {
	duckdb_validity_set_row_validity(validity, row, valid)
}

func ValiditySetRowInvalid(validity *uint64, row uint64) {
	duckdb_validity_set_row_invalid(validity, row)
}

func ValiditySetRowValid(validity *uint64, row uint64) {
	duckdb_validity_set_row_valid(validity, row)
}

func VectorSize() uint64 {
	return duckdb_vector_size()
}

// Memory

func Free(ptr uintptr) {
	duckdb_free(ptr)
}

func Malloc(size uint64) uintptr {
	return duckdb_malloc(size)
}
