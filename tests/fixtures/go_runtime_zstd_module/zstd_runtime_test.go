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
	if purego_func_ZSTD_versionNumber() == 0 {
		t.Fatal("ZSTD_versionNumber returned 0")
	}
	maxCLevel := purego_func_ZSTD_maxCLevel()
	if maxCLevel <= 0 {
		t.Fatalf("ZSTD_maxCLevel returned invalid level: %d", maxCLevel)
	}

	input := []byte("purego-gen zstd runtime roundtrip")
	compressBound := purego_func_ZSTD_compressBound(uint64(len(input)))
	if purego_func_ZSTD_isError(compressBound) != 0 {
		t.Fatalf("ZSTD_compressBound returned error code: %d", compressBound)
	}

	compressed := make([]byte, int(compressBound))
	compressedSize := purego_func_ZSTD_compress(
		bytesPtr(compressed),
		uint64(len(compressed)),
		bytesPtr(input),
		uint64(len(input)),
		1,
	)
	if purego_func_ZSTD_isError(compressedSize) != 0 {
		t.Fatalf("ZSTD_compress returned error code: %d", compressedSize)
	}
	compressed = compressed[:int(compressedSize)]

	output := make([]byte, len(input))
	outputSize := purego_func_ZSTD_decompress(
		bytesPtr(output),
		uint64(len(output)),
		bytesPtr(compressed),
		uint64(len(compressed)),
	)
	if purego_func_ZSTD_isError(outputSize) != 0 {
		t.Fatalf("ZSTD_decompress returned error code: %d", outputSize)
	}
	if outputSize != uint64(len(input)) {
		t.Fatalf("decompressed size = %d, want %d", outputSize, len(input))
	}
	if !bytes.Equal(output[:int(outputSize)], input) {
		t.Fatal("decompressed payload mismatch")
	}

	cctx := purego_func_ZSTD_createCCtx()
	if cctx == 0 {
		t.Fatal("ZSTD_createCCtx returned nil context")
	}
	defer func() {
		freeResult := purego_func_ZSTD_freeCCtx(cctx)
		if purego_func_ZSTD_isError(freeResult) != 0 {
			t.Fatalf("ZSTD_freeCCtx returned error code: %d", freeResult)
		}
	}()

	dctx := purego_func_ZSTD_createDCtx()
	if dctx == 0 {
		t.Fatal("ZSTD_createDCtx returned nil context")
	}
	defer func() {
		freeResult := purego_func_ZSTD_freeDCtx(dctx)
		if purego_func_ZSTD_isError(freeResult) != 0 {
			t.Fatalf("ZSTD_freeDCtx returned error code: %d", freeResult)
		}
	}()

	compressedCCtx := make([]byte, int(compressBound))
	compressedCCtxSize := purego_func_ZSTD_compressCCtx(
		cctx,
		bytesPtr(compressedCCtx),
		uint64(len(compressedCCtx)),
		bytesPtr(input),
		uint64(len(input)),
		maxCLevel,
	)
	if purego_func_ZSTD_isError(compressedCCtxSize) != 0 {
		errorNamePtr := purego_func_ZSTD_getErrorName(compressedCCtxSize)
		t.Fatalf("ZSTD_compressCCtx returned error code: %d (name ptr=%#x)", compressedCCtxSize, errorNamePtr)
	}
	compressedCCtx = compressedCCtx[:int(compressedCCtxSize)]

	frameContentSize := purego_func_ZSTD_getFrameContentSize(
		bytesPtr(compressedCCtx),
		uint64(len(compressedCCtx)),
	)
	if purego_func_ZSTD_isError(frameContentSize) != 0 {
		t.Fatalf("ZSTD_getFrameContentSize returned error code: %d", frameContentSize)
	}
	if frameContentSize != uint64(len(input)) {
		t.Fatalf("frame content size = %d, want %d", frameContentSize, len(input))
	}

	outputCCtx := make([]byte, len(input))
	outputCCtxSize := purego_func_ZSTD_decompressDCtx(
		dctx,
		bytesPtr(outputCCtx),
		uint64(len(outputCCtx)),
		bytesPtr(compressedCCtx),
		uint64(len(compressedCCtx)),
	)
	if purego_func_ZSTD_isError(outputCCtxSize) != 0 {
		t.Fatalf("ZSTD_decompressDCtx returned error code: %d", outputCCtxSize)
	}
	if outputCCtxSize != uint64(len(input)) {
		t.Fatalf("decompressDCtx size = %d, want %d", outputCCtxSize, len(input))
	}
	if !bytes.Equal(outputCCtx[:int(outputCCtxSize)], input) {
		t.Fatal("decompressDCtx payload mismatch")
	}

	undersizedDst := make([]byte, len(input)-1)
	errorCode := purego_func_ZSTD_decompressDCtx(
		dctx,
		bytesPtr(undersizedDst),
		uint64(len(undersizedDst)),
		bytesPtr(compressedCCtx),
		uint64(len(compressedCCtx)),
	)
	if purego_func_ZSTD_isError(errorCode) == 0 {
		t.Fatal("ZSTD_decompressDCtx should fail with undersized destination")
	}
	errorNamePtr := purego_func_ZSTD_getErrorName(errorCode)
	if errorNamePtr == 0 {
		t.Fatal("ZSTD_getErrorName returned NULL for an error code")
	}
}
