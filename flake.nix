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
              export UV_PROJECT_ENVIRONMENT=.venv
            '';
          };
        }
      );
    };
}
