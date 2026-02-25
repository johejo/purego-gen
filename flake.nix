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
