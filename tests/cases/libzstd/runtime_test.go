//go:build purego_gen_case_runtime
// +build purego_gen_case_runtime

package fixture

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
	t.Cleanup(func() {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			t.Errorf("close library: %v", closeErr)
		}
	})

	if err := purego_zstd_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if purego_func_ZSTD_versionNumber() == 0 {
		t.Fatal("ZSTD_versionNumber returned 0")
	}
	minCLevel := purego_func_ZSTD_minCLevel()
	maxCLevel := purego_func_ZSTD_maxCLevel()
	if maxCLevel <= 0 {
		t.Fatalf("ZSTD_maxCLevel returned invalid level: %d", maxCLevel)
	}
	if minCLevel > 0 {
		t.Fatalf("ZSTD_minCLevel returned invalid level: %d", minCLevel)
	}
	if minCLevel > maxCLevel {
		t.Fatalf("compression level range is invalid: min=%d max=%d", minCLevel, maxCLevel)
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
	if purego_func_ZSTD_getErrorCode(compressedSize) != 0 {
		t.Fatalf("ZSTD_getErrorCode should return no_error for success result: %d", compressedSize)
	}
	compressed = compressed[:int(compressedSize)]
	frameCompressedSize := purego_func_ZSTD_findFrameCompressedSize(
		bytesPtr(compressed),
		uint64(len(compressed)),
	)
	if purego_func_ZSTD_isError(frameCompressedSize) != 0 {
		t.Fatalf("ZSTD_findFrameCompressedSize returned error code: %d", frameCompressedSize)
	}
	if frameCompressedSize != uint64(len(compressed)) {
		t.Fatalf("frame compressed size = %d, want %d", frameCompressedSize, len(compressed))
	}

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
	t.Cleanup(func() {
		freeResult := purego_func_ZSTD_freeCCtx(cctx)
		if purego_func_ZSTD_isError(freeResult) != 0 {
			t.Errorf("ZSTD_freeCCtx returned error code: %d", freeResult)
		}
	})

	dctx := purego_func_ZSTD_createDCtx()
	if dctx == 0 {
		t.Fatal("ZSTD_createDCtx returned nil context")
	}
	t.Cleanup(func() {
		freeResult := purego_func_ZSTD_freeDCtx(dctx)
		if purego_func_ZSTD_isError(freeResult) != 0 {
			t.Errorf("ZSTD_freeDCtx returned error code: %d", freeResult)
		}
	})

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
		errorName := purego_func_ZSTD_getErrorName(compressedCCtxSize)
		t.Fatalf("ZSTD_compressCCtx returned error code: %d (name=%q)", compressedCCtxSize, errorName)
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

	dict := []byte("purego-gen-zstd-dict-2026")
	inputWithDict := bytes.Repeat(dict, 16)
	compressBoundWithDict := purego_func_ZSTD_compressBound(uint64(len(inputWithDict)))
	if purego_func_ZSTD_isError(compressBoundWithDict) != 0 {
		t.Fatalf("ZSTD_compressBound (dict) returned error code: %d", compressBoundWithDict)
	}
	compressedWithDict := make([]byte, int(compressBoundWithDict))
	compressedWithDictSize := purego_func_ZSTD_compress_usingDict(
		cctx,
		bytesPtr(compressedWithDict),
		uint64(len(compressedWithDict)),
		bytesPtr(inputWithDict),
		uint64(len(inputWithDict)),
		bytesPtr(dict),
		uint64(len(dict)),
		maxCLevel,
	)
	if purego_func_ZSTD_isError(compressedWithDictSize) != 0 {
		t.Fatalf("ZSTD_compress_usingDict returned error code: %d", compressedWithDictSize)
	}
	compressedWithDict = compressedWithDict[:int(compressedWithDictSize)]

	outputWithDict := make([]byte, len(inputWithDict))
	outputWithDictSize := purego_func_ZSTD_decompress_usingDict(
		dctx,
		bytesPtr(outputWithDict),
		uint64(len(outputWithDict)),
		bytesPtr(compressedWithDict),
		uint64(len(compressedWithDict)),
		bytesPtr(dict),
		uint64(len(dict)),
	)
	if purego_func_ZSTD_isError(outputWithDictSize) != 0 {
		t.Fatalf("ZSTD_decompress_usingDict returned error code: %d", outputWithDictSize)
	}
	if outputWithDictSize != uint64(len(inputWithDict)) {
		t.Fatalf("decompress_usingDict size = %d, want %d", outputWithDictSize, len(inputWithDict))
	}
	if !bytes.Equal(outputWithDict[:int(outputWithDictSize)], inputWithDict) {
		t.Fatal("decompress_usingDict payload mismatch")
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
	if purego_func_ZSTD_getErrorCode(errorCode) == 0 {
		t.Fatal("ZSTD_getErrorCode should return non-zero for an error result")
	}
	errorName := purego_func_ZSTD_getErrorName(errorCode)
	if errorName == "" {
		t.Fatal("ZSTD_getErrorName returned empty string for an error code")
	}
}
