import grpc_service
from grpc import aio
from functools import lru_cache
from typing import Dict
from config import GRPC_URL
import asyncio

from grpc_service.auth import auth_pb2_grpc
from grpc_service.permissions import permissions_pb2_grpc

class GrpcChannelManager:
    """Менеджер gRPC каналов"""
    
    def __init__(self):
        self.url = GRPC_URL
        self.channels: Dict[str, grpc_service.aio.Channel] = {}
        self.stubs: Dict[str, object] = {}  # Тип стаба может варьироваться

    async def initialize(self):
        if not self.channels:
            await self._initialize_channels()

    async def _initialize_channels(self) -> None:
        """Инициализация всех каналов"""
        config = {
            "auth": auth_pb2_grpc.AuthServiceStub,
            "permissions": permissions_pb2_grpc.PermissionServiceStub,
        }
        
        for title, stub_class in config.items():
            channel = aio.insecure_channel(self.url)
            self.channels[title] = channel
            self.stubs[title] = stub_class(channel)

    def get_auth_stub(self) -> auth_pb2_grpc.AuthServiceStub:
        """Получить стаб для сервиса аутентификации"""
        return self.stubs.get("auth")

    def get_permissions_stub(self) -> permissions_pb2_grpc.PermissionServiceStub:
        """Получить стаб для сервиса разрешений"""
        return self.stubs.get("permissions")

    async def check_connection_async(self) -> bool:
        """Проверяет доступность gRPC сервера"""
        if not self.channels:
            return False
        try:
            # Проверяем первый канал
            channel = next(iter(self.channels.values()))
            await asyncio.wait_for(channel.channel_ready(), timeout=2)
            return True
        except (asyncio.TimeoutError, aio.AioRpcError) as e:
            print(f"gRPC connection error: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

@lru_cache()
def get_channel_manager() -> GrpcChannelManager:
    """Получить экземпляр менеджера каналов без инициализации"""
    return GrpcChannelManager()

async def init_grpc_manager() -> GrpcChannelManager:
    #Асинхронная инициализация менеджера каналов
    manager = get_channel_manager()
    await manager.initialize()
    return manager

def get_auth_service() -> auth_pb2_grpc.AuthServiceStub:
    """Получить сервис аутентификации"""
    return get_channel_manager().get_auth_stub()

def get_permissions_service()  -> permissions_pb2_grpc.PermissionServiceStub:
    """Получить сервис разрешений"""
    return get_channel_manager().get_permissions_stub()