#!/usr/bin/env sh

for_each_golden_case() {
	case_callback=$1
	case_file=$2

	jq -c '.cases[]' "$case_file" | while IFS= read -r case_entry; do
		case_id="$(printf '%s' "$case_entry" | jq -r '.id')"
		output_path="$(printf '%s' "$case_entry" | jq -r '.output_path')"
		header_paths="$(printf '%s' "$case_entry" | jq -r '.header_paths[]')"
		emit_kinds="$(printf '%s' "$case_entry" | jq -r '.emit_kinds')"
		clang_args="$(printf '%s' "$case_entry" | jq -r '.clang_args // ""')"
		func_filter="$(printf '%s' "$case_entry" | jq -r '.func_filter // ""')"
		type_filter="$(printf '%s' "$case_entry" | jq -r '.type_filter // ""')"
		const_filter="$(printf '%s' "$case_entry" | jq -r '.const_filter // ""')"
		var_filter="$(printf '%s' "$case_entry" | jq -r '.var_filter // ""')"
		strict_enum_typedefs="$(printf '%s' "$case_entry" | jq -r '.strict_enum_typedefs // false')"
		typed_sentinel_constants="$(printf '%s' "$case_entry" | jq -r '.typed_sentinel_constants // false')"

		"$case_callback" \
			"$case_id" \
			"$output_path" \
			"$header_paths" \
			"$emit_kinds" \
			"$clang_args" \
			"$func_filter" \
			"$type_filter" \
			"$const_filter" \
			"$var_filter" \
			"$strict_enum_typedefs" \
			"$typed_sentinel_constants"
	done
}

render_golden_case() {
	render_output_path=$1
	render_header_paths=$2
	render_emit_kinds=$3
	render_clang_args=$4
	render_func_filter=$5
	render_type_filter=$6
	render_const_filter=$7
	render_var_filter=$8
	render_strict_enum_typedefs=$9
	render_typed_sentinel_constants=${10}

	mkdir -p "$(dirname -- "$render_output_path")"

	set -- \
		scripts/uv-run-python-src.sh -m purego_gen \
		--lib-id fixture_lib \
		--pkg fixture \
		--emit "$render_emit_kinds"

	old_ifs=$IFS
	IFS='
'
	for render_header in $render_header_paths; do
		set -- "$@" --header "$render_header"
	done
	IFS=$old_ifs

	if [ -n "$render_func_filter" ]; then
		set -- "$@" --func-filter "$render_func_filter"
	fi
	if [ -n "$render_type_filter" ]; then
		set -- "$@" --type-filter "$render_type_filter"
	fi
	if [ -n "$render_const_filter" ]; then
		set -- "$@" --const-filter "$render_const_filter"
	fi
	if [ -n "$render_var_filter" ]; then
		set -- "$@" --var-filter "$render_var_filter"
	fi
	if [ "$render_strict_enum_typedefs" = "true" ]; then
		set -- "$@" --strict-enum-typedefs
	fi
	if [ "$render_typed_sentinel_constants" = "true" ]; then
		set -- "$@" --typed-sentinel-constants
	fi

	if [ -n "$render_clang_args" ]; then
		# shellcheck disable=SC2086 # manifest stores clang args as space-delimited tokens.
		"$@" -- $render_clang_args >"$render_output_path"
		return
	fi

	"$@" >"$render_output_path"
}
