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
          isStandaloneLibclangSystem =
            pkgs.stdenv.hostPlatform.isDarwin && pkgs.stdenv.hostPlatform.isAarch64;
          llvmPkgs = pkgs.llvmPackages_21;
          llvmSourceTree = llvmPkgs.llvm.src;
          clangSourceTree = llvmPkgs.clang-unwrapped.src;
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
          standaloneLibclangCmakeFlags = [
            "-G"
            "Ninja"
            "-DCMAKE_BUILD_TYPE=Release"
            "-DBUILD_SHARED_LIBS=OFF"
            "-DLLVM_ENABLE_PROJECTS=clang"
            "-DLLVM_ENABLE_BINDINGS=OFF"
            "-DLLVM_BUILD_LLVM_DYLIB=OFF"
            "-DLLVM_LINK_LLVM_DYLIB=OFF"
            "-DLLVM_INCLUDE_TESTS=OFF"
            "-DLLVM_INCLUDE_BENCHMARKS=OFF"
            "-DLLVM_INCLUDE_EXAMPLES=OFF"
            "-DCLANG_INCLUDE_TESTS=OFF"
            "-DCLANG_BUILD_EXAMPLES=OFF"
            "-DCLANG_BUILD_TOOLS=OFF"
            "-DLLVM_TARGETS_TO_BUILD=host"
            "-DLLVM_ENABLE_ZSTD=OFF"
            "-DLLVM_ENABLE_LIBXML2=OFF"
            "-DLLVM_ENABLE_FFI=OFF"
            "-DLLVM_ENABLE_TERMINFO=OFF"
            "-DLLVM_ENABLE_LIBEDIT=OFF"
            "-DZLIB_INCLUDE_DIR=${pkgs.zlib.dev}/include"
            "-DZLIB_LIBRARY=${pkgs.zlib.static}/lib/libz.a"
          ];
          standaloneLibclangPackage =
            if !isStandaloneLibclangSystem then
              null
            else
              llvmPkgs.stdenv.mkDerivation {
                pname = "standalone-libclang";
                version = llvmPkgs.clang-unwrapped.version;
                dontUnpack = true;
                strictDeps = true;
                enableParallelBuilding = true;
                nativeBuildInputs = with pkgs; [
                  cmake
                  gnused
                  ninja
                  python314
                ];
                configurePhase = ''
                  runHook preConfigure
                  source_root="$PWD/llvm-project"
                  mkdir -p "$source_root"
                  for entry in ${llvmSourceTree}/*; do
                    cp -R "$entry" "$source_root/$(basename "$entry")"
                  done
                  cp -R ${clangSourceTree}/clang "$source_root/clang"
                  cp -R ${clangSourceTree}/clang-tools-extra "$source_root/clang-tools-extra"
                  ls -1 "$source_root" | sed -n '1,20p'
                  cmake -S "$source_root/llvm" -B build ${lib.escapeShellArgs standaloneLibclangCmakeFlags}
                  runHook postConfigure
                '';
                buildPhase = ''
                  runHook preBuild
                  cmake --build build --target libclang
                  runHook postBuild
                '';
                installPhase = ''
                  runHook preInstall
                  mkdir -p "$out/lib"
                  cp build/lib/libclang.dylib "$out/lib/libclang.dylib"
                  runHook postInstall
                '';
                meta = {
                  description = "Standalone libclang dylib built without a libLLVM runtime dependency";
                  license = lib.licenses.ncsa;
                  platforms = [ "aarch64-darwin" ];
                };
              };
          standaloneLibclangCheck =
            if standaloneLibclangPackage == null then
              null
            else
              pkgs.runCommand "standalone-libclang-smoke"
                {
                  nativeBuildInputs = [
                    pkgs.darwin.cctools
                    pkgs.python314
                  ];
                }
                ''
                  dylib="${standaloneLibclangPackage}/lib/libclang.dylib"
                  otool -L "$dylib" > deps.txt
                  if grep -F "libLLVM.dylib" deps.txt >/dev/null; then
                    echo "standalone libclang still depends on libLLVM.dylib" >&2
                    cat deps.txt >&2
                    exit 1
                  fi
                  external_deps="$(tail -n +2 deps.txt | grep -v '^	@rpath/libclang.dylib')"
                  dep_count="$(printf '%s\n' "$external_deps" | sed '/^$/d' | wc -l | tr -d ' ')"
                  if [ "$dep_count" -ne 2 ]; then
                    echo "unexpected dylib dependency count: $dep_count" >&2
                    cat deps.txt >&2
                    exit 1
                  fi
                  printf '%s\n' "$external_deps" | grep -F "/usr/lib/libc++.1.dylib" >/dev/null
                  printf '%s\n' "$external_deps" | grep -F "/usr/lib/libSystem.B.dylib" >/dev/null
                  nm -gUj "$dylib" | grep -Fx "_clang_createIndex" >/dev/null
                  nm -gUj "$dylib" | grep -Fx "_clang_parseTranslationUnit" >/dev/null
                  nm -gUj "$dylib" | grep -Fx "_clang_disposeIndex" >/dev/null
                  python - <<'PY'
                  import ctypes
                  lib = ctypes.CDLL("${standaloneLibclangPackage}/lib/libclang.dylib")
                  for name in (
                      "clang_createIndex",
                      "clang_parseTranslationUnit",
                      "clang_disposeIndex",
                  ):
                      getattr(lib, name)
                  PY
                  touch "$out"
                '';
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
                    ]
                  }" \
                  --set PUREGO_GEN_TEST_LIBZSTD_INCLUDE_DIR "${pkgs.zstd.dev}/include" \
                  --set PUREGO_GEN_TEST_LIBZSTD_LIB_DIR "${pkgs.zstd.out}/lib"
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
                PUREGO_GEN_TEST_LIBCLANG_INCLUDE_DIR = "${pkgs.libclang.dev}/include";
                PUREGO_GEN_TEST_LIBCLANG_LIB_DIR = "${pkgs.libclang.lib}/lib";
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
          } // lib.optionalAttrs (standaloneLibclangCheck != null) {
            standalone-libclang = standaloneLibclangCheck;
          };

          packages =
            {
              purego-gen = puregoGenPackage;
              golden-cases = goldenCasesRunner;
              default = puregoGenPackage;
            }
            // lib.optionalAttrs (standaloneLibclangPackage != null) {
              standalone-libclang = standaloneLibclangPackage;
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
