#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

GOLDEN_CASES_FILE="$REPO_ROOT/scripts/golden-cases.json"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# shellcheck source=scripts/golden-common.sh
. "$REPO_ROOT/scripts/golden-common.sh"

check_case() {
	case_id=$1
	output_path=$2
	header_path=$3
	emit_kinds=$4
	clang_args=$5
	func_filter=$6
	type_filter=$7
	const_filter=$8
	var_filter=$9

	generated_path="$TMP_DIR/${case_id}.generated.go"
	head_path="$TMP_DIR/${case_id}.head.go"

	render_golden_case \
		"$generated_path" \
		"$header_path" \
		"$emit_kinds" \
		"$clang_args" \
		"$func_filter" \
		"$type_filter" \
		"$const_filter" \
		"$var_filter"

	if ! git cat-file -e "HEAD:$output_path" 2>/dev/null; then
		echo "golden file is missing at HEAD: $output_path" >&2
		exit 1
	fi

	git show "HEAD:$output_path" >"$head_path"

	if ! diff -u "$head_path" "$generated_path"; then
		echo "golden drift detected against HEAD: run 'nix develop -c just golden-update' and commit golden changes." >&2
		exit 1
	fi
}

for_each_golden_case check_case "$GOLDEN_CASES_FILE"
