package libclang

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"unsafe"

	"github.com/ebitengine/purego"
)

type Index = purego_type_CXIndex

type TranslationUnit = purego_type_CXTranslationUnit

type Cursor = purego_type_CXCursor

type Type = purego_type_CXType

type String = purego_type_CXString

type SourceLocation = purego_type_CXSourceLocation

type SourceRange = purego_type_CXSourceRange

type File = purego_type_CXFile

type Token = purego_type_CXToken

type TokenKind = purego_type_CXTokenKind

type CursorKind = int32

type TypeKind = int32

type StorageClass = int32

type ChildVisitResult = int32

const (
	DetailedPreprocessingRecord        = purego_const_CXTranslationUnit_DetailedPreprocessingRecord
	SkipFunctionBodies                 = purego_const_CXTranslationUnit_SkipFunctionBodies
	DefaultParseOptions         uint32 = DetailedPreprocessingRecord | SkipFunctionBodies

	CursorStructDecl       CursorKind = purego_const_CXCursor_StructDecl
	CursorUnionDecl        CursorKind = purego_const_CXCursor_UnionDecl
	CursorEnumDecl         CursorKind = purego_const_CXCursor_EnumDecl
	CursorFieldDecl        CursorKind = purego_const_CXCursor_FieldDecl
	CursorEnumConstantDecl CursorKind = purego_const_CXCursor_EnumConstantDecl
	CursorFunctionDecl     CursorKind = purego_const_CXCursor_FunctionDecl
	CursorVarDecl          CursorKind = purego_const_CXCursor_VarDecl
	CursorParmDecl         CursorKind = purego_const_CXCursor_ParmDecl
	CursorTypedefDecl      CursorKind = purego_const_CXCursor_TypedefDecl
	CursorTranslationUnit  CursorKind = purego_const_CXCursor_TranslationUnit
	CursorMacroDefinition  CursorKind = purego_const_CXCursor_MacroDefinition

	TypeVoid            TypeKind = purego_const_CXType_Void
	TypeBool            TypeKind = purego_const_CXType_Bool
	TypeCharU           TypeKind = purego_const_CXType_Char_U
	TypeUChar           TypeKind = purego_const_CXType_UChar
	TypeUShort          TypeKind = purego_const_CXType_UShort
	TypeUInt            TypeKind = purego_const_CXType_UInt
	TypeULong           TypeKind = purego_const_CXType_ULong
	TypeULongLong       TypeKind = purego_const_CXType_ULongLong
	TypeCharS           TypeKind = purego_const_CXType_Char_S
	TypeSChar           TypeKind = purego_const_CXType_SChar
	TypeShort           TypeKind = purego_const_CXType_Short
	TypeInt             TypeKind = purego_const_CXType_Int
	TypeLong            TypeKind = purego_const_CXType_Long
	TypeLongLong        TypeKind = purego_const_CXType_LongLong
	TypeFloat           TypeKind = purego_const_CXType_Float
	TypeDouble          TypeKind = purego_const_CXType_Double
	TypePointer         TypeKind = purego_const_CXType_Pointer
	TypeRecord          TypeKind = purego_const_CXType_Record
	TypeEnum            TypeKind = purego_const_CXType_Enum
	TypeTypedef         TypeKind = purego_const_CXType_Typedef
	TypeFunctionNoProto TypeKind = purego_const_CXType_FunctionNoProto
	TypeFunctionProto   TypeKind = purego_const_CXType_FunctionProto
	TypeConstantArray   TypeKind = purego_const_CXType_ConstantArray

	StorageClassExtern StorageClass = purego_const_CX_SC_Extern

	ChildVisitBreak    ChildVisitResult = purego_const_CXChildVisit_Break
	ChildVisitContinue ChildVisitResult = purego_const_CXChildVisit_Continue
	ChildVisitRecurse  ChildVisitResult = purego_const_CXChildVisit_Recurse

	TokenPunctuation TokenKind = purego_const_CXToken_Punctuation
	TokenKeyword     TokenKind = purego_const_CXToken_Keyword
	TokenIdentifier  TokenKind = purego_const_CXToken_Identifier
	TokenLiteral     TokenKind = purego_const_CXToken_Literal
	TokenComment     TokenKind = purego_const_CXToken_Comment
)

type Library struct {
	handle uintptr
}

func Load() (*Library, error) {
	libraryPath, err := resolveLibraryPath()
	if err != nil {
		return nil, err
	}

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		return nil, fmt.Errorf("failed to open libclang: %w", err)
	}

	if err := purego_clang_register_functions(handle); err != nil {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			return nil, fmt.Errorf("%w (also failed to close handle: %v)", err, closeErr)
		}
		return nil, err
	}

	return &Library{handle: handle}, nil
}

func (library *Library) Close() error {
	if library == nil || library.handle == 0 {
		return nil
	}

	err := purego.Dlclose(library.handle)
	library.handle = 0
	if err != nil {
		return fmt.Errorf("failed to close libclang: %w", err)
	}
	return nil
}

