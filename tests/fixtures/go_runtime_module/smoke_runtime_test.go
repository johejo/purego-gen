package sample

import (
	"os"
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
)

func cInt32At(address uintptr) int32 {
	return *(*int32)(unsafe.Pointer(address))
}

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

	if err := purego_sample_lib_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if err := purego_sample_lib_load_runtime_vars(handle); err != nil {
		t.Fatalf("load runtime vars: %v", err)
	}
	if purego_var_smoke_counter == 0 {
		t.Fatal("runtime symbol smoke_counter is unresolved")
	}

	purego_func_smoke_reset()
	if got := cInt32At(purego_var_smoke_counter); got != 0 {
		t.Fatalf("counter after reset = %d, want 0", got)
	}
	purego_func_smoke_increment()
	purego_func_smoke_increment()
	if got := cInt32At(purego_var_smoke_counter); got != 2 {
		t.Fatalf("counter after increments = %d, want 2", got)
	}
}
