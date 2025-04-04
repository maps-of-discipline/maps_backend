from grpc.permissions import permissions_pb2
from grpc.dto.permissions import Permission, CreatePermission
from grpc.grpc_manager import get_permissions_service

class permissionGRPCService:
    
    def __init__(self) -> None:
        self.stub = get_permissions_service()

    def get_permission(self, service:str) -> list[Permission]:
        pass

    def update_permission(self, service_name: str, permission: str) -> Permission:
        pass    

    def update_permission(self, service_name: str, permission: str) -> None:
        pass