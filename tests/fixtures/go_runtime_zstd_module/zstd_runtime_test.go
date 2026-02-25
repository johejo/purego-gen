package zstdfixture

import (
	"bytes"
	"os"
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
)

func bytesPtr(data []byte) uintptr {
	if len(data) == 0 {
		return 0
	}
	return uintptr(unsafe.Pointer(&data[0]))
}

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

	input := []byte("purego-gen zstd runtime roundtrip")
	compressBound := purego_func_zstd_compressbound(uint64(len(input)))
	if purego_func_zstd_iserror(compressBound) != 0 {
		t.Fatalf("ZSTD_compressBound returned error code: %d", compressBound)
	}

	compressed := make([]byte, int(compressBound))
	compressedSize := purego_func_zstd_compress(
		bytesPtr(compressed),
		uint64(len(compressed)),
		bytesPtr(input),
		uint64(len(input)),
		1,
	)
	if purego_func_zstd_iserror(compressedSize) != 0 {
		t.Fatalf("ZSTD_compress returned error code: %d", compressedSize)
	}
	compressed = compressed[:int(compressedSize)]

	output := make([]byte, len(input))
	outputSize := purego_func_zstd_decompress(
		bytesPtr(output),
		uint64(len(output)),
		bytesPtr(compressed),
		uint64(len(compressed)),
	)
	if purego_func_zstd_iserror(outputSize) != 0 {
		t.Fatalf("ZSTD_decompress returned error code: %d", outputSize)
	}
	if outputSize != uint64(len(input)) {
		t.Fatalf("decompressed size = %d, want %d", outputSize, len(input))
	}
	if !bytes.Equal(output[:int(outputSize)], input) {
		t.Fatal("decompressed payload mismatch")
	}
}
