#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ -n "${PYTHONPATH:-}" ]; then
	export PYTHONPATH="src:$PYTHONPATH"
else
	export PYTHONPATH="src"
fi

exec uv run python "$@"
