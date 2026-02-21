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
	: "$case_id"

	render_golden_case "$output_path" "$header_path" "$emit_kinds" "$clang_args"
}

for_each_golden_case update_case "$GOLDEN_CASES_FILE"
