from flask import Request
from auth.models import Users
from auth.permissions.base import Permission
from maps.models import AupInfo
from utils.exceptions import EntityNotFoundException, PermissionsDeniedException


class CanEditOwnFaculty(Permission):
    def check(self, user: Users, request: Request) -> bool:
        super().check(user, request)

        aup_num = request.headers.get("Aup")
        aup = AupInfo.query.filter(
            AupInfo.num_aup == aup_num,
            AupInfo.is_delete != True,
        ).first()

        if not aup:
            raise EntityNotFoundException(f"Map ({aup})")

        if not any(fac.id_faculty == aup.id_faculty for fac in user.faculties):
            raise PermissionsDeniedException("Доступ к редактированию запрещён")

        return True


class CanEditOwnMap(CanEditOwnFaculty): ...
