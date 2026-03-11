package main

import (
	"bytes"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestRunBootstrapSuccess(t *testing.T) {
	if os.Getenv("LIBCLANG_PATH") == "" {
		t.Skip("LIBCLANG_PATH is not set")
	}

	headerPath := mustRepoPath(t, "tests", "cases", "basic_type_strict_opaque", "basic.h")
	expectedPath := mustRepoPath(t, "tests", "cases", "basic_type_strict_opaque", "generated.go")
	outputPath := filepath.Join(t.TempDir(), "generated.go")
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}

	exitCode := run(
		[]string{
			"--lib-id",
			"fixture_lib",
			"--header",
			headerPath,
			"--pkg",
			"fixture",
			"--emit",
			"type",
			"--out",
			outputPath,
		},
		stdout,
		stderr,
	)

	if exitCode != 0 {
		t.Fatalf("run() exit code = %d, stderr = %q", exitCode, stderr.String())
	}
	if stdout.String() != "" {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
	if stderr.String() != "" {
		t.Fatalf("stderr = %q, want empty", stderr.String())
	}

	got, err := os.ReadFile(outputPath)
	if err != nil {
		t.Fatalf("ReadFile(outputPath) error = %v", err)
	}
	want, err := os.ReadFile(expectedPath)
	if err != nil {
		t.Fatalf("ReadFile(expectedPath) error = %v", err)
	}
	if string(got) != string(want) {
		t.Fatalf("generated output mismatch\n got:\n%s\nwant:\n%s", got, want)
	}
}

func TestRunBootstrapFailsOnDiagnostics(t *testing.T) {
	if os.Getenv("LIBCLANG_PATH") == "" {
		t.Skip("LIBCLANG_PATH is not set")
	}

	headerPath := mustRepoPath(t, "tests", "cases", "libclang", "parse_input.h")
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}

	exitCode := run(
		[]string{
			"--lib-id",
			"clang",
			"--header",
			headerPath,
		},
		stdout,
		stderr,
	)

	if exitCode != 1 {
		t.Fatalf("run() exit code = %d, want 1", exitCode)
	}
	if stdout.String() != "" {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
	if !strings.Contains(stderr.String(), "produced 1 diagnostic(s)") {
		t.Fatalf("stderr = %q, want diagnostic failure", stderr.String())
	}
}

func TestRunRejectsUnsupportedEmitSubset(t *testing.T) {
	if os.Getenv("LIBCLANG_PATH") == "" {
		t.Skip("LIBCLANG_PATH is not set")
	}

	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}
	headerPath := mustRepoPath(t, "tests", "cases", "basic_func_type", "basic.h")

	exitCode := run(
		[]string{
			"--lib-id",
			"fixture_lib",
			"--header",
			headerPath,
			"--pkg",
			"fixture",
			"--emit",
			"func,type",
		},
		stdout,
		stderr,
	)

	if exitCode != 1 {
		t.Fatalf("run() exit code = %d, want 1", exitCode)
	}
	if stdout.String() != "" {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
	if !strings.Contains(stderr.String(), "stage1 unsupported: --emit must be exactly `type`") {
		t.Fatalf("stderr = %q, want unsupported emit error", stderr.String())
	}
}

func mustRepoPath(t *testing.T, elements ...string) string {
	t.Helper()

	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}

	allElements := append([]string{filepath.Dir(currentFile), "..", ".."}, elements...)
	return filepath.Clean(filepath.Join(allElements...))
}
