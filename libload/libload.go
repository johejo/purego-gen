// Package libload provides platform-aware shared library discovery and loading.
package libload

import (
	"fmt"
	"path/filepath"
	"runtime"
	"sort"

	"github.com/ebitengine/purego"
)

// Candidates returns platform-aware shared library candidate paths.
// extraPaths are prepended (e.g. from env var overrides).
// libDirs are directories to scan for versioned .so/.dylib files.
func Candidates(libraryName string, extraPaths []string, libDirs []string) []string {
	var candidates []string
	candidates = append(candidates, extraPaths...)
	for _, dir := range libDirs {
		candidates = append(candidates, DirCandidates(dir, libraryName)...)
	}

	stem := libStem(libraryName)
	switch runtime.GOOS {
	case "darwin":
		candidates = append(candidates, stem+".dylib")
	default:
		candidates = append(candidates, stem+".so", stem+".so.0")
	}

	return dedupe(candidates)
}

// Open tries each candidate with purego.Dlopen(RTLD_NOW|RTLD_LOCAL).
// Returns the first successful handle. label is used in the error message.
func Open(label string, candidates []string) (uintptr, error) {
	if len(candidates) == 0 {
		return 0, fmt.Errorf("open %s: no candidates provided", label)
	}
	var errs []error
	for _, candidate := range candidates {
		handle, err := purego.Dlopen(candidate, purego.RTLD_NOW|purego.RTLD_LOCAL)
		if err == nil {
			return handle, nil
		}
		errs = append(errs, fmt.Errorf("%s: %w", candidate, err))
	}
	return 0, fmt.Errorf("open %s: %v", label, errs)
}

// DirCandidates returns platform-aware candidate paths for a library
// within a specific directory.
func DirCandidates(libDir, libraryName string) []string {
	stem := libStem(libraryName)

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

func libStem(libraryName string) string {
	if len(libraryName) >= 3 && libraryName[:3] == "lib" {
		return libraryName
	}
	return "lib" + libraryName
}

func dedupe(values []string) []string {
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
