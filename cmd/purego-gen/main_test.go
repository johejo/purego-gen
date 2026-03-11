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

	headerPath := mustRepoPath(t, "tests", "cases", "libclang", "parse_input.h")
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}

	exitCode := run(
		[]string{
			"--lib-id",
			"clang",
			"--header",
			headerPath,
			"--",
			"-DPUREGO_GEN_STAGE1_PARSE=1",
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
	if !strings.Contains(stderr.String(), "stage1 bootstrap parse succeeded") {
		t.Fatalf("stderr = %q, want success message", stderr.String())
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

func TestRunRejectsOutFileDuringBootstrap(t *testing.T) {
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}

	exitCode := run(
		[]string{
			"--lib-id",
			"clang",
			"--header",
			"fixture.h",
			"--out",
			"generated.go",
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
	if !strings.Contains(stderr.String(), "generation not implemented in stage1 bootstrap") {
		t.Fatalf("stderr = %q, want bootstrap out error", stderr.String())
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
