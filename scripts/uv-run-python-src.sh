#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"

if [ -n "${PYTHONPATH:-}" ]; then
	export PYTHONPATH="$REPO_ROOT/src:$PYTHONPATH"
else
	export PYTHONPATH="$REPO_ROOT/src"
fi

exec uv run --project "$REPO_ROOT" python "$@"
