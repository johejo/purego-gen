//go:generate ../../scripts/uv-run-python-src.sh -m purego_gen gen --config ./config.json --out ./generated.go

package sqlite3sys

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"sync"
	"unsafe"

	"github.com/ebitengine/purego"
)

type (
	DB             = sqlite3
	Stmt           = sqlite3_stmt
	Value          = sqlite3_value
	Context        = sqlite3_context
	Int64          = sqlite3_int64
	Uint64         = sqlite3_uint64
	DestructorType = sqlite3_destructor_type
	Backup         = sqlite3_backup
	Blob           = sqlite3_blob
	Mutex          = sqlite3_mutex
)

var (
	loadOnce sync.Once
	loadErr  error
)

// Load resolves libsqlite3 and registers all required symbols once per process.
func Load() error {
	loadOnce.Do(func() {
		handle, err := openLibrary()
		if err != nil {
			loadErr = err
			return
		}
		if err := sqlite3_register_functions(handle); err != nil {
			loadErr = err
			return
		}
	})
	return loadErr
}

func openLibrary() (uintptr, error) {
	candidates := libraryCandidates()
	var errs []error
	for _, candidate := range candidates {
		handle, err := purego.Dlopen(candidate, purego.RTLD_NOW|purego.RTLD_LOCAL)
		if err == nil {
			return handle, nil
		}
		errs = append(errs, fmt.Errorf("%s: %w", candidate, err))
	}
	return 0, fmt.Errorf("open libsqlite3: %v", errs)
}

func libraryCandidates() []string {
	var candidates []string

	if envPath := os.Getenv("PUREGO_GEN_TEST_LIBSQLITE3_PATH"); envPath != "" {
		candidates = append(candidates, envPath)
	}
	if envDir := os.Getenv("PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR"); envDir != "" {
		candidates = append(candidates, sharedLibraryCandidates(envDir, "sqlite3")...)
	}

	switch runtime.GOOS {
	case "darwin":
		candidates = append(candidates, "libsqlite3.dylib")
	default:
		candidates = append(candidates, "libsqlite3.so", "libsqlite3.so.0")
	}

	return dedupeStrings(candidates)
}

func sharedLibraryCandidates(libDir string, libraryName string) []string {
	stem := libraryName
	if len(stem) < 3 || stem[:3] != "lib" {
		stem = "lib" + stem
	}

	if runtime.GOOS == "darwin" {
		return []string{filepath.Join(libDir, stem+".dylib")}
	}

	candidates := []string{filepath.Join(libDir, stem+".so")}
	matches, err := filepath.Glob(filepath.Join(libDir, stem+".so.*"))
	if err == nil {
		sort.Strings(matches)
		candidates = append(candidates, matches...)
	}
	return candidates
}

func dedupeStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	out := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}

// --- Helpers ---

// cStringPtr returns a uintptr to a null-terminated copy of s.
// Callers must use runtime.KeepAlive(returned-slice) after the C call.
func cStringPtr(s string) (uintptr, []byte) {
	buf := append([]byte(s), 0)
	return uintptr(unsafe.Pointer(&buf[0])), buf
}

func copyBytes(ptr uintptr, length int32) []byte {
	return copyBytesN(ptr, int(length))
}

func copyBytesN(ptr uintptr, length int) []byte {
	if ptr == 0 || length <= 0 {
		return nil
	}
	src := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), ptr)), length)
	dst := make([]byte, length)
	copy(dst, src)
	return dst
}

// goStringMaxLen is the maximum number of bytes goString will scan.
const goStringMaxLen = 1 << 30

func goString(ptr uintptr) string {
	if ptr == 0 {
		return ""
	}
	p := unsafe.Add(unsafe.Pointer(nil), ptr)
	n := 0
	for n < goStringMaxLen && *(*byte)(unsafe.Add(p, n)) != 0 {
		n++
	}
	return string(unsafe.Slice((*byte)(p), n))
}
