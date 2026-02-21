#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

GOLDEN_CASES_FILE="$REPO_ROOT/scripts/golden-cases.json"

# shellcheck source=scripts/golden-common.sh
. "$REPO_ROOT/scripts/golden-common.sh"

update_case() {
	case_id=$1
	output_path=$2
	header_path=$3
	emit_kinds=$4
	clang_args=$5
	func_filter=$6
	type_filter=$7
	const_filter=$8
	var_filter=$9
	: "$case_id"

	render_golden_case \
		"$output_path" \
		"$header_path" \
		"$emit_kinds" \
		"$clang_args" \
		"$func_filter" \
		"$type_filter" \
		"$const_filter" \
		"$var_filter"
}

for_each_golden_case update_case "$GOLDEN_CASES_FILE"
