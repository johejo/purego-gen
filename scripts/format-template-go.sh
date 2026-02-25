#!/bin/sh
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ "$#" -eq 0 ]; then
	set -- templates/*.j2
	if [ "$1" = "templates/*.j2" ]; then
		exit 0
	fi
fi

for template_path in "$@"; do
	tmp_file="$(mktemp)"
	# Keep template source aligned with djlint's 4-space indentation width.
	expand -t 4 "$template_path" >"$tmp_file"
	if cmp -s "$template_path" "$tmp_file"; then
		rm -f "$tmp_file"
		continue
	fi
	mv "$tmp_file" "$template_path"
done

djlint --reformat --extension=j2 --preserve-leading-space --preserve-blank-lines "$@"
