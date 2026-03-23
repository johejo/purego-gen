//go:generate ../../scripts/uv-run-python-src.sh -m purego_gen gen --config ./config.json --out ./generated.go

package duckdbsys

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
	Database          = duckdb_database
	Connection        = duckdb_connection
	PreparedStatement = duckdb_prepared_statement
	Config            = duckdb_config
	DataChunk         = duckdb_data_chunk
	Vector            = duckdb_vector
	LogicalType       = duckdb_logical_type
	Result            = duckdb_result
	Timestamp         = duckdb_timestamp
	TimestampS        = duckdb_timestamp_s
	TimestampMS       = duckdb_timestamp_ms
	TimestampNS       = duckdb_timestamp_ns
	Date              = duckdb_date
	Time              = duckdb_time
	DateStruct        = duckdb_date_struct
	TimeStruct        = duckdb_time_struct
	TimestampStruct   = duckdb_timestamp_struct
	Interval          = duckdb_interval
	Hugeint           = duckdb_hugeint
	Uhugeint          = duckdb_uhugeint
	Blob              = duckdb_blob
	DuckDBString      = duckdb_string
	Decimal           = duckdb_decimal
	ListEntry         = duckdb_list_entry
	TimeTZ            = duckdb_time_tz
	TimeTZStruct      = duckdb_time_tz_struct
	QueryProgressType = duckdb_query_progress_type
	Appender          = duckdb_appender
	PendingResult     = duckdb_pending_result
	DuckDBValue       = duckdb_value
	ExtractedStmts    = duckdb_extracted_statements
	ProfilingInfo     = duckdb_profiling_info
	TableDescription  = duckdb_table_description
)

var (
	loadOnce sync.Once
	loadErr  error
)

// Load resolves libduckdb and registers all required symbols once per process.
func Load() error {
	loadOnce.Do(func() {
		handle, err := openLibrary()
		if err != nil {
			loadErr = err
			return
		}
		if err := duckdb_register_functions(handle); err != nil {
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
	return 0, fmt.Errorf("open libduckdb: %v", errs)
}

func libraryCandidates() []string {
	var candidates []string

	if envPath := os.Getenv("PUREGO_GEN_TEST_LIBDUCKDB_PATH"); envPath != "" {
		candidates = append(candidates, envPath)
	}
	if envDir := os.Getenv("PUREGO_GEN_TEST_LIBDUCKDB_LIB_DIR"); envDir != "" {
		candidates = append(candidates, sharedLibraryCandidates(envDir, "duckdb")...)
	}

	switch runtime.GOOS {
	case "darwin":
		candidates = append(candidates, "libduckdb.dylib")
	default:
		candidates = append(candidates, "libduckdb.so", "libduckdb.so.0")
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

// ownedString converts a char* uintptr (freed with duckdb_free) to a Go string.
func ownedString(ptr uintptr) string {
	s := gostring(ptr)
	if ptr != 0 {
		duckdb_free(ptr)
	}
	return s
}

// String helpers for duckdb_string_t in vectors.
// duckdb_string_t is a 16-byte union: if length <= 12, the string is inlined;
// otherwise bytes 4..8 contain a pointer to the string data.
// purego-gen cannot generate this type (union), so we handle it manually.

const duckdbStringInlineLimit = 12

// ReadStringFromVector reads a duckdb_string_t value at the given pointer offset.
func ReadStringFromVector(base uintptr, row uint64) string {
	// #nosec G103 -- required for reading vector data from C memory
	ptr := unsafe.Add(unsafe.Pointer(nil), base+uintptr(row)*16)
	length := *(*uint32)(ptr)
	if length <= duckdbStringInlineLimit {
		data := unsafe.Slice((*byte)(unsafe.Add(ptr, 4)), int(length))
		return string(data)
	}
	strPtr := *(*uintptr)(unsafe.Add(ptr, 8))
	data := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), strPtr)), int(length))
	return string(data)
}

// ReadBlobFromVector reads a duckdb_string_t value as bytes at the given pointer offset.
func ReadBlobFromVector(base uintptr, row uint64) []byte {
	// #nosec G103 -- required for reading vector data from C memory
	ptr := unsafe.Add(unsafe.Pointer(nil), base+uintptr(row)*16)
	length := *(*uint32)(ptr)
	if length <= duckdbStringInlineLimit {
		src := unsafe.Slice((*byte)(unsafe.Add(ptr, 4)), int(length))
		dst := make([]byte, len(src))
		copy(dst, src)
		return dst
	}
	strPtr := *(*uintptr)(unsafe.Add(ptr, 8))
	src := unsafe.Slice((*byte)(unsafe.Add(unsafe.Pointer(nil), strPtr)), int(length))
	dst := make([]byte, len(src))
	copy(dst, src)
	return dst
}
