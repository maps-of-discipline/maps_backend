from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class GetPayloadRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class GetPayloadResponse(_message.Message):
    __slots__ = ("user_id", "role", "expires_at", "service_name", "permissions")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    PERMISSIONS_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    role: str
    expires_at: str
    service_name: str
    permissions: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, user_id: _Optional[str] = ..., role: _Optional[str] = ..., expires_at: _Optional[str] = ..., service_name: _Optional[str] = ..., permissions: _Optional[_Iterable[str]] = ...) -> None: ...

class GetUserRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class GetUserResponse(_message.Message):
    __slots__ = ("id", "external_id", "role", "external_role", "name", "surname", "patronymic", "email", "faculty", "login", "last_login", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_ROLE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SURNAME_FIELD_NUMBER: _ClassVar[int]
    PATRONYMIC_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    FACULTY_FIELD_NUMBER: _ClassVar[int]
    LOGIN_FIELD_NUMBER: _ClassVar[int]
    LAST_LOGIN_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    external_id: str
    role: str
    external_role: str
    name: str
    surname: str
    patronymic: str
    email: str
    faculty: str
    login: str
    last_login: str
    created_at: str
    def __init__(self, id: _Optional[str] = ..., external_id: _Optional[str] = ..., role: _Optional[str] = ..., external_role: _Optional[str] = ..., name: _Optional[str] = ..., surname: _Optional[str] = ..., patronymic: _Optional[str] = ..., email: _Optional[str] = ..., faculty: _Optional[str] = ..., login: _Optional[str] = ..., last_login: _Optional[str] = ..., created_at: _Optional[str] = ...) -> None: ...