func (library *Library) CreateIndex(excludeDeclarationsFromPCH int32, displayDiagnostics int32) Index {
	return Index(purego_func_clang_createIndex(excludeDeclarationsFromPCH, displayDiagnostics))
}

func (library *Library) DisposeIndex(index Index) {
	if index == 0 {
		return
	}
	purego_func_clang_disposeIndex(uintptr(index))
}

func (library *Library) ParseTranslationUnit(
	index Index,
	headerPath string,
	commandLineArgs []string,
	options uint32,
) (TranslationUnit, error) {
	arguments := newCStringArray(commandLineArgs)
	translationUnit := TranslationUnit(
		purego_func_clang_parseTranslationUnit(
			uintptr(index),
			headerPath,
			arguments.pointer(),
			int32(len(arguments.ptrs)),
			0,
			0,
			options,
		),
	)
	runtime.KeepAlive(arguments.raw)
	runtime.KeepAlive(arguments.ptrs)

	if translationUnit == 0 {
		return 0, fmt.Errorf("clang_parseTranslationUnit returned nil translation unit for %s", headerPath)
	}
	return translationUnit, nil
}

func (library *Library) DisposeTranslationUnit(translationUnit TranslationUnit) {
	if translationUnit == 0 {
		return
	}
	purego_func_clang_disposeTranslationUnit(uintptr(translationUnit))
}

func (library *Library) NumDiagnostics(translationUnit TranslationUnit) uint32 {
	if translationUnit == 0 {
		return 0
	}
	return purego_func_clang_getNumDiagnostics(uintptr(translationUnit))
}

func CopyString(value String) string {
	text := purego_func_clang_getCString(value)
	purego_func_clang_disposeString(value)
	return text
}

func (library *Library) TranslationUnitCursor(translationUnit TranslationUnit) Cursor {
	return purego_func_clang_getTranslationUnitCursor(uintptr(translationUnit))
}

func (library *Library) File(translationUnit TranslationUnit, fileName string) File {
	return File(purego_func_clang_getFile(uintptr(translationUnit), fileName))
}

func (library *Library) Location(
	translationUnit TranslationUnit,
	file File,
	line uint32,
	column uint32,
) SourceLocation {
	return purego_func_clang_getLocation(uintptr(translationUnit), uintptr(file), line, column)
}

func (library *Library) Cursor(translationUnit TranslationUnit, location SourceLocation) Cursor {
	return purego_func_clang_getCursor(uintptr(translationUnit), location)
}

func (library *Library) CursorKind(cursor Cursor) CursorKind {
	return CursorKind(purego_func_clang_getCursorKind(cursor))
}

func (library *Library) CursorKindSpelling(kind CursorKind) string {
	return CopyString(purego_func_clang_getCursorKindSpelling(int32(kind)))
}

func (library *Library) CursorSpelling(cursor Cursor) string {
	return CopyString(purego_func_clang_getCursorSpelling(cursor))
}

func (library *Library) CursorRawCommentText(cursor Cursor) string {
	return CopyString(purego_func_clang_Cursor_getRawCommentText(cursor))
}

func (library *Library) CursorLocation(cursor Cursor) SourceLocation {
	return purego_func_clang_getCursorLocation(cursor)
}

func (library *Library) CursorExtent(cursor Cursor) SourceRange {
	return purego_func_clang_getCursorExtent(cursor)
}

func (library *Library) ExpansionLocation(location SourceLocation) (File, uint32, uint32, uint32) {
	var file File
	var line uint32
	var column uint32
	var offset uint32
	purego_func_clang_getExpansionLocation(
		location,
		uintptr(unsafe.Pointer(&file)),
		uintptr(unsafe.Pointer(&line)),
		uintptr(unsafe.Pointer(&column)),
		uintptr(unsafe.Pointer(&offset)),
	)
	return file, line, column, offset
}

func (library *Library) FileName(file File) string {
	return CopyString(purego_func_clang_getFileName(uintptr(file)))
}

func (library *Library) CursorType(cursor Cursor) Type {
	return purego_func_clang_getCursorType(cursor)
}

func (library *Library) CursorResultType(cursor Cursor) Type {
	return purego_func_clang_getCursorResultType(cursor)
}

func (library *Library) CursorTypedefUnderlyingType(cursor Cursor) Type {
	return purego_func_clang_getTypedefDeclUnderlyingType(cursor)
}

func (library *Library) CursorNumArguments(cursor Cursor) int32 {
	return purego_func_clang_Cursor_getNumArguments(cursor)
}

func (library *Library) CursorArgument(cursor Cursor, index uint32) Cursor {
	return purego_func_clang_Cursor_getArgument(cursor, uint32(index))
}

func (library *Library) CursorStorageClass(cursor Cursor) StorageClass {
	return StorageClass(purego_func_clang_Cursor_getStorageClass(cursor))
}

func (library *Library) IsMacroFunctionLike(cursor Cursor) bool {
	return purego_func_clang_Cursor_isMacroFunctionLike(cursor) != 0
}

func (library *Library) IsMacroBuiltin(cursor Cursor) bool {
	return purego_func_clang_Cursor_isMacroBuiltin(cursor) != 0
}

