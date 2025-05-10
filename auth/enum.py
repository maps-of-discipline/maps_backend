from enum import Enum

from auth.permissions import (
    Permission,
    CanEditOwnFaculty,
    CanEditOwnMap,
)


class PermissionsEnum(Permission, Enum):
    canEditOwnFaculty = CanEditOwnFaculty("CanEditOwnFaculty")
    canEditAnyFaculty = Permission("CanEditAnyFaculty")
    canEditOwnMap = CanEditOwnMap("CanEditOwnMap")
    canEditAnyMap = Permission("CanEditAnyMap")
