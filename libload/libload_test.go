package libload

import (
	"runtime"
	"testing"
)

func TestCandidates_basic(t *testing.T) {
	candidates := Candidates("sqlite3", nil, nil)
	if len(candidates) == 0 {
		t.Fatal("expected at least one candidate")
	}
	switch runtime.GOOS {
	case "darwin":
		if candidates[0] != "libsqlite3.dylib" {
			t.Errorf("unexpected first candidate: %s", candidates[0])
		}
	default:
		if candidates[0] != "libsqlite3.so" {
			t.Errorf("unexpected first candidate: %s", candidates[0])
		}
	}
}

func TestCandidates_extraPaths(t *testing.T) {
	candidates := Candidates("foo", []string{"/custom/libfoo.so"}, nil)
	if candidates[0] != "/custom/libfoo.so" {
		t.Errorf("expected extra path first, got: %s", candidates[0])
	}
}

func TestCandidates_dedupe(t *testing.T) {
	candidates := Candidates("sqlite3", []string{"libsqlite3.dylib", "libsqlite3.dylib"}, nil)
	seen := make(map[string]int)
	for _, c := range candidates {
		seen[c]++
		if seen[c] > 1 {
			t.Errorf("duplicate candidate: %s", c)
		}
	}
}

func TestDirCandidates_darwin(t *testing.T) {
	if runtime.GOOS != "darwin" {
		t.Skip("darwin-only test")
	}
	got := DirCandidates("/usr/lib", "sqlite3")
	if len(got) != 1 || got[0] != "/usr/lib/libsqlite3.dylib" {
		t.Errorf("unexpected candidates: %v", got)
	}
}

func TestLibStem(t *testing.T) {
	tests := []struct{ in, want string }{
		{"sqlite3", "libsqlite3"},
		{"libfoo", "libfoo"},
		{"ab", "libab"},
	}
	for _, tt := range tests {
		if got := libStem(tt.in); got != tt.want {
			t.Errorf("libStem(%q) = %q, want %q", tt.in, got, tt.want)
		}
	}
}

func TestDedupe(t *testing.T) {
	got := dedupe([]string{"a", "b", "", "a", "c", ""})
	want := []string{"a", "b", "c"}
	if len(got) != len(want) {
		t.Fatalf("got %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("got[%d] = %q, want %q", i, got[i], want[i])
		}
	}
}
