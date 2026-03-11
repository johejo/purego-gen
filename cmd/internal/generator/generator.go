package generator

import (
	"bufio"
	"bytes"
	"embed"
	"fmt"
	"go/format"
	"os"
	"regexp"
	"strings"
	"text/template"
)

var (
	basicIntTypedefPattern = regexp.MustCompile(`^typedef\s+int\s+([A-Za-z_][A-Za-z0-9_]*)\s*;$`)
	voidPtrTypedefPattern  = regexp.MustCompile(`^typedef\s+void\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)\s*;$`)
	opaqueTypedefPattern   = regexp.MustCompile(
		`^typedef\s+struct\s+([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;$`,
	)
	blockCommentPattern = regexp.MustCompile(`(?s)/\*.*?\*/`)
	lineCommentPattern  = regexp.MustCompile(`//.*$`)
)

//go:embed generated.go.gotmpl
var templateFS embed.FS

var generatedSourceTemplate = template.Must(
	template.ParseFS(templateFS, "generated.go.gotmpl"),
)

type Config struct {
	HeaderPath  string
	PackageName string
}

type typeDecl struct {
	Name    string
	Target  string
	IsAlias bool
}

type sourceTemplateData struct {
	PackageName  string
	Declarations []typeDecl
}

func Generate(config Config) (string, error) {
	source, err := os.ReadFile(config.HeaderPath)
	if err != nil {
		return "", fmt.Errorf("failed to read header %s: %w", config.HeaderPath, err)
	}

	declarations, err := parseSupportedTypedefs(string(source))
	if err != nil {
		return "", err
	}
	if len(declarations) == 0 {
		return "", fmt.Errorf("stage1 unsupported: no supported typedef declarations found in %s", config.HeaderPath)
	}

	rendered, err := renderSource(config.PackageName, declarations)
	if err != nil {
		return "", err
	}
	return rendered, nil
}

func parseSupportedTypedefs(headerSource string) ([]typeDecl, error) {
	withoutBlockComments := blockCommentPattern.ReplaceAllString(headerSource, "")
	scanner := bufio.NewScanner(strings.NewReader(withoutBlockComments))

	declarations := make([]typeDecl, 0)
	for scanner.Scan() {
		line := strings.TrimSpace(lineCommentPattern.ReplaceAllString(scanner.Text(), ""))
		if line == "" {
			continue
		}

		if matches := basicIntTypedefPattern.FindStringSubmatch(line); matches != nil {
			declarations = append(declarations, typeDecl{
				Name:    matches[1],
				Target:  "int32",
				IsAlias: true,
			})
			continue
		}
		if matches := voidPtrTypedefPattern.FindStringSubmatch(line); matches != nil {
			declarations = append(declarations, typeDecl{
				Name:    matches[1],
				Target:  "uintptr",
				IsAlias: true,
			})
			continue
		}
		if matches := opaqueTypedefPattern.FindStringSubmatch(line); matches != nil {
			if matches[1] != matches[2] {
				return nil, fmt.Errorf(
					"stage1 unsupported: opaque typedef requires matching struct and alias names: %s",
					line,
				)
			}
			declarations = append(declarations, typeDecl{
				Name:    matches[2],
				Target:  "uintptr",
				IsAlias: false,
			})
			continue
		}

		if isTypeDeclarationLine(line) {
			return nil, fmt.Errorf("stage1 unsupported: unsupported declaration: %s", line)
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("failed to scan header source: %w", err)
	}

	return declarations, nil
}

func isTypeDeclarationLine(line string) bool {
	return strings.HasPrefix(line, "typedef ") ||
		strings.HasPrefix(line, "struct ") ||
		strings.HasPrefix(line, "enum ") ||
		strings.HasPrefix(line, "union ")
}

func renderSource(packageName string, declarations []typeDecl) (string, error) {
	var buffer bytes.Buffer
	if err := generatedSourceTemplate.Execute(&buffer, sourceTemplateData{
		PackageName:  packageName,
		Declarations: declarations,
	}); err != nil {
		return "", fmt.Errorf("failed to render generated source template: %w", err)
	}

	formatted, err := format.Source(buffer.Bytes())
	if err != nil {
		return "", fmt.Errorf("failed to format generated source: %w", err)
	}
	return string(formatted), nil
}
