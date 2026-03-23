package libload

import (
	"os"
	"path/filepath"
	"runtime"
	"sort"
)

// ResolveFromDir finds the first existing shared library file in libDir.
// Returns the path and true if found, or "" and false otherwise.
// Intended for test helpers that need file-existence checks.
func ResolveFromDir(libDir, libraryName string) (string, bool) {
	stem := libStem(libraryName)

	if runtime.GOOS == "darwin" {
		exactPath := filepath.Join(libDir, stem+".dylib")
		if isRegularFile(exactPath) {
			return exactPath, true
		}
		return "", false
	}

	exactPath := filepath.Join(libDir, stem+".so")
	if isRegularFile(exactPath) {
		return exactPath, true
	}

	matches, err := filepath.Glob(filepath.Join(libDir, stem+".so.*"))
	if err != nil || len(matches) == 0 {
		return "", false
	}
	sort.Strings(matches)
	for _, match := range matches {
		if isRegularFile(match) {
			return match, true
		}
	}
	return "", false
}

func isRegularFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}
