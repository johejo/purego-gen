package fixture

import (
	"os"
	"path/filepath"
	"runtime"
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
}
