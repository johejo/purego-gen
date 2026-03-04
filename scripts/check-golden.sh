#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

GOLDEN_CASES_FILE="$REPO_ROOT/scripts/golden-cases.json"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
STRICT_HEAD_ONLY="${GOLDEN_CHECK_STRICT_HEAD:-0}"

# shellcheck source=scripts/golden-common.sh
. "$REPO_ROOT/scripts/golden-common.sh"

if [ "$STRICT_HEAD_ONLY" != "0" ] && [ "$STRICT_HEAD_ONLY" != "1" ]; then
	echo "GOLDEN_CHECK_STRICT_HEAD must be '0' or '1'." >&2
	exit 1
fi

check_case() {
	case_id=$1
	output_path=$2
	header_paths=$3
	emit_kinds=$4
	clang_args=$5
	func_filter=$6
	type_filter=$7
	const_filter=$8
	var_filter=$9
	strict_enum_typedefs=${10}
	typed_sentinel_constants=${11}

	generated_path="$TMP_DIR/${case_id}.generated.go"
	expected_path="$TMP_DIR/${case_id}.expected.go"
	expected_source=""

	render_golden_case \
		"$generated_path" \
		"$header_paths" \
		"$emit_kinds" \
		"$clang_args" \
		"$func_filter" \
		"$type_filter" \
		"$const_filter" \
		"$var_filter" \
		"$strict_enum_typedefs" \
		"$typed_sentinel_constants"

	if git cat-file -e "HEAD:$output_path" 2>/dev/null; then
		git show "HEAD:$output_path" >"$expected_path"
		expected_source="HEAD"
	elif [ "$STRICT_HEAD_ONLY" = "1" ]; then
		echo "golden file is missing at HEAD (strict mode): $output_path" >&2
		exit 1
	elif [ -f "$output_path" ]; then
		cp "$output_path" "$expected_path"
		expected_source="working-tree"
	else
		echo "golden file is missing: $output_path" >&2
		exit 1
	fi

	if ! diff -u "$expected_path" "$generated_path"; then
		if [ "$expected_source" = "HEAD" ]; then
			echo "golden drift detected against HEAD: run 'nix develop -c just golden-update' and commit golden changes." >&2
		else
			echo "golden drift detected for new file in working tree: run 'nix develop -c just golden-update' and commit golden changes." >&2
		fi
		exit 1
	fi
}

for_each_golden_case check_case "$GOLDEN_CASES_FILE"
