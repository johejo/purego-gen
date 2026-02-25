package fixture

import (
	"os"
	"testing"

	"github.com/ebitengine/purego"
)

func TestGeneratedBindingsCallSharedLibrary(t *testing.T) {
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

	if err := purego_fixture_lib_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}

	if got := purego_func_smoke_reset(); got != 0 {
		t.Fatalf("smoke_reset() = %d, want 0", got)
	}
	if got := purego_func_smoke_increment(); got != 1 {
		t.Fatalf("smoke_increment() #1 = %d, want 1", got)
	}
	if got := purego_func_smoke_increment(); got != 2 {
		t.Fatalf("smoke_increment() #2 = %d, want 2", got)
	}
	if got := purego_func_smoke_get_counter(); got != 2 {
		t.Fatalf("smoke_get_counter() = %d, want 2", got)
	}
}
