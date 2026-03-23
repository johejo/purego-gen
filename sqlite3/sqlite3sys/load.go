//go:generate ../../scripts/uv-run-python-src.sh -m purego_gen gen --config ./config.json --out ./generated.go

package sqlite3sys

import (
	"os"
	"sync"
	"unsafe"

	"github.com/johejo/purego-gen/libload"
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
	return libload.Open("libsqlite3", libraryCandidates())
}

func libraryCandidates() []string {
	var extraPaths []string
	if p := os.Getenv("PUREGO_GEN_TEST_LIBSQLITE3_PATH"); p != "" {
		extraPaths = append(extraPaths, p)
	}
	var libDirs []string
	if d := os.Getenv("PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR"); d != "" {
		libDirs = append(libDirs, d)
	}
	return libload.Candidates("sqlite3", extraPaths, libDirs)
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
