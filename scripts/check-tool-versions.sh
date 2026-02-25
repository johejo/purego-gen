#!/bin/sh
set -eu

extract_semver() {
	printf '%s\n' "$1" | sed -nE 's/.*([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' | head -n 1
}

uv_djlint_raw="$(uv run djlint --version 2>/dev/null || true)"

nix_djlint_ver="$(
	nix eval --impure --raw --expr '
		let
			flake = builtins.getFlake (toString ./.);
			pkgs = import flake.inputs.nixpkgs { system = builtins.currentSystem; };
		in
			pkgs.djlint.version
	' 2>/dev/null || true
)"
uv_djlint_ver="$(extract_semver "$uv_djlint_raw")"

if [ -z "$nix_djlint_ver" ]; then
	echo "failed to determine djlint version from flake-pinned nixpkgs." >&2
	exit 1
fi

if [ -z "$uv_djlint_ver" ]; then
	echo "failed to determine djlint version from uv environment: $uv_djlint_raw" >&2
	exit 1
fi

if [ "$nix_djlint_ver" != "$uv_djlint_ver" ]; then
	echo "djlint version mismatch detected:" >&2
	echo "  nix: $nix_djlint_ver" >&2
	echo "  uv : $uv_djlint_ver" >&2
	echo "align flake.lock and uv.lock so both toolchains use the same djlint version." >&2
	exit 1
fi
