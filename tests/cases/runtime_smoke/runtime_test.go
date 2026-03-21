package fixture

import (
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
	"github.com/johejo/purego-gen/tests/testruntime"
)

func int32At(address uintptr) int32 {
	pointer := *(*unsafe.Pointer)(unsafe.Pointer(&address))
	return *(*int32)(pointer)
}

func TestGeneratedBindingsCallSharedLibrary(t *testing.T) {
	libraryPath := testruntime.ResolveLibraryPathFromEnv(t, "PUREGO_GEN_TEST_LIB")

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		t.Fatalf("open library: %v", err)
	}
	defer func() {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			t.Fatalf("close library: %v", closeErr)
		}
	}()

	if err := fixture_lib_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if err := fixture_lib_load_runtime_vars(handle); err != nil {
		t.Fatalf("load runtime vars: %v", err)
	}

	if got := smoke_reset(); got != 0 {
		t.Fatalf("smoke_reset() = %d, want 0", got)
	}
	if got := smoke_increment(); got != 1 {
		t.Fatalf("smoke_increment() #1 = %d, want 1", got)
	}
	if got := smoke_increment(); got != 2 {
		t.Fatalf("smoke_increment() #2 = %d, want 2", got)
	}
	if got := smoke_get_counter(); got != 2 {
		t.Fatalf("smoke_get_counter() = %d, want 2", got)
	}

	if smoke_magic == 0 {
		t.Fatal("smoke_magic symbol address is zero")
	}
	if smoke_epoch == 0 {
		t.Fatal("smoke_epoch symbol address is zero")
	}
	if got := int32At(smoke_magic); got != 17 {
		t.Fatalf("smoke_magic = %d, want 17", got)
	}
	if got := int32At(smoke_epoch); got != 2026 {
		t.Fatalf("smoke_epoch = %d, want 2026", got)
	}
}
