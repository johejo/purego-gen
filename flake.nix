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
      perSystem = forAllSystems (
        { pkgs }:
        let
          lib = pkgs.lib;
          treefmt = (mkTreefmt pkgs).config.build.wrapper;
          pythonRuntime = pkgs.python314.withPackages (pythonPkgs: [
            pythonPkgs.libclang
            pythonPkgs.jinja2
            pythonPkgs.pydantic
            pythonPkgs."annotated-types"
          ]);
          puregoGenPackage = pkgs.stdenvNoCC.mkDerivation {
            pname = "purego-gen";
            version = "0.0.0";
            src = self;
            nativeBuildInputs = [ pkgs.makeWrapper ];
            dontBuild = true;
            installPhase = ''
              runHook preInstall

              mkdir -p "$out/bin" "$out/share/purego-gen"
              cp -r "$src/src" "$out/share/purego-gen/src"
              cp -r "$src/templates" "$out/share/purego-gen/templates"

              makeWrapper ${pythonRuntime}/bin/python "$out/bin/purego-gen" \
                --set LIBCLANG_PATH "${pkgs.libclang.lib}/lib" \
                --set PYTHONPATH "$out/share/purego-gen/src" \
                --add-flags "-m purego_gen"

              runHook postInstall
            '';
            meta = {
              description = "Practical C-header-to-purego binding generator";
              mainProgram = "purego-gen";
              license = lib.licenses.asl20;
              platforms = systems;
            };
          };
          codingAgentEnvGuard = pkgs.writeShellScriptBin "env" ''
            echo "purego-gen: coding-agent blocks env. In most cases, run commands directly (for example: uv run ...); required cache env vars are already set by shellHook." >&2
            exit 1
          '';
          commonPackages = with pkgs; [
            actionlint
            bash
            ccache
            clang
            clang-tools
            duckdb
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
                PUREGO_GEN_TEST_LIBZSTD_INCLUDE_DIR = "${pkgs.zstd.dev}/include";
                PUREGO_GEN_TEST_LIBZSTD_LIB_DIR = "${pkgs.zstd.out}/lib";
              }
              // extra
            );
        in
        {
          formatter = treefmt;

          checks = {
            formatting = (mkTreefmt pkgs).config.build.check self;
          };

          packages = {
            purego-gen = puregoGenPackage;
            default = puregoGenPackage;
          };

          apps =
            let
              puregoGenApp = {
                type = "app";
                program = lib.getExe puregoGenPackage;
                meta = puregoGenPackage.meta;
              };
            in
            {
              purego-gen = puregoGenApp;
              default = puregoGenApp;
            };

          devShells = {
            default = mkDevShell {
              shellHook = ''
                if [ -n "''${CODEX_SHELL:-}" ] || [ -n "''${CODEX_CI:-}" ]; then
                  echo "purego-gen: in Codex, use 'nix develop .#coding-agent -c ...' instead of 'nix develop -c ...'." >&2
                  exit 1
                fi
              '';
            };
            coding-agent = mkDevShell {
              packages = [ codingAgentEnvGuard ] ++ commonPackages;
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
          };
        }
      );
    in
    {
      formatter = nixpkgs.lib.mapAttrs (_: attrs: attrs.formatter) perSystem;
      checks = nixpkgs.lib.mapAttrs (_: attrs: attrs.checks) perSystem;
      packages = nixpkgs.lib.mapAttrs (_: attrs: attrs.packages) perSystem;
      apps = nixpkgs.lib.mapAttrs (_: attrs: attrs.apps) perSystem;
      devShells = nixpkgs.lib.mapAttrs (_: attrs: attrs.devShells) perSystem;
    };
}
