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
        f: nixpkgs.lib.genAttrs systems (system: f { pkgs = import nixpkgs { inherit system; }; });
      perSystem = forAllSystems (
        { pkgs }:
        let
          system = pkgs.system;
          lib = pkgs.lib;
          pythonPkgs = pkgs.python314Packages;
          treefmt = (mkTreefmt pkgs).config.build.wrapper;
          pythonAppVersion = "0.0.0";
          commonPythonAppMeta = {
            license = lib.licenses.asl20;
            platforms = systems;
          };
          commonPythonBuildSystem = with pythonPkgs; [
            setuptools
            wheel
          ];
          commonPythonDependencies = with pythonPkgs; [
            libclang
            jinja2
            pydantic
            pythonPkgs."annotated-types"
          ];
          mkPythonApplication =
            args:
            pythonPkgs.buildPythonApplication (
              {
                version = pythonAppVersion;
                src = self;
                nativeBuildInputs = [ pkgs.makeWrapper ];
                dependencies = commonPythonDependencies;
                meta = commonPythonAppMeta;
              }
              // args
            );
          commonTemplateInstall = ''
            mkdir -p "$out/share/purego-gen"
            cp -r "$src/templates" "$out/share/purego-gen/templates"
          '';
          mkPackagedPuregoGenApplication =
            {
              pname,
              mainProgram,
              description,
              pythonImportsCheck,
              extraWrapArgs ? "",
            }:
            mkPythonApplication {
              inherit pname;
              pyproject = true;
              build-system = commonPythonBuildSystem;
              inherit pythonImportsCheck;
              postInstall = commonTemplateInstall;
              postFixup = ''
                wrapProgram "$out/bin/${mainProgram}" \
                  --set LIBCLANG_PATH "${pkgs.libclang.lib}/lib" \
                  --set PUREGO_GEN_TEMPLATE_DIR "$out/share/purego-gen/templates"${extraWrapArgs}
              '';
              meta = commonPythonAppMeta // {
                inherit description mainProgram;
              };
            };
          puregoGenPackage = mkPackagedPuregoGenApplication {
            pname = "purego-gen";
            mainProgram = "purego-gen";
            description = "Practical C-header-to-purego binding generator";
            pythonImportsCheck = [ "purego_gen" ];
          };
          goldenCasesRunner = mkPackagedPuregoGenApplication {
            pname = "golden-cases";
            mainProgram = "golden-cases";
            description = "Run purego-gen golden cases with nix-provided Python/toolchain";
            pythonImportsCheck = [
              "purego_gen"
              "purego_gen_e2e"
            ];
            extraWrapArgs = ''
              \
                  --prefix PATH : "$out/bin:${
                    lib.makeBinPath [
                      pkgs.clang
                      pkgs.git
                      pkgs.go
                      pkgs.sqlite
                    ]
                  }" \
                  --set PUREGO_GEN_TEST_LIBCLANG_INCLUDE_DIR "${pkgs.libclang.dev}/include" \
                  --set PUREGO_GEN_TEST_LIBCLANG_LIB_DIR "${pkgs.libclang.lib}/lib" \
                  --set PUREGO_GEN_TEST_LIBZSTD_INCLUDE_DIR "${pkgs.zstd.dev}/include" \
                  --set PUREGO_GEN_TEST_LIBZSTD_LIB_DIR "${pkgs.zstd.out}/lib" \
                  --set PUREGO_GEN_TEST_LIBSQLITE3_INCLUDE_DIR "${pkgs.sqlite.dev}/include" \
                  --set PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR "${pkgs.sqlite.out}/lib"
            '';
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
            gnugrep
            jq
            just
            libclang
            nixfmt
            pkg-config
            python314
            shellcheck
            shfmt
            go-tools
            uv
            sqlite
            zstd
            treefmt
          ];
          mkDevShell =
            extra:
            pkgs.mkShell (
              {
                packages = commonPackages;
                LIBCLANG_PATH = "${pkgs.libclang.lib}/lib";
                PUREGO_GEN_TEST_LIBCLANG_INCLUDE_DIR = "${pkgs.libclang.dev}/include";
                PUREGO_GEN_TEST_LIBCLANG_LIB_DIR = "${pkgs.libclang.lib}/lib";
                PUREGO_GEN_TEST_LIBZSTD_INCLUDE_DIR = "${pkgs.zstd.dev}/include";
                PUREGO_GEN_TEST_LIBZSTD_LIB_DIR = "${pkgs.zstd.out}/lib";
                PUREGO_GEN_TEST_LIBSQLITE3_INCLUDE_DIR = "${pkgs.sqlite.dev}/include";
                PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR = "${pkgs.sqlite.out}/lib";
              }
              // extra
            );
          sources = pkgs.callPackage ./_sources/generated.nix { };
        in
        {
          formatter = treefmt;

          checks = {
            formatting = (mkTreefmt pkgs).config.build.check self;
          };

          packages = {
            purego-gen = puregoGenPackage;
            golden-cases = goldenCasesRunner;
            default = puregoGenPackage;
            libduckdb-bin = pkgs.callPackage ./libduckdb-bin.nix {
              source = sources."libduckdb-${system}-bin";
            };
          };

          apps =
            let
              puregoGenApp = {
                type = "app";
                program = lib.getExe puregoGenPackage;
                meta = puregoGenPackage.meta;
              };
              goldenCasesApp = {
                type = "app";
                program = lib.getExe goldenCasesRunner;
                meta = goldenCasesRunner.meta;
              };
            in
            {
              purego-gen = puregoGenApp;
              golden-cases = goldenCasesApp;
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
                    echo "purego-gen: coding-agent automatically sets $var_name to shell; you don't have to set/unset them." >&2
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
