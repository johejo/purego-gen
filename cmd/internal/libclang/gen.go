package libclang

//go:generate ../../../scripts/uv-run-python-src.sh -m purego_gen --lib-id clang --pkg libclang --emit func,type,const --header $PUREGO_GEN_TEST_LIBCLANG_INCLUDE_DIR/clang-c/Index.h --func-filter ^(clang_createIndex|clang_disposeIndex|clang_parseTranslationUnit|clang_disposeTranslationUnit|clang_getNumDiagnostics)$ --type-filter ^(CXIndex|CXTranslationUnit)$ --const-filter ^(CXTranslationUnit_DetailedPreprocessingRecord|CXTranslationUnit_SkipFunctionBodies)$ --const-char-as-string --out generated.go -- -I $PUREGO_GEN_TEST_LIBCLANG_INCLUDE_DIR
