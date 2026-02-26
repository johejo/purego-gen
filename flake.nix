{
  description = "purego-gen development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      treefmt-nix,
      ...
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      mkTreefmt = pkgs: treefmt-nix.lib.evalModule pkgs ./treefmt.nix;
      forAllSystems =
        f:
        nixpkgs.lib.genAttrs systems (
          system:
          f {
            pkgs = import nixpkgs {
              inherit system;
            };
          }
        );
    in
    {
      formatter = forAllSystems ({ pkgs }: (mkTreefmt pkgs).config.build.wrapper);

      checks = forAllSystems (
        { pkgs }:
        {
          formatting = (mkTreefmt pkgs).config.build.check self;
        }
      );

      devShells = forAllSystems (
        { pkgs }:
        let
          treefmt = (mkTreefmt pkgs).config.build.wrapper;
          commonPackages = with pkgs; [
            actionlint
            bash
            ccache
            clang
            clang-tools
            go
            jq
            just
            libclang
            nixfmt
            pkg-config
            python314
            shellcheck
            shfmt
            uv
            zstd
            treefmt
          ];
          mkDevShell =
            extra:
            pkgs.mkShell (
              {
                packages = commonPackages;
                LIBCLANG_PATH = "${pkgs.libclang.lib}/lib";
              }
              // extra
            );
        in
        {
          default = mkDevShell {
            shellHook = ''
              if [ -n "''${CODEX_SHELL:-}" ] || [ -n "''${CODEX_CI:-}" ]; then
                echo "purego-gen: in Codex, use 'nix develop .#coding-agent -c ...' instead of 'nix develop -c ...'." >&2
                exit 1
              fi
            '';
          };
          coding-agent = mkDevShell {
            shellHook = ''
              guarded_env_vars="
              XDG_CACHE_HOME
              GOMODCACHE
              GOCACHE
              CCACHE_DIR
              CCACHE_BASEDIR
              CCACHE_NOHASHDIR
              UV_PROJECT_ENVIRONMENT
              "
              for var_name in $guarded_env_vars; do
                if printenv "$var_name" >/dev/null 2>&1; then
                  echo "purego-gen: coding-agent requires $var_name to be unset before nix develop; external override is not allowed." >&2
                  exit 1
                fi
              done
              export XDG_CACHE_HOME="$PWD/.cache"
              export GOMODCACHE="$PWD/.cache/gomod"
              export GOCACHE="$PWD/.cache/go-build"
              export CCACHE_DIR="$PWD/.cache/ccache"
              export CCACHE_BASEDIR="$PWD"
              export CCACHE_NOHASHDIR=1
              export UV_PROJECT_ENVIRONMENT=.venv
            '';
          };
        }
      );
    };
}
