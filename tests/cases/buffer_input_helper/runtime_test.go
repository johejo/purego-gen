package fixture

import (
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
	"github.com/johejo/purego-gen/tests/testruntime"
)

func bytesPtr(data []byte) uintptr {
	if len(data) == 0 {
		return 0
	}
	return uintptr(unsafe.Pointer(&data[0]))
}

func TestGeneratedBufferInputHelperWrapsConstVoidPointerInputs(t *testing.T) {
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

	if err := purego_fixture_lib_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}

	payload := []byte{1, 2, 3}
	if got := purego_func_fixture_sum_bytes_bytes(payload, 7); got != 13 {
		t.Fatalf("purego_func_fixture_sum_bytes_bytes(payload, 7) = %d, want %d", got, 13)
	}
	if got := purego_func_fixture_sum_bytes(bytesPtr(payload), uint64(len(payload)), 7); got != 13 {
		t.Fatalf("purego_func_fixture_sum_bytes(low-level) = %d, want %d", got, 13)
	}
	if got := purego_func_fixture_sum_bytes_bytes(nil, 11); got != 11 {
		t.Fatalf("purego_func_fixture_sum_bytes_bytes(nil, 11) = %d, want %d", got, 11)
	}
}
