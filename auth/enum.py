from enum import Enum

from auth.permissions.maps import (
    Permission,
    CanEditOwnFaculty,
    CanEditOwnMap,
    CanUploadPlan,
    CanAddModule,
    CanChangeModule,
    CanAddGroup,
    CanDeleteGroup,
    CanUpdateGroup,
    CanSaveWeeks,
    CanSaveReports,
    
)


class PermissionsEnum(Permission, Enum):
    canEditOwnFaculty = CanEditOwnFaculty("CanEditOwnFaculty")
    canEditAnyFaculty = Permission("CanEditAnyFaculty")
    canEditOwnMap = CanEditOwnMap("CanEditOwnMap") 
    canEditAnyMap = Permission("CanEditAnyMap")
    canUploadPlan = CanUploadPlan("CanUploadPlan")
    canAddModule = CanAddModule("CanAddModule")
    canChangeModule = CanChangeModule("CanChangeModule")
    canAddGroup = CanAddGroup("CanAddGroup")
    canDeleteGroup = CanDeleteGroup("CanDeleteGroup")
    canUpdateGroup = CanUpdateGroup("CanUpdateGroup")
    canSaveWeeks = CanSaveWeeks("CanSaveWeeks")
    canSaveReports = CanSaveReports("CanSaveReports")
