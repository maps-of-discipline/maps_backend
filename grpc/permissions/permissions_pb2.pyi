from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CreatePermission(_message.Message):
    __slots__ = ("title", "verbose_name")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    VERBOSE_NAME_FIELD_NUMBER: _ClassVar[int]
    title: str
    verbose_name: str
    def __init__(self, title: _Optional[str] = ..., verbose_name: _Optional[str] = ...) -> None: ...

class Permission(_message.Message):
    __slots__ = ("id", "title", "verbose_name")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    VERBOSE_NAME_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    verbose_name: str
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., verbose_name: _Optional[str] = ...) -> None: ...

class GetPermissionsByServiceRequest(_message.Message):
    __slots__ = ("service_name",)
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    service_name: str
    def __init__(self, service_name: _Optional[str] = ...) -> None: ...

class GetPermissionsByServiceResponse(_message.Message):
    __slots__ = ("permissions",)
    PERMISSIONS_FIELD_NUMBER: _ClassVar[int]
    permissions: _containers.RepeatedCompositeFieldContainer[Permission]
    def __init__(self, permissions: _Optional[_Iterable[_Union[Permission, _Mapping]]] = ...) -> None: ...

class CreateServicePermissionRequest(_message.Message):
    __slots__ = ("service_name", "permission")
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    PERMISSION_FIELD_NUMBER: _ClassVar[int]
    service_name: str
    permission: CreatePermission
    def __init__(self, service_name: _Optional[str] = ..., permission: _Optional[_Union[CreatePermission, _Mapping]] = ...) -> None: ...

class CreateServicePermissionResponse(_message.Message):
    __slots__ = ("permission",)
    PERMISSION_FIELD_NUMBER: _ClassVar[int]
    permission: Permission
    def __init__(self, permission: _Optional[_Union[Permission, _Mapping]] = ...) -> None: ...

class UpdateServicePermissionRequest(_message.Message):
    __slots__ = ("service_name", "permission")
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    PERMISSION_FIELD_NUMBER: _ClassVar[int]
    service_name: str
    permission: Permission
    def __init__(self, service_name: _Optional[str] = ..., permission: _Optional[_Union[Permission, _Mapping]] = ...) -> None: ...

class UpdateServicePermissionResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class DeleteServicePermissionRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class DeleteServicePermissionResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
