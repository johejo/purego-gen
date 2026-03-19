{
  lib,
  unzip,
  stdenv,
  autoPatchelfHook,
  source,
}:

stdenv.mkDerivation rec {
  pname = "libduckdb-bin";
  inherit (source) version src;

  nativeBuildInputs = [ unzip ] ++ lib.optionals stdenv.isLinux [ autoPatchelfHook ];

  buildInputs = [ stdenv.cc.cc.lib ];

  unpackPhase = ''
    unzip $src
  '';

  installPhase = ''
    mkdir -p $out/include
    cp duckdb.* $out/include/
    mkdir -p $out/lib
  ''
  + lib.optionalString stdenv.isLinux ''
    cp libduckdb.so $out/lib/libduckdb.so
  ''
  + lib.optionalString stdenv.isDarwin ''
    cp libduckdb.dylib $out/lib/libduckdb.dylib
  ''
  + ''
    runHook postInstall
  '';

  meta = {
    description = "libduckdb binary distribution";
    homepage = "https://duckdb.org/install";
    license = lib.licenses.mit;
    changelog = "https://github.com/duckdb/duckdb/releases/tag/${version}";
    sourcePrivate = with lib.sourceType; [ binaryNativeCode ];
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
      "aarch64-darwin"
    ];
  };
}
