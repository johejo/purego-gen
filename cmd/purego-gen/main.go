package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/johejo/purego-gen/cmd/internal/libclang"
)

var goIdentifierPattern = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(argv []string, stdout io.Writer, stderr io.Writer) int {
	_ = stdout

	options, err := parseOptions(argv)
	if err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return fail(stderr, err)
	}

	if options.out != "-" {
		return fail(stderr, errors.New("generation not implemented in stage1 bootstrap"))
	}

	if err := runBootstrap(options); err != nil {
		return fail(stderr, err)
	}

	_, _ = fmt.Fprintln(stderr, "purego-gen: stage1 bootstrap parse succeeded.")
	return 0
}

func fail(stderr io.Writer, err error) int {
	message := err.Error()
	if !strings.HasPrefix(message, "purego-gen: ") {
		message = "purego-gen: " + message
	}
	_, _ = fmt.Fprintln(stderr, message)
	return 1
}

func runBootstrap(options cliOptions) (err error) {
	for _, header := range options.headers {
		if _, statErr := os.Stat(header); statErr != nil {
			return fmt.Errorf("header not found: %s", header)
		}
	}

	library, err := libclang.Load()
	if err != nil {
		return err
	}
	defer func() {
		closeErr := library.Close()
		if err == nil && closeErr != nil {
			err = closeErr
		}
	}()

	index := library.CreateIndex(0, 0)
	if index == 0 {
		return errors.New("clang_createIndex returned nil index")
	}
	defer library.DisposeIndex(index)

	for _, header := range options.headers {
		resolvedHeader, resolveErr := filepath.Abs(header)
		if resolveErr != nil {
			return fmt.Errorf("failed to resolve header path %s: %w", header, resolveErr)
		}

		translationUnit, parseErr := library.ParseTranslationUnit(
			index,
			resolvedHeader,
			options.clangArgs,
			libclang.DefaultParseOptions,
		)
		if parseErr != nil {
			return parseErr
		}

		diagnosticCount := library.NumDiagnostics(translationUnit)
		library.DisposeTranslationUnit(translationUnit)
		if diagnosticCount != 0 {
			return fmt.Errorf("header %s produced %d diagnostic(s)", resolvedHeader, diagnosticCount)
		}
	}

	return nil
}

type cliOptions struct {
	libID                  string
	headers                []string
	pkg                    string
	out                    string
	emitKinds              []string
	funcFilter             string
	typeFilter             string
	constFilter            string
	varFilter              string
	constCharAsString      bool
	strictEnumTypedefs     bool
	typedSentinelConstants bool
	clangArgs              []string
}

type stringSliceFlag struct {
	values *[]string
}

func (flagValue *stringSliceFlag) String() string {
	if flagValue == nil || flagValue.values == nil {
		return ""
	}
	return strings.Join(*flagValue.values, ",")
}

func (flagValue *stringSliceFlag) Set(value string) error {
	*flagValue.values = append(*flagValue.values, value)
	return nil
}

func parseOptions(argv []string) (cliOptions, error) {
	cliArgs, clangArgs := splitCLIAndClangArgs(argv)

	var options cliOptions
	options.out = "-"
	options.pkg = "bindings"
	options.emitKinds = []string{"func", "type", "const", "var"}

	flagSet := flag.NewFlagSet("purego-gen", flag.ContinueOnError)
	flagSet.SetOutput(io.Discard)
	flagSet.Usage = func() {}

	flagSet.StringVar(&options.libID, "lib-id", "", "Library identifier.")
	flagSet.Var(&stringSliceFlag{values: &options.headers}, "header", "Input C header path.")
	flagSet.StringVar(&options.pkg, "pkg", "bindings", "Generated Go package name.")
	flagSet.StringVar(&options.out, "out", "-", "Output file path.")
	flagSet.Func("emit", "Comma-separated categories to emit.", func(value string) error {
		emitKinds, err := parseEmitKinds(value)
		if err != nil {
			return err
		}
		options.emitKinds = emitKinds
		return nil
	})
	flagSet.StringVar(&options.funcFilter, "func-filter", "", "Regex filter for function declarations.")
	flagSet.StringVar(&options.typeFilter, "type-filter", "", "Regex filter for type declarations.")
	flagSet.StringVar(&options.constFilter, "const-filter", "", "Regex filter for constant declarations.")
	flagSet.StringVar(&options.varFilter, "var-filter", "", "Regex filter for runtime variable declarations.")
	flagSet.BoolVar(
		&options.constCharAsString,
		"const-char-as-string",
		false,
		"Map const char* function signature slots to Go string.",
	)
	flagSet.BoolVar(
		&options.strictEnumTypedefs,
		"strict-enum-typedefs",
		false,
		"Emit enum typedef aliases as strict Go types when possible.",
	)
	flagSet.BoolVar(
		&options.typedSentinelConstants,
		"typed-sentinel-constants",
		false,
		"Emit large sentinel-style constants as typed uint64 constants.",
	)

	if err := flagSet.Parse(cliArgs); err != nil {
		return cliOptions{}, err
	}
	if len(flagSet.Args()) != 0 {
		return cliOptions{}, fmt.Errorf("unexpected positional arguments: %s", strings.Join(flagSet.Args(), " "))
	}

	normalizedLibID, err := normalizeLibID(options.libID)
	if err != nil {
		return cliOptions{}, err
	}
	options.libID = normalizedLibID

	if len(options.headers) == 0 {
		return cliOptions{}, errors.New("--header is required")
	}
	if !isGoIdentifier(options.pkg) {
		return cliOptions{}, errors.New("Go package name must match ^[A-Za-z_][A-Za-z0-9_]*$.")
	}

	options.clangArgs = clangArgs
	return options, nil
}

func splitCLIAndClangArgs(argv []string) ([]string, []string) {
	for index, argument := range argv {
		if argument == "--" {
			return append([]string(nil), argv[:index]...), append([]string(nil), argv[index+1:]...)
		}
	}
	return append([]string(nil), argv...), nil
}

func normalizeLibID(value string) (string, error) {
	normalized := invalidLibIDPattern.ReplaceAllString(strings.ToLower(value), "_")
	normalized = strings.Trim(normalized, "_")
	if normalized == "" {
		return "", errors.New("--lib-id must contain at least one alphanumeric character.")
	}
	if normalized[0] >= '0' && normalized[0] <= '9' {
		normalized = "lib_" + normalized
	}
	return normalized, nil
}

var invalidLibIDPattern = regexp.MustCompile(`[^0-9A-Za-z]+`)

func isGoIdentifier(value string) bool {
	return goIdentifierPattern.MatchString(value)
}

func parseEmitKinds(value string) ([]string, error) {
	parts := strings.Split(value, ",")
	emitKinds := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed == "" {
			continue
		}
		switch trimmed {
		case "func", "type", "const", "var":
			emitKinds = append(emitKinds, trimmed)
		default:
			return nil, fmt.Errorf(
				"Unsupported emit category: %s. Supported values: func,type,const,var.",
				trimmed,
			)
		}
	}
	if len(emitKinds) == 0 {
		return nil, errors.New("--emit must contain at least one category.")
	}
	return emitKinds, nil
}
