package fixture

import (
	"os"
	"testing"

	"github.com/ebitengine/purego"
)

func TestGeneratedBindingsExchangeConstCharStrings(t *testing.T) {
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

	if got := purego_func_smoke_const_greeting(); got != "hello-from-c" {
		t.Fatalf("smoke_const_greeting() = %q, want %q", got, "hello-from-c")
	}
	if got := purego_func_smoke_const_is_expected("ping-from-go"); got != 1 {
		t.Fatalf("smoke_const_is_expected(match) = %d, want 1", got)
	}
	if got := purego_func_smoke_const_is_expected("mismatch"); got != 0 {
		t.Fatalf("smoke_const_is_expected(mismatch) = %d, want 0", got)
	}
	if got := purego_func_smoke_const_roundtrip("echo-from-go"); got != "echo-from-go" {
		t.Fatalf("smoke_const_roundtrip() = %q, want %q", got, "echo-from-go")
	}
}
