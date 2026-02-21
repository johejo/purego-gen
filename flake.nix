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
        "x86_64-darwin"
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
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              ccache
              clang
              clang-tools
              go
              jq
              just
              lefthook
              libclang
              nixfmt
              python314
              shellcheck
              shfmt
              uv
              treefmt
            ];

            LIBCLANG_PATH = "${pkgs.libclang.lib}/lib";

            shellHook = ''
              export XDG_CACHE_HOME="$PWD/.cache"
              export GOMODCACHE="$XDG_CACHE_HOME/gomod"
              export GOCACHE="$XDG_CACHE_HOME/go-build"
              export CCACHE_DIR="$XDG_CACHE_HOME/ccache"
              export CCACHE_BASEDIR="$PWD"
              export CCACHE_NOHASHDIR=1
              export CC="ccache clang"
              export CXX="ccache clang++"
              mkdir -p "$XDG_CACHE_HOME/nix" "$GOMODCACHE" "$GOCACHE" "$CCACHE_DIR"
              export UV_PROJECT_ENVIRONMENT=.venv
            '';
          };
        }
      );
    };
}
