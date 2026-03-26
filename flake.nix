{
  description = "purego-gen development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    zig-overlay = {
      url = "github:mitchellh/zig-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      treefmt-nix,
      zig-overlay,
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
          system = pkgs.stdenv.hostPlatform.system;
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
            annotated-types
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
                  --set PUREGO_GEN_TEMPLATE_DIR "$out/share/purego-gen/templates" \
                  ${extraWrapArgs}
              '';
              meta = commonPythonAppMeta // {
                inherit description mainProgram;
              };
            };
          testLibEnvVars = {
            PUREGO_GEN_TEST_LIBCLANG_INCLUDE_DIR = "${pkgs.libclang.dev}/include";
            PUREGO_GEN_TEST_LIBCLANG_LIB_DIR = "${pkgs.libclang.lib}/lib";
            PUREGO_GEN_TEST_LIBZSTD_INCLUDE_DIR = "${pkgs.zstd.dev}/include";
            PUREGO_GEN_TEST_LIBZSTD_LIB_DIR = "${pkgs.zstd.out}/lib";
            PUREGO_GEN_TEST_LIBSQLITE3_INCLUDE_DIR = "${pkgs.sqlite.dev}/include";
            PUREGO_GEN_TEST_LIBSQLITE3_LIB_DIR = "${pkgs.sqlite.out}/lib";
            PUREGO_GEN_TEST_LIBDUCKDB_INCLUDE_DIR = "${self.packages.${system}.libduckdb-bin}/include";
            PUREGO_GEN_TEST_LIBDUCKDB_LIB_DIR = "${self.packages.${system}.libduckdb-bin}/lib";
          };
          puregoGenPackage = mkPackagedPuregoGenApplication {
            pname = "purego-gen";
            mainProgram = "purego-gen";
            description = "Practical C-header-to-purego binding generator";
            pythonImportsCheck = [ "purego_gen" ];
          };
          goldenCasesPackage = mkPackagedPuregoGenApplication {
            pname = "golden-cases";
            mainProgram = "golden-cases";
            description = "Run purego-gen golden cases with nix-provided Python/toolchain";
            pythonImportsCheck = [
              "purego_gen"
              "purego_gen_e2e"
            ];
            extraWrapArgs =
              let
                envSetArgs = lib.concatStringsSep " \\\n                  " (
                  lib.mapAttrsToList (name: value: ''--set ${name} "${value}"'') testLibEnvVars
                );
              in
              ''
                --prefix PATH : "$out/bin:${
                  lib.makeBinPath [
                    pkgs.clang
                    pkgs.git
                    pkgs.go
                  ]
                }" \
                  ${envSetArgs}
              '';
          };
          commonPackages =
            (with pkgs; [
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
            ])
            ++ [ zig-overlay.packages.${system}."0.15.2" ];
          sources = pkgs.callPackage ./_sources/generated.nix { };
        in
        {
          formatter = treefmt;

          checks = {
            formatting = (mkTreefmt pkgs).config.build.check self;
          };

          packages = {
            purego-gen = puregoGenPackage;
            golden-cases = goldenCasesPackage;
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
                program = lib.getExe goldenCasesPackage;
                meta = goldenCasesPackage.meta;
              };
            in
            {
              purego-gen = puregoGenApp;
              golden-cases = goldenCasesApp;
              default = puregoGenApp;
            };

          devShells =
            let
              libclangStatic = pkgs.llvmPackages.libclang.overrideAttrs (old: {
                cmakeFlags = (old.cmakeFlags or [ ]) ++ [ "-DLIBCLANG_BUILD_STATIC=ON" ];
              });
            in
            {
              default = pkgs.mkShell (
                {
                  packages = commonPackages;
                  LIBCLANG_PATH = "${pkgs.libclang.lib}/lib";
                  LIBCLANG_INCLUDE_PATH = "${pkgs.libclang.dev}/include";
                  LLVM_LIB_PATH = "${pkgs.llvmPackages.llvm.lib}/lib";
                  ZLIB_STATIC_PATH = "${pkgs.zlib.static}/lib";
                  LIBCLANG_STATIC_PATH = "${libclangStatic.lib}/lib";
                  shellHook = ''
                    if [ "''${PUREGO_GEN_DEVSHELL:-}" = "1" ]; then
                      echo "purego-gen: already inside devshell; do not nest nix develop." >&2
                      exit 1
                    fi
                    export PUREGO_GEN_DEVSHELL=1
                    export XDG_CACHE_HOME="$PWD/.cache"
                    export GOMODCACHE="$PWD/.cache/gomod"
                    export GOCACHE="$PWD/.cache/go-build"
                    export CCACHE_DIR="$PWD/.cache/ccache"
                    export CCACHE_BASEDIR="$PWD"
                    export CCACHE_NOHASHDIR=1
                    export UV_PROJECT_ENVIRONMENT=.venv
                  '';
                }
                // testLibEnvVars
              );
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
