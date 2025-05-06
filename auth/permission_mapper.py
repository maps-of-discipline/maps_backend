from typing import Dict
from flask import Request

from grpc_service.dto.auth import TokenPayload
from auth.models import Users
from auth.exceptions import PermissionDeniedError
from maps.models import AupInfo

class PermissionMapper:
    def __init__(self,):
        self.mapper: dict = {
            "canEditFaculty": self._check_can_edit_faculty, 
            "perm2": self._check_perm2, 
        } 
        
        
    def check_permissions(self, permissions: list[str], user: Users, request: Request):
        for perm in permissions: 
            if perm in self.mapper:
                checker = self.mapper[perm]
                checker(user, request)
        
        
    def _check_can_edit_faculty(self, user: Users, request: Request):
        aup_num = request.headers.get('Aup')
        aup = AupInfo.query.filter(AupInfo.num_aup == aup_num, AupInfo.is_delete != True).first()
        if not aup:
            raise PermissionDeniedError(f"Карта дисциплин {aup_num} не найдена")
        
        if not any(fac.id_faculty == aup.id_faculty for fac in user.faculties):
            raise PermissionDeniedError("Доступ к редактированию запрещён")
        
        # have_access = True
        # if not have_access: 
        #     raise Exception("Permissions denied")

    def _check_perm2(self, user: Users, reqeust: Request):
        ...
        have_access = True
        if not have_access: 
            raise Exception("Permissions denied")

    def _check_perm3(self, user: Users, reqeust: Request):
            ...
            have_access = True
            if not have_access: 
          
                raise Exception("Permissions denied")
            



# if __name__ == '__main__':
#     required = [...]
#     user = None
#     request = None
    
    
#     # Проверить токен по грпс 
#     # Создать пользователя если нету
#     # Проверить пермишены (базовая проверка)

    
#     checker = PermissionMapper()
#     try: 
#         checker.check_permissions(required, user, request)
#     except: 
#         raise PermissionError()
    
#     return user
    
    