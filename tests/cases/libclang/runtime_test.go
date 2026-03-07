package fixture

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/ebitengine/purego"
)

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

	translationUnit := purego_func_clang_parseTranslationUnit(
		index,
		headerPath,
		0,
		0,
		0,
		0,
		0,
	)
	if translationUnit == 0 {
		t.Fatal("clang_parseTranslationUnit returned nil translation unit")
	}
	t.Cleanup(func() {
		purego_func_clang_disposeTranslationUnit(translationUnit)
	})

	if got := purego_func_clang_getNumDiagnostics(translationUnit); got != 0 {
		t.Fatalf("clang_getNumDiagnostics() = %d, want 0", got)
	}
}
