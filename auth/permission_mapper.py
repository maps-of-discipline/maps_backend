from flask import Request

from auth.models import Users
from utils.exceptions import PermissionsDeniedException, EntityNotFoundException
from maps.models import AupInfo


class PermissionMapper:
    def __init__(
        self,
    ):
        self.mapper: dict = {
            "canEditFaculty": self._check_can_edit_faculty,
        }

    def check_permissions(self, permissions: list[str], user: Users, request: Request):
        for perm in permissions:
            if perm in self.mapper:
                checker = self.mapper[perm]
                checker(user, request)

    def _check_can_edit_faculty(self, user: Users, request: Request):
        aup_num = request.headers.get("Aup")
        aup = AupInfo.query.filter(
            AupInfo.num_aup == aup_num, not AupInfo.is_delete != True
        ).first()
        if not aup:
            raise EntityNotFoundException(f"Map ({aup})")

        if not any(fac.id_faculty == aup.id_faculty for fac in user.faculties):
            raise PermissionsDeniedException("Доступ к редактированию запрещён")
