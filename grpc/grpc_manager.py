import grpc
from functools import lru_cache
from config import GRPC_URL

from src.grpc.auth import auth_pb2_grpc
from src.grpc.permissions import permissions_pb2_grpc

class GrpcChannelManager:
    #Менеджер gRPC каналов

    def __init__(self):
        self.url = GRPC_URL
        self.channels: Dict[str, grpc.aio.Channel] = {}
        self.stubs = {}

        self._initialize_channels()

    def _initilize_chanels(self):
        """Инициализация всех каналов"""
        config = {
            "auth": auth_pb2_grpc.AuthServiceStub,
            "permissions": permissions_pb2_grpc.PermissionServiceStub,
        }
        
        for title, stub in config.items():
            channel = grpc.aio.insecure_channel(self.url)

            self.channels[title] = channel

            if title == "auth":
                self.stubs[title] = stub(channel)
            elif title == "permissions":
                self.stubs[title] = stub(channel)


    def get_auth_stub(self):
        # Получить стаб для сервиса пользователей
        return self.stubs.get("auth")

    def get_permissions_stub(self):
        #Получить стаб для сервиса продуктов
        return self.stubs.get("permissions")
    
@lru_cache()
def get_channel_manager():
    return GrpcChannelManager()


def get_auth_service():
    return get_channel_manager().get_auth_stub()


def get_permissions_service():
    return get_channel_manager().get_permissions_stub()
