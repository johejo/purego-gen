package libclang

import (
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"
)

func TestParseTranslationUnitSmoke(t *testing.T) {
	if os.Getenv("LIBCLANG_PATH") == "" {
		t.Skip("LIBCLANG_PATH is not set")
	}

	library, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	t.Cleanup(func() {
		if closeErr := library.Close(); closeErr != nil {
			t.Errorf("Close() error = %v", closeErr)
		}
	})

	index := library.CreateIndex(0, 0)
	if index == 0 {
		t.Fatal("CreateIndex() returned nil index")
	}
	t.Cleanup(func() {
		library.DisposeIndex(index)
	})

	headerPath := mustRepoPath(t, "tests", "cases", "libclang", "parse_input.h")

	translationUnitWithoutDefine, err := library.ParseTranslationUnit(
		index,
		headerPath,
		nil,
		DefaultParseOptions,
	)
	if err != nil {
		t.Fatalf("ParseTranslationUnit() without define error = %v", err)
	}
	t.Cleanup(func() {
		library.DisposeTranslationUnit(translationUnitWithoutDefine)
	})
	if got := library.NumDiagnostics(translationUnitWithoutDefine); got == 0 {
		t.Fatal("NumDiagnostics() without required define = 0, want > 0")
	}

	translationUnitWithDefine, err := library.ParseTranslationUnit(
		index,
		headerPath,
		[]string{"-DPUREGO_GEN_STAGE1_PARSE=1"},
		DefaultParseOptions,
	)
	if err != nil {
		t.Fatalf("ParseTranslationUnit() with define error = %v", err)
	}
	t.Cleanup(func() {
		library.DisposeTranslationUnit(translationUnitWithDefine)
	})
	if got := library.NumDiagnostics(translationUnitWithDefine); got != 0 {
		t.Fatalf("NumDiagnostics() with required define = %d, want 0", got)
	}

	rootCursor := library.TranslationUnitCursor(translationUnitWithDefine)
	if got := library.CursorKind(rootCursor); got != CursorTranslationUnit {
		t.Fatalf("CursorKind(rootCursor) = %d, want %d", got, CursorTranslationUnit)
	}
	if got := library.CursorKindSpelling(CursorTranslationUnit); !strings.Contains(got, "TranslationUnit") {
		t.Fatalf("CursorKindSpelling(CursorTranslationUnit) = %q", got)
	}

	functionCursor := mustCursorBySpelling(
		t,
		library,
		translationUnitWithDefine,
		headerPath,
		"purego_gen_stage1_make_point",
	)
	if got := library.CursorKind(functionCursor); got != CursorFunctionDecl {
		t.Fatalf("CursorKind(functionCursor) = %d, want %d", got, CursorFunctionDecl)
	}
	if got := library.CursorSpelling(functionCursor); got != "purego_gen_stage1_make_point" {
		t.Fatalf("CursorSpelling(functionCursor) = %q", got)
	}
	if got := library.CursorRawCommentText(functionCursor); !strings.Contains(got, "stage1 point docs") {
		t.Fatalf("CursorRawCommentText(functionCursor) = %q", got)
	}
	if library.IsCursorDefinition(functionCursor) {
		t.Fatal("IsCursorDefinition(functionCursor) = true, want false")
	}
	if got := library.CursorNumArguments(functionCursor); got != 1 {
		t.Fatalf("CursorNumArguments(functionCursor) = %d, want 1", got)
	}

	argumentCursor := library.CursorArgument(functionCursor, 0)
	if got := library.CursorKind(argumentCursor); got != CursorParmDecl {
		t.Fatalf("CursorKind(argumentCursor) = %d, want %d", got, CursorParmDecl)
	}
	if got := library.CursorSpelling(argumentCursor); got != "value" {
		t.Fatalf("CursorSpelling(argumentCursor) = %q, want value", got)
	}

	resultType := library.CursorResultType(functionCursor)
	if got := library.TypeSpelling(resultType); got != "purego_gen_stage1_point_t" {
		t.Fatalf("TypeSpelling(resultType) = %q, want purego_gen_stage1_point_t", got)
	}
	canonicalResultType := library.CanonicalType(resultType)
	if got := library.TypeKind(canonicalResultType); got != TypeRecord {
		t.Fatalf("TypeKind(canonicalResultType) = %d, want %d", got, TypeRecord)
	}
	if got := library.TypeKindSpelling(TypeRecord); got != "Record" {
		t.Fatalf("TypeKindSpelling(TypeRecord) = %q, want Record", got)
	}
	if got := library.TypeSize(canonicalResultType); got != 8 {
		t.Fatalf("TypeSize(canonicalResultType) = %d, want 8", got)
	}
	if got := library.TypeAlign(canonicalResultType); got != 4 {
		t.Fatalf("TypeAlign(canonicalResultType) = %d, want 4", got)
	}

	typeDeclaration := library.TypeDeclaration(canonicalResultType)
	if got := library.CursorKind(typeDeclaration); got != CursorStructDecl {
		t.Fatalf("CursorKind(typeDeclaration) = %d, want %d", got, CursorStructDecl)
	}

	locationFile, line, column, offset := library.ExpansionLocation(library.CursorLocation(functionCursor))
	if got := library.FileName(locationFile); got != headerPath {
		t.Fatalf("FileName(locationFile) = %q, want %q", got, headerPath)
	}
	if line == 0 || column == 0 {
		t.Fatalf("ExpansionLocation(functionCursor) line=%d column=%d, want > 0", line, column)
	}
	if offset == 0 {
		t.Fatal("ExpansionLocation(functionCursor) offset = 0, want > 0")
	}

	typedefCursor := mustCursorBySpelling(
		t,
		library,
		translationUnitWithDefine,
		headerPath,
		"purego_gen_stage1_name_t",
	)
	if got := library.CursorKind(typedefCursor); got != CursorTypedefDecl {
		t.Fatalf("CursorKind(typedefCursor) = %d, want %d", got, CursorTypedefDecl)
	}
	underlyingType := library.CursorTypedefUnderlyingType(typedefCursor)
	if got := library.TypeKind(underlyingType); got != TypePointer {
		t.Fatalf("TypeKind(underlyingType) = %d, want %d", got, TypePointer)
	}
	if !library.IsConstQualifiedType(library.PointeeType(underlyingType)) {
		t.Fatal("IsConstQualifiedType(pointee(underlyingType)) = false, want true")
	}

	varCursor := mustCursorBySpelling(
		t,
		library,
		translationUnitWithDefine,
		headerPath,
		"purego_gen_stage1_counter",
	)
	if got := library.CursorKind(varCursor); got != CursorVarDecl {
		t.Fatalf("CursorKind(varCursor) = %d, want %d", got, CursorVarDecl)
	}
	if got := library.CursorStorageClass(varCursor); got != StorageClassExtern {
		t.Fatalf("CursorStorageClass(varCursor) = %d, want %d", got, StorageClassExtern)
	}

	objectMacroCursor := mustCursorBySpelling(
		t,
		library,
		translationUnitWithDefine,
		headerPath,
		"PUREGO_GEN_STAGE1_OBJECT_MACRO",
	)
	if got := library.CursorKind(objectMacroCursor); got != CursorMacroDefinition {
		t.Fatalf("CursorKind(objectMacroCursor) = %d, want %d", got, CursorMacroDefinition)
	}
	if library.IsMacroFunctionLike(objectMacroCursor) {
		t.Fatal("IsMacroFunctionLike(objectMacroCursor) = true, want false")
	}
	if library.IsMacroBuiltin(objectMacroCursor) {
		t.Fatal("IsMacroBuiltin(objectMacroCursor) = true, want false")
	}
	objectMacroTokens := library.Tokenize(translationUnitWithDefine, library.CursorExtent(objectMacroCursor))
	if len(objectMacroTokens) == 0 {
		t.Fatal("Tokenize(objectMacroCursor) returned no tokens")
	}
	if got := library.TokenKind(objectMacroTokens[0]); got != TokenIdentifier {
		t.Fatalf("TokenKind(objectMacroTokens[0]) = %d, want %d", got, TokenIdentifier)
	}
	if got := tokenSpellings(library, translationUnitWithDefine, objectMacroTokens); !slices.Equal(
		got,
		[]string{"PUREGO_GEN_STAGE1_OBJECT_MACRO", "(", "1u", "<<", "3", ")"},
	) {
		t.Fatalf("object macro token spellings = %#v", got)
	}
	library.DisposeTokens(translationUnitWithDefine, objectMacroTokens)

	functionMacroCursor := mustCursorBySpelling(
		t,
		library,
		translationUnitWithDefine,
		headerPath,
		"PUREGO_GEN_STAGE1_FUNCTION_MACRO",
	)
	if got := library.CursorKind(functionMacroCursor); got != CursorMacroDefinition {
		t.Fatalf("CursorKind(functionMacroCursor) = %d, want %d", got, CursorMacroDefinition)
	}
	if !library.IsMacroFunctionLike(functionMacroCursor) {
		t.Fatal("IsMacroFunctionLike(functionMacroCursor) = false, want true")
	}
	if library.IsMacroBuiltin(functionMacroCursor) {
		t.Fatal("IsMacroBuiltin(functionMacroCursor) = true, want false")
	}
	functionMacroTokens := library.Tokenize(translationUnitWithDefine, library.CursorExtent(functionMacroCursor))
	if len(functionMacroTokens) == 0 {
		t.Fatal("Tokenize(functionMacroCursor) returned no tokens")
	}
	if got := tokenSpellings(library, translationUnitWithDefine, functionMacroTokens); !slices.Equal(
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
	library.DisposeTokens(translationUnitWithDefine, functionMacroTokens)
}

func mustRepoPath(t *testing.T, elements ...string) string {
	t.Helper()

	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}

	allElements := append([]string{filepath.Dir(currentFile), "..", "..", ".."}, elements...)
	return filepath.Clean(filepath.Join(allElements...))
}

func mustCursorBySpelling(
	t *testing.T,
	library *Library,
	translationUnit TranslationUnit,
	headerPath string,
	spelling string,
) Cursor {
	t.Helper()

	line, column := mustLineColumnForToken(t, headerPath, spelling)
	file := library.File(translationUnit, headerPath)
	if file == 0 {
		t.Fatalf("File(%q) returned nil", headerPath)
	}
	location := library.Location(translationUnit, file, uint32(line), uint32(column))
	cursor := library.Cursor(translationUnit, location)
	if got := library.CursorSpelling(cursor); got != spelling {
		t.Fatalf("Cursor(%q) spelling = %q", spelling, got)
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

func tokenSpellings(
	library *Library,
	translationUnit TranslationUnit,
	tokens []Token,
) []string {
	spellings := make([]string, 0, len(tokens))
	for _, token := range tokens {
		spellings = append(spellings, library.TokenSpelling(translationUnit, token))
	}
	return spellings
}
