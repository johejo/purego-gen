//go:build purego_gen_case_runtime
// +build purego_gen_case_runtime

package fixture

import (
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
)

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

func parseHeader(
	t *testing.T,
	index uintptr,
	headerPath string,
	commandLineArgs cStringArray,
	options uint32,
) uintptr {
	t.Helper()

	translationUnit := purego_func_clang_parseTranslationUnit(
		index,
		headerPath,
		commandLineArgs.pointer(),
		int32(len(commandLineArgs.ptrs)),
		0,
		0,
		options,
	)
	runtime.KeepAlive(commandLineArgs.raw)
	runtime.KeepAlive(commandLineArgs.ptrs)
	if translationUnit == 0 {
		t.Fatal("clang_parseTranslationUnit returned nil translation unit")
	}
	return translationUnit
}

func consumeString(value purego_type_CXString) string {
	text := purego_func_clang_getCString(value)
	purego_func_clang_disposeString(value)
	return text
}

func TestGeneratedBindingsParseHeaderWithLibclang(t *testing.T) {
	libraryPath := os.Getenv("PUREGO_GEN_TEST_LIB")
	if libraryPath == "" {
		t.Fatal("PUREGO_GEN_TEST_LIB must be set")
	}

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		t.Fatalf("open library: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			t.Errorf("close library: %v", closeErr)
		}
	})

	if err := purego_clang_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}

	index := purego_func_clang_createIndex(0, 0)
	if index == 0 {
		t.Fatal("clang_createIndex returned nil index")
	}
	t.Cleanup(func() {
		purego_func_clang_disposeIndex(index)
	})

	headerPath, err := filepath.Abs("parse_input.h")
	if err != nil {
		t.Fatalf("resolve parse_input.h: %v", err)
	}

	options := uint32(
		purego_const_CXTranslationUnit_DetailedPreprocessingRecord |
			purego_const_CXTranslationUnit_SkipFunctionBodies,
	)
	if options == 0 {
		t.Fatal("translation-unit parse options should not be zero")
	}

	translationUnitWithoutDefine := parseHeader(t, index, headerPath, cStringArray{}, options)
	t.Cleanup(func() {
		purego_func_clang_disposeTranslationUnit(translationUnitWithoutDefine)
	})
	if got := purego_func_clang_getNumDiagnostics(translationUnitWithoutDefine); got == 0 {
		t.Fatal("clang_getNumDiagnostics() without required define = 0, want > 0")
	}

	commandLineArgs := newCStringArray([]string{"-DPUREGO_GEN_STAGE1_PARSE=1"})
	translationUnitWithDefine := parseHeader(t, index, headerPath, commandLineArgs, options)
	t.Cleanup(func() {
		purego_func_clang_disposeTranslationUnit(translationUnitWithDefine)
	})
	if got := purego_func_clang_getNumDiagnostics(translationUnitWithDefine); got != 0 {
		t.Fatalf("clang_getNumDiagnostics() with required define = %d, want 0", got)
	}

	rootCursor := purego_func_clang_getTranslationUnitCursor(translationUnitWithDefine)
	if got := purego_func_clang_getCursorKind(rootCursor); got != purego_const_CXCursor_TranslationUnit {
		t.Fatalf(
			"clang_getCursorKind(rootCursor) = %d, want %d",
			got,
			purego_const_CXCursor_TranslationUnit,
		)
	}
	if got := consumeString(
		purego_func_clang_getCursorKindSpelling(purego_const_CXCursor_TranslationUnit),
	); !strings.Contains(got, "TranslationUnit") {
		t.Fatalf("clang_getCursorKindSpelling(CXCursor_TranslationUnit) = %q", got)
	}

	functionCursor := mustCursorBySpelling(
		t,
		translationUnitWithDefine,
		headerPath,
		"purego_gen_stage1_make_point",
	)
	if got := purego_func_clang_getCursorKind(functionCursor); got != purego_const_CXCursor_FunctionDecl {
		t.Fatalf("clang_getCursorKind(functionCursor) = %d, want %d", got, purego_const_CXCursor_FunctionDecl)
	}
	if got := consumeString(purego_func_clang_getCursorSpelling(functionCursor)); got != "purego_gen_stage1_make_point" {
		t.Fatalf("clang_getCursorSpelling(functionCursor) = %q, want purego_gen_stage1_make_point", got)
	}
	if got := consumeString(purego_func_clang_Cursor_getRawCommentText(functionCursor)); !strings.Contains(got, "stage1 point docs") {
		t.Fatalf("clang_Cursor_getRawCommentText(functionCursor) = %q", got)
	}
	if got := purego_func_clang_isCursorDefinition(functionCursor); got != 0 {
		t.Fatalf("clang_isCursorDefinition(functionCursor) = %d, want 0", got)
	}
	if got := purego_func_clang_Cursor_getNumArguments(functionCursor); got != 1 {
		t.Fatalf("clang_Cursor_getNumArguments(functionCursor) = %d, want 1", got)
	}

	argCursor := purego_func_clang_Cursor_getArgument(functionCursor, 0)
	if got := purego_func_clang_getCursorKind(argCursor); got != purego_const_CXCursor_ParmDecl {
		t.Fatalf("clang_getCursorKind(argCursor) = %d, want %d", got, purego_const_CXCursor_ParmDecl)
	}
	if got := consumeString(purego_func_clang_getCursorSpelling(argCursor)); got != "value" {
		t.Fatalf("clang_getCursorSpelling(argCursor) = %q, want value", got)
	}

	resultType := purego_func_clang_getCursorResultType(functionCursor)
	if got := consumeString(purego_func_clang_getTypeSpelling(resultType)); got != "purego_gen_stage1_point_t" {
		t.Fatalf("clang_getTypeSpelling(resultType) = %q, want purego_gen_stage1_point_t", got)
	}
	canonicalResultType := purego_func_clang_getCanonicalType(resultType)
	if got := canonicalResultType.kind; got != purego_const_CXType_Record {
		t.Fatalf("canonicalResultType.kind = %d, want %d", got, purego_const_CXType_Record)
	}
	if got := consumeString(purego_func_clang_getTypeKindSpelling(purego_const_CXType_Record)); got != "Record" {
		t.Fatalf("clang_getTypeKindSpelling(CXType_Record) = %q, want Record", got)
	}
	if got := purego_func_clang_Type_getSizeOf(canonicalResultType); got != 8 {
		t.Fatalf("clang_Type_getSizeOf(canonicalResultType) = %d, want 8", got)
	}
	if got := purego_func_clang_Type_getAlignOf(canonicalResultType); got != 4 {
		t.Fatalf("clang_Type_getAlignOf(canonicalResultType) = %d, want 4", got)
	}

	typeDeclaration := purego_func_clang_getTypeDeclaration(canonicalResultType)
	if got := purego_func_clang_getCursorKind(typeDeclaration); got != purego_const_CXCursor_StructDecl {
		t.Fatalf("clang_getCursorKind(typeDeclaration) = %d, want %d", got, purego_const_CXCursor_StructDecl)
	}

	location := purego_func_clang_getCursorLocation(functionCursor)
	var file purego_type_CXFile
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
	if got := consumeString(purego_func_clang_getFileName(uintptr(file))); got != headerPath {
		t.Fatalf("clang_getFileName(file) = %q, want %q", got, headerPath)
	}
	if line == 0 || column == 0 || offset == 0 {
		t.Fatalf("clang_getExpansionLocation() line=%d column=%d offset=%d, want > 0", line, column, offset)
	}

	typedefCursor := mustCursorBySpelling(
		t,
		translationUnitWithDefine,
		headerPath,
		"purego_gen_stage1_name_t",
	)
	if got := purego_func_clang_getCursorKind(typedefCursor); got != purego_const_CXCursor_TypedefDecl {
		t.Fatalf("clang_getCursorKind(typedefCursor) = %d, want %d", got, purego_const_CXCursor_TypedefDecl)
	}
	underlyingType := purego_func_clang_getTypedefDeclUnderlyingType(typedefCursor)
	if got := underlyingType.kind; got != purego_const_CXType_Pointer {
		t.Fatalf("underlyingType.kind = %d, want %d", got, purego_const_CXType_Pointer)
	}
	if got := purego_func_clang_isConstQualifiedType(purego_func_clang_getPointeeType(underlyingType)); got == 0 {
		t.Fatal("clang_isConstQualifiedType(pointee(underlyingType)) = 0, want non-zero")
	}

	varCursor := mustCursorBySpelling(
		t,
		translationUnitWithDefine,
		headerPath,
		"purego_gen_stage1_counter",
	)
	if got := purego_func_clang_getCursorKind(varCursor); got != purego_const_CXCursor_VarDecl {
		t.Fatalf("clang_getCursorKind(varCursor) = %d, want %d", got, purego_const_CXCursor_VarDecl)
	}
	if got := purego_func_clang_Cursor_getStorageClass(varCursor); got != purego_const_CX_SC_Extern {
		t.Fatalf("clang_Cursor_getStorageClass(varCursor) = %d, want %d", got, purego_const_CX_SC_Extern)
	}

	objectMacroCursor := mustCursorBySpelling(
		t,
		translationUnitWithDefine,
		headerPath,
		"PUREGO_GEN_STAGE1_OBJECT_MACRO",
	)
	if got := purego_func_clang_getCursorKind(objectMacroCursor); got != purego_const_CXCursor_MacroDefinition {
		t.Fatalf(
			"clang_getCursorKind(objectMacroCursor) = %d, want %d",
			got,
			purego_const_CXCursor_MacroDefinition,
		)
	}
	if got := purego_func_clang_Cursor_isMacroFunctionLike(objectMacroCursor); got != 0 {
		t.Fatalf("clang_Cursor_isMacroFunctionLike(objectMacroCursor) = %d, want 0", got)
	}
	if got := purego_func_clang_Cursor_isMacroBuiltin(objectMacroCursor); got != 0 {
		t.Fatalf("clang_Cursor_isMacroBuiltin(objectMacroCursor) = %d, want 0", got)
	}
	objectMacroTokens := tokenizeCursor(t, translationUnitWithDefine, objectMacroCursor)
	if got := purego_func_clang_getTokenKind(objectMacroTokens[0]); got != purego_const_CXToken_Identifier {
		t.Fatalf("clang_getTokenKind(objectMacroTokens[0]) = %d, want %d", got, purego_const_CXToken_Identifier)
	}
	if got := tokenSpellings(translationUnitWithDefine, objectMacroTokens); !slices.Equal(
		got,
		[]string{"PUREGO_GEN_STAGE1_OBJECT_MACRO", "(", "1u", "<<", "3", ")"},
	) {
		t.Fatalf("object macro token spellings = %#v", got)
	}
	disposeTokens(translationUnitWithDefine, objectMacroTokens)

	functionMacroCursor := mustCursorBySpelling(
		t,
		translationUnitWithDefine,
		headerPath,
		"PUREGO_GEN_STAGE1_FUNCTION_MACRO",
	)
	if got := purego_func_clang_getCursorKind(functionMacroCursor); got != purego_const_CXCursor_MacroDefinition {
		t.Fatalf(
			"clang_getCursorKind(functionMacroCursor) = %d, want %d",
			got,
			purego_const_CXCursor_MacroDefinition,
		)
	}
	if got := purego_func_clang_Cursor_isMacroFunctionLike(functionMacroCursor); got == 0 {
		t.Fatal("clang_Cursor_isMacroFunctionLike(functionMacroCursor) = 0, want non-zero")
	}
	if got := purego_func_clang_Cursor_isMacroBuiltin(functionMacroCursor); got != 0 {
		t.Fatalf("clang_Cursor_isMacroBuiltin(functionMacroCursor) = %d, want 0", got)
	}
	functionMacroTokens := tokenizeCursor(t, translationUnitWithDefine, functionMacroCursor)
	if got := tokenSpellings(translationUnitWithDefine, functionMacroTokens); !slices.Equal(
		got,
		[]string{
			"PUREGO_GEN_STAGE1_FUNCTION_MACRO",
			"(",
			"value",
			")",
			"(",
			"(",
			"value",
			")",
			"+",
			"PUREGO_GEN_STAGE1_OBJECT_MACRO",
			")",
		},
	) {
		t.Fatalf("function macro token spellings = %#v", got)
	}
	disposeTokens(translationUnitWithDefine, functionMacroTokens)
}

