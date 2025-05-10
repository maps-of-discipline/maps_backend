from enum import Enum

from auth.permissions import (
    Permission,
    CanEditAnyFaculty,
    CanEditOwnFaculty,
    CanEditOwnMap,
)


class PermissionsEnum(Permission, Enum):
    CanEditOwnFaculty = CanEditOwnFaculty("CanEditOwnFaculty")
    CanEditAnyFaculty = CanEditAnyFaculty("CanEditAnyFaculty")
    CanEditOwnMap = CanEditOwnMap("CanEditOwnMap")
