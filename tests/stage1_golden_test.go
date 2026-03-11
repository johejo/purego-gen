package tests

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
)

const (
	stage1SkipReasonEnvInclude  = "headers.kind=`env_include` is not supported"
	stage1SkipReasonHeaders     = "exactly one local header path is required"
	stage1SkipReasonFilters     = "declaration filters are not supported"
	stage1SkipReasonClangArgs   = "clang_args are not supported"
	stage1SkipReasonTypeMapping = "non-default type_mapping is not supported"
	stage1SkipReasonRuntime     = "runtime cases are not supported"
	stage1SkipReasonEmit        = "emit must be exactly `type`"
)

type stage1GoldenCase struct {
	caseID          string
	caseDir         string
	generatedPath   string
	runtimeTestPath string
	profile         stage1CaseProfile
}

type stage1CaseProfile struct {
	LibID       string                `json:"lib_id"`
	PackageName string                `json:"package"`
	Emit        string                `json:"emit"`
	Headers     stage1CaseHeaders     `json:"headers"`
	Filters     stage1CaseFilters     `json:"filters"`
	TypeMapping stage1CaseTypeMapping `json:"type_mapping"`
	ClangArgs   []string              `json:"clang_args"`
	Runtime     json.RawMessage       `json:"runtime"`
}

type stage1CaseHeaders struct {
	Kind  string   `json:"kind"`
	Paths []string `json:"paths"`
}

type stage1CaseFilters struct {
	Func  string `json:"func"`
	Type  string `json:"type"`
	Const string `json:"const"`
	Var   string `json:"var"`
}

type stage1CaseTypeMapping struct {
	ConstCharAsString      bool `json:"const_char_as_string"`
	StrictEnumTypedefs     bool `json:"strict_enum_typedefs"`
	TypedSentinelConstants bool `json:"typed_sentinel_constants"`
}

func TestStage1GoldenCases(t *testing.T) {
	for _, goldenCase := range discoverStage1GoldenCases(t) {
		goldenCase := goldenCase
		t.Run(goldenCase.caseID, func(t *testing.T) {
			if reason := stage1CaseSkipReason(goldenCase); reason != "" {
				t.Skip(reason)
			}
			if os.Getenv("LIBCLANG_PATH") == "" {
				t.Skip("LIBCLANG_PATH is not set")
			}

			stdout, stderr := runStage1CLI(t, goldenCase)
			if stderr != "" {
				t.Fatalf("stderr = %q, want empty", stderr)
			}

			want, err := os.ReadFile(goldenCase.generatedPath)
			if err != nil {
				t.Fatalf("ReadFile(generated.go) error = %v", err)
			}
			if stdout != string(want) {
				t.Fatalf("generated output mismatch\n got:\n%s\nwant:\n%s", stdout, want)
			}
		})
	}
}

func TestStage1GoldenCaseSkipReasons(t *testing.T) {
	casesByID := make(map[string]stage1GoldenCase)
	for _, goldenCase := range discoverStage1GoldenCases(t) {
		casesByID[goldenCase.caseID] = goldenCase
	}

	testCases := map[string]string{
		"categories_const":          stage1SkipReasonEmit,
		"categories_mixed_filtered": stage1SkipReasonFilters,
		"conditional_with_define":   stage1SkipReasonClangArgs,
		"libclang":                  stage1SkipReasonEnvInclude,
		"runtime_smoke":             stage1SkipReasonRuntime,
		"strict_typing_enabled":     stage1SkipReasonTypeMapping,
	}

	for caseID, wantReason := range testCases {
		goldenCase, ok := casesByID[caseID]
		if !ok {
			t.Fatalf("case %q not found", caseID)
		}

		if got := stage1CaseSkipReason(goldenCase); got != wantReason {
			t.Fatalf("case %q skip reason = %q, want %q", caseID, got, wantReason)
		}
	}
}

