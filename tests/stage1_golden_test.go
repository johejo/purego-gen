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
	configPath      string
	generatedPath   string
	runtimeTestPath string
	config          stage1CaseConfig
}

type stage1CaseConfig struct {
	Generator stage1GeneratorConfig `json:"generator"`
	Golden    *stage1GoldenConfig   `json:"golden"`
}

type stage1GeneratorConfig struct {
	LibID       string                `json:"lib_id"`
	PackageName string                `json:"package"`
	Emit        string                `json:"emit"`
	Headers     stage1CaseHeaders     `json:"headers"`
	Filters     stage1CaseFilters     `json:"filters"`
	TypeMapping stage1CaseTypeMapping `json:"type_mapping"`
	ClangArgs   []string              `json:"clang_args"`
}

type stage1GoldenConfig struct {
	Runtime json.RawMessage `json:"runtime"`
}

type stage1CaseHeaders struct {
	Kind    string   `json:"kind"`
	Headers []string `json:"headers"`
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
		configPath := filepath.Join(caseDir, "config.json")
		profileData, err := os.ReadFile(configPath)
		if err != nil {
			t.Fatalf("ReadFile(%q) error = %v", configPath, err)
		}

		var config stage1CaseConfig
		if err := json.Unmarshal(profileData, &config); err != nil {
			t.Fatalf("Unmarshal(%q) error = %v", configPath, err)
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
			configPath:      configPath,
			generatedPath:   filepath.Join(caseDir, "generated.go"),
			runtimeTestPath: runtimeTestPath,
			config:          config,
		})
	}
	return cases
}

func stage1CaseSkipReason(goldenCase stage1GoldenCase) string {
	if goldenCase.config.Generator.Headers.Kind != "local" {
		return stage1SkipReasonEnvInclude
	}
	if len(goldenCase.config.Generator.Headers.Headers) != 1 {
		return stage1SkipReasonHeaders
	}
	if goldenCase.config.Generator.Filters.Func != "" ||
		goldenCase.config.Generator.Filters.Type != "" ||
		goldenCase.config.Generator.Filters.Const != "" ||
		goldenCase.config.Generator.Filters.Var != "" {
		return stage1SkipReasonFilters
	}
	if len(goldenCase.config.Generator.ClangArgs) != 0 {
		return stage1SkipReasonClangArgs
	}
	if goldenCase.config.Generator.TypeMapping.ConstCharAsString ||
		goldenCase.config.Generator.TypeMapping.StrictEnumTypedefs ||
		goldenCase.config.Generator.TypeMapping.TypedSentinelConstants {
		return stage1SkipReasonTypeMapping
	}
	if goldenCase.runtimeTestPath != "" || hasRuntimeConfig(goldenCase.config.Golden) {
		return stage1SkipReasonRuntime
	}
	if goldenCase.config.Generator.Emit != "type" {
		return stage1SkipReasonEmit
	}
	return ""
}

func hasRuntimeConfig(golden *stage1GoldenConfig) bool {
	if golden == nil {
		return false
	}
	return len(bytes.TrimSpace(golden.Runtime)) != 0 && string(bytes.TrimSpace(golden.Runtime)) != "null"
}

func runStage1CLI(t *testing.T, goldenCase stage1GoldenCase) (string, string) {
	t.Helper()

	headerPath := filepath.Join(goldenCase.caseDir, goldenCase.config.Generator.Headers.Headers[0])
	command := exec.Command(
		"go",
		"run",
		"./cmd/purego-gen",
		"--lib-id",
		goldenCase.config.Generator.LibID,
		"--header",
		headerPath,
		"--pkg",
		goldenCase.config.Generator.PackageName,
		"--emit",
		goldenCase.config.Generator.Emit,
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
