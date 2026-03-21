package fixture

import (
	"bytes"
	"testing"
	"unsafe"

	"github.com/ebitengine/purego"
	"github.com/johejo/purego-gen/tests/testruntime"
)

func TestGeneratedBindingsResolveLibzstdSymbols(t *testing.T) {
	libraryPath := testruntime.ResolveLibraryPathFromLibDirEnv(
		t,
		"PUREGO_GEN_TEST_LIBZSTD_LIB_DIR",
		"zstd",
	)

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		t.Fatalf("open library: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			t.Errorf("close library: %v", closeErr)
		}
	})

	if err := zstd_register_functions(handle); err != nil {
		t.Fatalf("register functions: %v", err)
	}
	if ZSTD_versionNumber() == 0 {
		t.Fatal("ZSTD_versionNumber returned 0")
	}
	minCLevel := ZSTD_minCLevel()
	maxCLevel := ZSTD_maxCLevel()
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
	compressBound := ZSTD_compressBound(uint64(len(input)))
	if ZSTD_isError(compressBound) != 0 {
		t.Fatalf("ZSTD_compressBound returned error code: %d", compressBound)
	}

	compressed := make([]byte, int(compressBound))
	compressedSize := ZSTD_compress_bytes(
		uintptr(unsafe.Pointer(&compressed[0])),
		uint64(len(compressed)),
		input,
		1,
	)
	if ZSTD_isError(compressedSize) != 0 {
		t.Fatalf("ZSTD_compress returned error code: %d", compressedSize)
	}
	if ZSTD_getErrorCode(compressedSize) != 0 {
		t.Fatalf("ZSTD_getErrorCode should return no_error for success result: %d", compressedSize)
	}
	compressed = compressed[:int(compressedSize)]
	frameCompressedSize := ZSTD_findFrameCompressedSize_bytes(
		compressed,
	)
	if ZSTD_isError(frameCompressedSize) != 0 {
		t.Fatalf("ZSTD_findFrameCompressedSize returned error code: %d", frameCompressedSize)
	}
	if frameCompressedSize != uint64(len(compressed)) {
		t.Fatalf("frame compressed size = %d, want %d", frameCompressedSize, len(compressed))
	}

	output := make([]byte, len(input))
	outputSize := ZSTD_decompress_bytes(
		uintptr(unsafe.Pointer(&output[0])),
		uint64(len(output)),
		compressed,
	)
	if ZSTD_isError(outputSize) != 0 {
		t.Fatalf("ZSTD_decompress returned error code: %d", outputSize)
	}
	if outputSize != uint64(len(input)) {
		t.Fatalf("decompressed size = %d, want %d", outputSize, len(input))
	}
	if !bytes.Equal(output[:int(outputSize)], input) {
		t.Fatal("decompressed payload mismatch")
	}

	cctx := ZSTD_createCCtx()
	if cctx == nil {
		t.Fatal("ZSTD_createCCtx returned nil context")
	}
	t.Cleanup(func() {
		freeResult := ZSTD_freeCCtx(cctx)
		if ZSTD_isError(freeResult) != 0 {
			t.Errorf("ZSTD_freeCCtx returned error code: %d", freeResult)
		}
	})

	dctx := ZSTD_createDCtx()
	if dctx == nil {
		t.Fatal("ZSTD_createDCtx returned nil context")
	}
	t.Cleanup(func() {
		freeResult := ZSTD_freeDCtx(dctx)
		if ZSTD_isError(freeResult) != 0 {
			t.Errorf("ZSTD_freeDCtx returned error code: %d", freeResult)
		}
	})

	compressedCCtx := make([]byte, int(compressBound))
	compressedCCtxSize := ZSTD_compressCCtx_bytes(
		cctx,
		uintptr(unsafe.Pointer(&compressedCCtx[0])),
		uint64(len(compressedCCtx)),
		input,
		maxCLevel,
	)
	if ZSTD_isError(compressedCCtxSize) != 0 {
		errorName := ZSTD_getErrorName(compressedCCtxSize)
		t.Fatalf("ZSTD_compressCCtx returned error code: %d (name=%q)", compressedCCtxSize, errorName)
	}
	compressedCCtx = compressedCCtx[:int(compressedCCtxSize)]

	frameContentSize := ZSTD_getFrameContentSize_bytes(
		compressedCCtx,
	)
	if ZSTD_isError(frameContentSize) != 0 {
		t.Fatalf("ZSTD_getFrameContentSize returned error code: %d", frameContentSize)
	}
	if frameContentSize != uint64(len(input)) {
		t.Fatalf("frame content size = %d, want %d", frameContentSize, len(input))
	}

	outputCCtx := make([]byte, len(input))
	outputCCtxSize := ZSTD_decompressDCtx_bytes(
		dctx,
		uintptr(unsafe.Pointer(&outputCCtx[0])),
		uint64(len(outputCCtx)),
		compressedCCtx,
	)
	if ZSTD_isError(outputCCtxSize) != 0 {
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
	compressBoundWithDict := ZSTD_compressBound(uint64(len(inputWithDict)))
	if ZSTD_isError(compressBoundWithDict) != 0 {
		t.Fatalf("ZSTD_compressBound (dict) returned error code: %d", compressBoundWithDict)
	}
	compressedWithDict := make([]byte, int(compressBoundWithDict))
	compressedWithDictSize := ZSTD_compress_usingDict_bytes(
		cctx,
		uintptr(unsafe.Pointer(&compressedWithDict[0])),
		uint64(len(compressedWithDict)),
		inputWithDict,
		dict,
		maxCLevel,
	)
	if ZSTD_isError(compressedWithDictSize) != 0 {
		t.Fatalf("ZSTD_compress_usingDict returned error code: %d", compressedWithDictSize)
	}
	compressedWithDict = compressedWithDict[:int(compressedWithDictSize)]

	outputWithDict := make([]byte, len(inputWithDict))
	outputWithDictSize := ZSTD_decompress_usingDict_bytes(
		dctx,
		uintptr(unsafe.Pointer(&outputWithDict[0])),
		uint64(len(outputWithDict)),
		compressedWithDict,
		dict,
	)
	if ZSTD_isError(outputWithDictSize) != 0 {
		t.Fatalf("ZSTD_decompress_usingDict returned error code: %d", outputWithDictSize)
	}
	if outputWithDictSize != uint64(len(inputWithDict)) {
		t.Fatalf("decompress_usingDict size = %d, want %d", outputWithDictSize, len(inputWithDict))
	}
	if !bytes.Equal(outputWithDict[:int(outputWithDictSize)], inputWithDict) {
		t.Fatal("decompress_usingDict payload mismatch")
	}

	undersizedDst := make([]byte, len(input)-1)
	errorCode := ZSTD_decompressDCtx_bytes(
		dctx,
		uintptr(unsafe.Pointer(&undersizedDst[0])),
		uint64(len(undersizedDst)),
		compressedCCtx,
	)
	if ZSTD_isError(errorCode) == 0 {
		t.Fatal("ZSTD_decompressDCtx should fail with undersized destination")
	}
	if ZSTD_getErrorCode(errorCode) == 0 {
		t.Fatal("ZSTD_getErrorCode should return non-zero for an error result")
	}
	errorName := ZSTD_getErrorName(errorCode)
	if errorName == "" {
		t.Fatal("ZSTD_getErrorName returned empty string for an error code")
	}
}
