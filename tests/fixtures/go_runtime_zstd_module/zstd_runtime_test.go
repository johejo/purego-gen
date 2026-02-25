package zstdfixture

import (
	"os"
	"testing"

	"github.com/ebitengine/purego"
)

func TestGeneratedBindingsResolveLibzstdSymbols(t *testing.T) {
	libraryPath := os.Getenv("PUREGO_GEN_TEST_LIB")
	if libraryPath == "" {
		t.Fatal("PUREGO_GEN_TEST_LIB must be set")
	}

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		t.Fatalf("open library: %v", err)
	}
	defer func() {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			t.Fatalf("close library: %v", closeErr)
		}
	}()

	if err := purego_zstd_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
}
