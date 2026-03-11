package libclang

import (
	"os"
	"path/filepath"
	"runtime"
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