func discoverStage1GoldenCases(t *testing.T) []stage1GoldenCase {
	t.Helper()

	casesDir := filepath.Join(repoRoot(t), "tests", "cases")
	entries, err := os.ReadDir(casesDir)
	if err != nil {
		t.Fatalf("ReadDir(%q) error = %v", casesDir, err)
	}

	cases := make([]stage1GoldenCase, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		caseDir := filepath.Join(casesDir, entry.Name())
		profilePath := filepath.Join(caseDir, "profile.json")
		profileData, err := os.ReadFile(profilePath)
		if err != nil {
			t.Fatalf("ReadFile(%q) error = %v", profilePath, err)
		}

		var profile stage1CaseProfile
		if err := json.Unmarshal(profileData, &profile); err != nil {
			t.Fatalf("Unmarshal(%q) error = %v", profilePath, err)
		}

		runtimeTestPath := filepath.Join(caseDir, "runtime_test.go")
		if _, err := os.Stat(runtimeTestPath); err != nil {
			if !os.IsNotExist(err) {
				t.Fatalf("Stat(%q) error = %v", runtimeTestPath, err)
			}
			runtimeTestPath = ""
		}

		cases = append(cases, stage1GoldenCase{
			caseID:          entry.Name(),
			caseDir:         caseDir,
			generatedPath:   filepath.Join(caseDir, "generated.go"),
			runtimeTestPath: runtimeTestPath,
			profile:         profile,
		})
	}
	return cases
}

func stage1CaseSkipReason(goldenCase stage1GoldenCase) string {
	if goldenCase.profile.Headers.Kind != "local" {
		return stage1SkipReasonEnvInclude
	}
	if len(goldenCase.profile.Headers.Paths) != 1 {
		return stage1SkipReasonHeaders
	}
	if goldenCase.profile.Filters.Func != "" ||
		goldenCase.profile.Filters.Type != "" ||
		goldenCase.profile.Filters.Const != "" ||
		goldenCase.profile.Filters.Var != "" {
		return stage1SkipReasonFilters
	}
	if len(goldenCase.profile.ClangArgs) != 0 {
		return stage1SkipReasonClangArgs
	}
	if goldenCase.profile.TypeMapping.ConstCharAsString ||
		goldenCase.profile.TypeMapping.StrictEnumTypedefs ||
		goldenCase.profile.TypeMapping.TypedSentinelConstants {
		return stage1SkipReasonTypeMapping
	}
	if goldenCase.runtimeTestPath != "" || hasRuntimeConfig(goldenCase.profile.Runtime) {
		return stage1SkipReasonRuntime
	}
	if goldenCase.profile.Emit != "type" {
		return stage1SkipReasonEmit
	}
	return ""
}

func hasRuntimeConfig(raw json.RawMessage) bool {
	return len(bytes.TrimSpace(raw)) != 0 && string(bytes.TrimSpace(raw)) != "null"
}

func runStage1CLI(t *testing.T, goldenCase stage1GoldenCase) (string, string) {
	t.Helper()

	headerPath := filepath.Join(goldenCase.caseDir, goldenCase.profile.Headers.Paths[0])
	command := exec.Command(
		"go",
		"run",
		"./cmd/purego-gen",
		"--lib-id",
		goldenCase.profile.LibID,
		"--header",
		headerPath,
		"--pkg",
		goldenCase.profile.PackageName,
		"--emit",
		goldenCase.profile.Emit,
	)
	command.Dir = repoRoot(t)
	command.Env = os.Environ()

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr

	if err := command.Run(); err != nil {
		t.Fatalf("go run %s failed: %v\nstderr:\n%s", goldenCase.caseID, err, stderr.String())
	}

	return stdout.String(), stderr.String()
}

func repoRoot(t *testing.T) string {
	t.Helper()

	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}

	return filepath.Clean(filepath.Join(filepath.Dir(currentFile), ".."))
}
