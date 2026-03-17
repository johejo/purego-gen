package testruntime

import (
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"
)

// ResolveLibraryPathFromEnv returns one explicit shared-library path or skips the test.
func ResolveLibraryPathFromEnv(t *testing.T, envName string) string {
	t.Helper()

	libraryPath := os.Getenv(envName)
	if libraryPath == "" {
		t.Skipf("skipping runtime test: %s is not set", envName)
	}

	resolvedPath, err := filepath.Abs(libraryPath)
	if err != nil {
		t.Fatalf("resolve library path from %s: %v", envName, err)
	}
	return resolvedPath
}

// ResolveLibraryPathFromLibDirEnv resolves one shared library from a libdir env or skips the test.
func ResolveLibraryPathFromLibDirEnv(t *testing.T, envName string, libraryName string) string {
	t.Helper()

	libDir := os.Getenv(envName)
	if libDir == "" {
		t.Skipf("skipping runtime test: %s is not set", envName)
	}

	resolvedDir, err := filepath.Abs(libDir)
	if err != nil {
		t.Fatalf("resolve library directory from %s: %v", envName, err)
	}

	info, err := os.Stat(resolvedDir)
	if err != nil || !info.IsDir() {
		t.Skipf("skipping runtime test: %s does not point to a directory: %s", envName, resolvedDir)
	}

	resolvedPath, ok := resolveSharedLibraryPath(resolvedDir, libraryName)
	if !ok {
		t.Skipf(
			"skipping runtime test: shared library %q not found under %s from %s",
			libraryName,
			resolvedDir,
			envName,
		)
	}
	return resolvedPath
}

func resolveSharedLibraryPath(libDir string, libraryName string) (string, bool) {
	stem := libraryName
	if len(stem) < 3 || stem[:3] != "lib" {
		stem = "lib" + stem
	}

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
