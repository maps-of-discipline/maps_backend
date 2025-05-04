from typing import Dict
from grpc_service.dto.auth import TokenPayload

# на пермишен накидываем код
# валидируем данные там всякие
# 
class PermissionMapper:
    def __init__(self):
        pass

    def check(self, permission: str, payload: TokenPayload ):
        pass