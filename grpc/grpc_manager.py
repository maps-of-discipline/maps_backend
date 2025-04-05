import grpc
from functools import lru_cache
from typing import Dict
from config import GRPC_URL

from src.grpc.auth import auth_pb2_grpc
from src.grpc.permissions import permissions_pb2_grpc

class GrpcChannelManager:
    """Менеджер gRPC каналов"""
    
    def __init__(self):
        self.url = GRPC_URL
        self.channels: Dict[str, grpc.aio.Channel] = {}
        self.stubs: Dict[str, object] = {}  # Тип стаба может варьироваться
        
        self._initialize_channels()

    def _initialize_channels(self) -> None:
        """Инициализация всех каналов"""
        config = {
            "auth": auth_pb2_grpc.AuthServiceStub,
            "permissions": permissions_pb2_grpc.PermissionServiceStub,
        }
        
        for title, stub_class in config.items():
            channel = grpc.aio.insecure_channel(self.url)
            self.channels[title] = channel
            self.stubs[title] = stub_class(channel)

    def get_auth_stub(self) -> auth_pb2_grpc.AuthServiceStub:
        """Получить стаб для сервиса аутентификации"""
        return self.stubs.get("auth")

    def get_permissions_stub(self) -> permissions_pb2_grpc.PermissionServiceStub:
        """Получить стаб для сервиса разрешений"""
        return self.stubs.get("permissions")

@lru_cache()
def get_channel_manager() -> GrpcChannelManager:
    """Получить экземпляр менеджера каналов"""
    return GrpcChannelManager()

def get_auth_service() -> auth_pb2_grpc.AuthServiceStub:
    """Получить сервис аутентификации"""
    return get_channel_manager().get_auth_stub()

def get_permissions_service()  -> permissions_pb2_grpc.PermissionServiceStub:
    """Получить сервис разрешений"""
    return get_channel_manager().get_permissions_stub()