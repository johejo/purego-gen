package libclang

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"unsafe"

	"github.com/ebitengine/purego"
)

type Index = purego_type_CXIndex

type TranslationUnit = purego_type_CXTranslationUnit

const (
	DetailedPreprocessingRecord        = purego_const_CXTranslationUnit_DetailedPreprocessingRecord
	SkipFunctionBodies                 = purego_const_CXTranslationUnit_SkipFunctionBodies
	DefaultParseOptions         uint32 = DetailedPreprocessingRecord | SkipFunctionBodies
)

type Library struct {
	handle uintptr
}

func Load() (*Library, error) {
	libraryPath, err := resolveLibraryPath()
	if err != nil {
		return nil, err
	}

	handle, err := purego.Dlopen(libraryPath, purego.RTLD_NOW|purego.RTLD_LOCAL)
	if err != nil {
		return nil, fmt.Errorf("failed to open libclang: %w", err)
	}

	if err := purego_clang_register_functions(handle); err != nil {
		if closeErr := purego.Dlclose(handle); closeErr != nil {
			return nil, fmt.Errorf("%w (also failed to close handle: %v)", err, closeErr)
		}
		return nil, err
	}

	return &Library{handle: handle}, nil
}

func (library *Library) Close() error {
	if library == nil || library.handle == 0 {
		return nil
	}

	err := purego.Dlclose(library.handle)
	library.handle = 0
	if err != nil {
		return fmt.Errorf("failed to close libclang: %w", err)
	}
	return nil
}

func (library *Library) CreateIndex(excludeDeclarationsFromPCH int32, displayDiagnostics int32) Index {
	return Index(purego_func_clang_createIndex(excludeDeclarationsFromPCH, displayDiagnostics))
}

func (library *Library) DisposeIndex(index Index) {
	if index == 0 {
		return
	}
	purego_func_clang_disposeIndex(uintptr(index))
}

func (library *Library) ParseTranslationUnit(
	index Index,
	headerPath string,
	commandLineArgs []string,
	options uint32,
) (TranslationUnit, error) {
	arguments := newCStringArray(commandLineArgs)
	translationUnit := TranslationUnit(
		purego_func_clang_parseTranslationUnit(
			uintptr(index),
			headerPath,
			arguments.pointer(),
			int32(len(arguments.ptrs)),
			0,
			0,
			options,
		),
	)
	runtime.KeepAlive(arguments.raw)
	runtime.KeepAlive(arguments.ptrs)

	if translationUnit == 0 {
		return 0, fmt.Errorf("clang_parseTranslationUnit returned nil translation unit for %s", headerPath)
	}
	return translationUnit, nil
}

func (library *Library) DisposeTranslationUnit(translationUnit TranslationUnit) {
	if translationUnit == 0 {
		return
	}
	purego_func_clang_disposeTranslationUnit(uintptr(translationUnit))
}

func (library *Library) NumDiagnostics(translationUnit TranslationUnit) uint32 {
	if translationUnit == 0 {
		return 0
	}
	return purego_func_clang_getNumDiagnostics(uintptr(translationUnit))
}

type cStringArray struct {
	raw  [][]byte
	ptrs []*byte
}

func newCStringArray(values []string) cStringArray {
	raw := make([][]byte, len(values))
	ptrs := make([]*byte, len(values))
	for index, value := range values {
		raw[index] = append([]byte(value), 0)
		ptrs[index] = &raw[index][0]
	}
	return cStringArray{
		raw:  raw,
		ptrs: ptrs,
	}
}

func (values cStringArray) pointer() uintptr {
	if len(values.ptrs) == 0 {
		return 0
	}
	return uintptr(unsafe.Pointer(&values.ptrs[0]))
}

func resolveLibraryPath() (string, error) {
	libraryPath := os.Getenv("LIBCLANG_PATH")
	if libraryPath == "" {
		return defaultLibraryName(), nil
	}

	info, err := os.Stat(libraryPath)
	if err != nil {
		return "", fmt.Errorf("failed to stat LIBCLANG_PATH %q: %w", libraryPath, err)
	}

	if !info.IsDir() {
		return libraryPath, nil
	}

	for _, candidate := range libraryFileCandidates() {
		resolved := filepath.Join(libraryPath, candidate)
		if _, err := os.Stat(resolved); err == nil {
			return resolved, nil
		}
	}

	for _, pattern := range libraryGlobCandidates() {
		matches, err := filepath.Glob(filepath.Join(libraryPath, pattern))
		if err != nil {
			return "", fmt.Errorf("failed to resolve libclang from LIBCLANG_PATH %q: %w", libraryPath, err)
		}
		if len(matches) != 0 {
			return matches[0], nil
		}
	}

	return "", fmt.Errorf("LIBCLANG_PATH %q does not contain a libclang shared library", libraryPath)
}

func defaultLibraryName() string {
	if runtime.GOOS == "darwin" {
		return "libclang.dylib"
	}
	return "libclang.so"
}

func libraryFileCandidates() []string {
	if runtime.GOOS == "darwin" {
		return []string{"libclang.dylib"}
	}
	return []string{"libclang.so"}
}

func libraryGlobCandidates() []string {
	if runtime.GOOS == "darwin" {
		return nil
	}
	return []string{"libclang.so.*"}
}
