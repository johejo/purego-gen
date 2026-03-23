package duckdbsys

// Logical Type

func CreateLogicalType(typeID int32) LogicalType {
	return duckdb_create_logical_type(typeID)
}

func LogicalTypeGetAlias(logicalType LogicalType) string {
	return ownedString(duckdb_logical_type_get_alias(logicalType))
}

func LogicalTypeSetAlias(logicalType LogicalType, alias string) {
	duckdb_logical_type_set_alias(logicalType, alias)
}

func CreateListType(childType LogicalType) LogicalType {
	return duckdb_create_list_type(childType)
}

func CreateArrayType(childType LogicalType, size uint64) LogicalType {
	return duckdb_create_array_type(childType, size)
}

func CreateMapType(keyType LogicalType, valueType LogicalType) LogicalType {
	return duckdb_create_map_type(keyType, valueType)
}

func CreateUnionType(memberTypes *LogicalType, memberNames uintptr, memberCount uint64) LogicalType {
	return duckdb_create_union_type(memberTypes, memberNames, memberCount)
}

func CreateStructType(memberTypes *LogicalType, memberNames uintptr, memberCount uint64) LogicalType {
	return duckdb_create_struct_type(memberTypes, memberNames, memberCount)
}

func CreateEnumType(memberNames uintptr, memberCount uint64) LogicalType {
	return duckdb_create_enum_type(memberNames, memberCount)
}

func CreateDecimalType(width uint8, scale uint8) LogicalType {
	return duckdb_create_decimal_type(width, scale)
}

func GetTypeId(logicalType LogicalType) int32 {
	return duckdb_get_type_id(logicalType)
}

func DecimalWidth(logicalType LogicalType) uint8 {
	return duckdb_decimal_width(logicalType)
}

func DecimalScale(logicalType LogicalType) uint8 {
	return duckdb_decimal_scale(logicalType)
}

func DecimalInternalType(logicalType LogicalType) int32 {
	return duckdb_decimal_internal_type(logicalType)
}

func EnumInternalType(logicalType LogicalType) int32 {
	return duckdb_enum_internal_type(logicalType)
}

func EnumDictionarySize(logicalType LogicalType) uint32 {
	return duckdb_enum_dictionary_size(logicalType)
}

func EnumDictionaryValue(logicalType LogicalType, index uint64) string {
	return ownedString(duckdb_enum_dictionary_value(logicalType, index))
}

func ListTypeChildType(logicalType LogicalType) LogicalType {
	return duckdb_list_type_child_type(logicalType)
}

func ArrayTypeChildType(logicalType LogicalType) LogicalType {
	return duckdb_array_type_child_type(logicalType)
}

func ArrayTypeArraySize(logicalType LogicalType) uint64 {
	return duckdb_array_type_array_size(logicalType)
}

func MapTypeKeyType(logicalType LogicalType) LogicalType {
	return duckdb_map_type_key_type(logicalType)
}

func MapTypeValueType(logicalType LogicalType) LogicalType {
	return duckdb_map_type_value_type(logicalType)
}

func StructTypeChildCount(logicalType LogicalType) uint64 {
	return duckdb_struct_type_child_count(logicalType)
}

func StructTypeChildName(logicalType LogicalType, index uint64) string {
	return ownedString(duckdb_struct_type_child_name(logicalType, index))
}

func StructTypeChildType(logicalType LogicalType, index uint64) LogicalType {
	return duckdb_struct_type_child_type(logicalType, index)
}

func UnionTypeMemberCount(logicalType LogicalType) uint64 {
	return duckdb_union_type_member_count(logicalType)
}

func UnionTypeMemberName(logicalType LogicalType, index uint64) string {
	return ownedString(duckdb_union_type_member_name(logicalType, index))
}

func UnionTypeMemberType(logicalType LogicalType, index uint64) LogicalType {
	return duckdb_union_type_member_type(logicalType, index)
}

func DestroyLogicalType(logicalType *LogicalType) {
	duckdb_destroy_logical_type(logicalType)
}
