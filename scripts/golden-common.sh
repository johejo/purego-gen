#!/usr/bin/env sh

for_each_golden_case() {
	case_callback=$1
	case_file=$2
	tab_char="$(printf '\t')"

	jq -r '.cases[] | [.id, .output_path, .header_path, .emit_kinds, (.clang_args // "")] | @tsv' "$case_file" |
		while IFS="$tab_char" read -r case_id output_path header_path emit_kinds clang_args; do
			"$case_callback" "$case_id" "$output_path" "$header_path" "$emit_kinds" "$clang_args"
		done
}

render_golden_case() {
	render_output_path=$1
	render_header_path=$2
	render_emit_kinds=$3
	render_clang_args=$4

	if [ -n "$render_clang_args" ]; then
		# shellcheck disable=SC2086 # manifest stores clang args as space-delimited tokens.
		PYTHONPATH=src uv run python -m purego_gen \
			--lib-id sample_lib \
			--header "$render_header_path" \
			--pkg sample \
			--emit "$render_emit_kinds" \
			-- \
			$render_clang_args >"$render_output_path"
		return
	fi

	PYTHONPATH=src uv run python -m purego_gen \
		--lib-id sample_lib \
		--header "$render_header_path" \
		--pkg sample \
		--emit "$render_emit_kinds" >"$render_output_path"
}
