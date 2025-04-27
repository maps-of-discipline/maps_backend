from typing import Dict
from grpc_service.dto.auth import TokenPayload

class PermissionMapper:
    def __init__(self):
        pass

    def check(self, permission: str, payload: TokenPayload ):
        pass