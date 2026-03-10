from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PutRequest(_message.Message):
    __slots__ = ("key", "textbook_chunk", "embedding")
    KEY_FIELD_NUMBER: _ClassVar[int]
    TEXTBOOK_CHUNK_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    key: str
    textbook_chunk: str
    embedding: bytes
    def __init__(self, key: _Optional[str] = ..., textbook_chunk: _Optional[str] = ..., embedding: _Optional[bytes] = ...) -> None: ...

class PutResponse(_message.Message):
    __slots__ = ("overwritten",)
    OVERWRITTEN_FIELD_NUMBER: _ClassVar[int]
    overwritten: bool
    def __init__(self, overwritten: bool = ...) -> None: ...

class StreamEmbeddingsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StreamEmbeddingsResponse(_message.Message):
    __slots__ = ("key", "embedding")
    KEY_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    key: str
    embedding: bytes
    def __init__(self, key: _Optional[str] = ..., embedding: _Optional[bytes] = ...) -> None: ...

class GetTextRequest(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class GetTextResponse(_message.Message):
    __slots__ = ("found", "textbook_chunk")
    FOUND_FIELD_NUMBER: _ClassVar[int]
    TEXTBOOK_CHUNK_FIELD_NUMBER: _ClassVar[int]
    found: bool
    textbook_chunk: str
    def __init__(self, found: bool = ..., textbook_chunk: _Optional[str] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = ("name", "version", "key_count")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    KEY_COUNT_FIELD_NUMBER: _ClassVar[int]
    name: str
    version: str
    key_count: int
    def __init__(self, name: _Optional[str] = ..., version: _Optional[str] = ..., key_count: _Optional[int] = ...) -> None: ...
