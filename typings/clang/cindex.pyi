# Copyright (c) 2026 purego-gen contributors.

class Config:
    loaded: bool

    @staticmethod
    def set_library_path(path: str) -> None: ...

class TranslationUnit:
    PARSE_SKIP_FUNCTION_BODIES: int
    PARSE_DETAILED_PROCESSING_RECORD: int

class CursorKind:
    FUNCTION_DECL: object
    TYPEDEF_DECL: object
    ENUM_CONSTANT_DECL: object
    VAR_DECL: object
    MACRO_DEFINITION: object

class Cursor: ...

class _IndexInstance:
    def parse(
        self,
        *,
        path: str,
        args: list[str],
        options: int,
    ) -> object: ...

class Index:
    @staticmethod
    def create() -> _IndexInstance: ...

class TranslationUnitLoadError(Exception): ...
class LibclangError(Exception): ...
