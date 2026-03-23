package testruntime

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/johejo/purego-gen/libload"
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

	resolvedPath, ok := libload.ResolveFromDir(resolvedDir, libraryName)
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