func mustCursorBySpelling(
	t *testing.T,
	translationUnit uintptr,
	headerPath string,
	spelling string,
) purego_type_CXCursor {
	t.Helper()

	line, column := mustLineColumnForToken(t, headerPath, spelling)
	file := purego_func_clang_getFile(translationUnit, headerPath)
	if file == 0 {
		t.Fatalf("clang_getFile(%q) returned nil", headerPath)
	}
	location := purego_func_clang_getLocation(translationUnit, file, uint32(line), uint32(column))
	cursor := purego_func_clang_getCursor(translationUnit, location)
	if got := consumeString(purego_func_clang_getCursorSpelling(cursor)); got != spelling {
		t.Fatalf("cursor spelling for %q = %q", spelling, got)
	}
	return cursor
}

func mustLineColumnForToken(t *testing.T, path string, token string) (int, int) {
	t.Helper()

	source, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile(%q) error = %v", path, err)
	}

	index := strings.Index(string(source), token)
	if index < 0 {
		t.Fatalf("token %q not found in %s", token, path)
	}

	line := 1
	column := 1
	for _, b := range source[:index] {
		if b == '\n' {
			line++
			column = 1
			continue
		}
		column++
	}
	return line, column
}

func tokenizeCursor(
	t *testing.T,
	translationUnit uintptr,
	cursor purego_type_CXCursor,
) []purego_type_CXToken {
	t.Helper()

	var tokensPtr uintptr
	var tokenCount uint32
	purego_func_clang_tokenize(
		translationUnit,
		purego_func_clang_getCursorExtent(cursor),
		uintptr(unsafe.Pointer(&tokensPtr)),
		uintptr(unsafe.Pointer(&tokenCount)),
	)
	if tokensPtr == 0 || tokenCount == 0 {
		t.Fatal("clang_tokenize returned no tokens")
	}
	return unsafe.Slice((*purego_type_CXToken)(unsafe.Pointer(tokensPtr)), int(tokenCount))
}

func disposeTokens(translationUnit uintptr, tokens []purego_type_CXToken) {
	if len(tokens) == 0 {
		return
	}
	purego_func_clang_disposeTokens(
		translationUnit,
		uintptr(unsafe.Pointer(&tokens[0])),
		uint32(len(tokens)),
	)
}

func tokenSpellings(translationUnit uintptr, tokens []purego_type_CXToken) []string {
	spellings := make([]string, 0, len(tokens))
	for _, token := range tokens {
		spellings = append(spellings, consumeString(purego_func_clang_getTokenSpelling(translationUnit, token)))
	}
	return spellings
}