func (library *Library) IsCursorDefinition(cursor Cursor) bool {
	return purego_func_clang_isCursorDefinition(cursor) != 0
}

func (library *Library) CanonicalType(typ Type) Type {
	return purego_func_clang_getCanonicalType(typ)
}

func (library *Library) PointeeType(typ Type) Type {
	return purego_func_clang_getPointeeType(typ)
}

func (library *Library) TypeDeclaration(typ Type) Cursor {
	return purego_func_clang_getTypeDeclaration(typ)
}

func (library *Library) TypeSpelling(typ Type) string {
	return CopyString(purego_func_clang_getTypeSpelling(typ))
}

func (library *Library) TypeKind(typ Type) TypeKind {
	return TypeKind(typ.kind)
}

func (library *Library) TypeKindSpelling(kind TypeKind) string {
	return CopyString(purego_func_clang_getTypeKindSpelling(int32(kind)))
}

func (library *Library) TypeSize(typ Type) int64 {
	return purego_func_clang_Type_getSizeOf(typ)
}

func (library *Library) TypeAlign(typ Type) int64 {
	return purego_func_clang_Type_getAlignOf(typ)
}

func (library *Library) IsConstQualifiedType(typ Type) bool {
	return purego_func_clang_isConstQualifiedType(typ) != 0
}

func (library *Library) TokenKind(token Token) TokenKind {
	return TokenKind(purego_func_clang_getTokenKind(token))
}

func (library *Library) TokenSpelling(translationUnit TranslationUnit, token Token) string {
	return CopyString(purego_func_clang_getTokenSpelling(uintptr(translationUnit), token))
}

func (library *Library) Tokenize(translationUnit TranslationUnit, sourceRange SourceRange) []Token {
	var tokensPtr uintptr
	var tokenCount uint32
	purego_func_clang_tokenize(
		uintptr(translationUnit),
		sourceRange,
		uintptr(unsafe.Pointer(&tokensPtr)),
		uintptr(unsafe.Pointer(&tokenCount)),
	)
	if tokensPtr == 0 || tokenCount == 0 {
		return nil
	}
	return unsafe.Slice((*Token)(unsafe.Pointer(tokensPtr)), int(tokenCount))
}

func (library *Library) DisposeTokens(translationUnit TranslationUnit, tokens []Token) {
	if len(tokens) == 0 {
		return
	}
	purego_func_clang_disposeTokens(
		uintptr(translationUnit),
		uintptr(unsafe.Pointer(&tokens[0])),
		uint32(len(tokens)),
	)
}

func (library *Library) VisitChildrenRaw(
	parent Cursor,
	visitor uintptr,
	clientData uintptr,
) uint32 {
	// A typed Go callback wrapper is deferred until purego can safely bridge
	// libclang's by-value CXCursor callback ABI.
	return purego_func_clang_visitChildren(parent, visitor, clientData)
}

type cStringArray struct {
	raw  [][]byte
	ptrs []*byte
}

func newCStringArray(values []string) cStringArray {
	raw := make([][]byte, len(values))
	ptrs := make([]*byte, len(values))
	for index, value := range values {
		raw[index] = append([]byte(value), 0)
		ptrs[index] = &raw[index][0]
	}
	return cStringArray{
		raw:  raw,
		ptrs: ptrs,
	}
}

func (values cStringArray) pointer() uintptr {
	if len(values.ptrs) == 0 {
		return 0
	}
	return uintptr(unsafe.Pointer(&values.ptrs[0]))
}

func resolveLibraryPath() (string, error) {
	libraryPath := os.Getenv("LIBCLANG_PATH")
	if libraryPath == "" {
		return defaultLibraryName(), nil
	}

	info, err := os.Stat(libraryPath)
	if err != nil {
		return "", fmt.Errorf("failed to stat LIBCLANG_PATH %q: %w", libraryPath, err)
	}

	if !info.IsDir() {
		return libraryPath, nil
	}

	for _, candidate := range libraryFileCandidates() {
		resolved := filepath.Join(libraryPath, candidate)
		if _, err := os.Stat(resolved); err == nil {
			return resolved, nil
		}
	}

	for _, pattern := range libraryGlobCandidates() {
		matches, err := filepath.Glob(filepath.Join(libraryPath, pattern))
		if err != nil {
			return "", fmt.Errorf("failed to resolve libclang from LIBCLANG_PATH %q: %w", libraryPath, err)
		}
		if len(matches) != 0 {
			return matches[0], nil
		}
	}

	return "", fmt.Errorf("LIBCLANG_PATH %q does not contain a libclang shared library", libraryPath)
}

func defaultLibraryName() string {
	if runtime.GOOS == "darwin" {
		return "libclang.dylib"
	}
	return "libclang.so"
}

func libraryFileCandidates() []string {
	if runtime.GOOS == "darwin" {
		return []string{"libclang.dylib"}
	}
	return []string{"libclang.so"}
}

func libraryGlobCandidates() []string {
	if runtime.GOOS == "darwin" {
		return nil
	}
	return []string{"libclang.so.*"}
}
