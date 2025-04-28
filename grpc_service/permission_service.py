import grpc
from typing import List
from grpc_service.permissions import permissions_pb2, permissions_pb2_grpc
from grpc_service.dto.permissions import Permission, CreatePermission
from config import GRPC_URL

class permissionGRPCService:
    
    def __init__(self) -> None:
        self.url = GRPC_URL
        self.channel = None
        self.stub = None

    def __enter__(self):
        self.channel = grpc.insecure_channel(self.url)
        self.stub = permissions_pb2_grpc.PermissionServiceStub(self.channel)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.channel:
            self.channel.close()

    def get_permissions(self, service:str) -> List[Permission]:
        request = permissions_pb2.GetPermissionsByServiceRequest(service_name=service)
        response = self.stub.GetPermissionsByService(request) 

        permissions: List[Permission] = [
            Permission(
                id= el.id,
                title= el.title,
                verbose_name= el.verbose_name,
            )
            for el in response
        ]
        return permissions
        

    def create_permissions(self, service_name: str, permission: CreatePermission) -> Permission:
        permission_create = permissions_pb2.CreatePermission(
            title=permission.title,
            verbose_name=permission.verbose_name,
        )
        
        request = permissions_pb2.CreateServicePermissionRequest(
            service_name= service_name,
            permission=permission_create,
        )

        response = self.stub.CreateServicePermission(request)
        response_permission = response.permission
        
        return Permission(
            id= response_permission.id,
            title= response_permission.title,
            verbose_name= response_permission.verbose_name,
        )

    def update_permissions(self, service_name: str, permission: Permission):
        permission_update = permissions_pb2.Permission(
            id= permission.id,
            title= permission.title,
            verbose_name= permission.verbose_name,
        )
        
        request = permissions_pb2.UpdateServicePermissionRequest(
            service_name= service_name,
            permission= permission_update,
        )

        response = self.stub.UpdateServicePermission(request)

        return response
    
    def delete_permissions(self, permission_id: str) -> None:
        request = permissions_pb2.DeleteServicePermissionRequest(id= permission_id)
        
        self.stub.DeleteServicePermission(request)

    def check_conn(self) -> bool:
        try:
            grpc.channel_ready_future(self.channel).result(timeout= 15)
            return True
        except grpc.FutureTimeoutError:
            return False    
        except AttributeError:
            return False