from grpc import aio
from functools import lru_cache
from typing import Dict
from config import GRPC_URL
import asyncio

from grpc_service.auth import auth_pb2_grpc
from grpc_service.permissions import permissions_pb2_grpc

class GrpcChannelManager:
    """Менеджер gRPC каналов с контекстным управлением"""
    
    def __init__(self):
        self.url = GRPC_URL
        self.channels: Dict[str, aio.Channel] = {}
        self.stubs: Dict[str, object] = {}

    async def __aenter__(self):
        await self._initialize_channels()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _initialize_channels(self) -> None:
        config = {
            "auth": auth_pb2_grpc.AuthServiceStub,
            "permissions": permissions_pb2_grpc.PermissionServiceStub,
        }
        
        for title, stub_class in config.items():
            channel = aio.insecure_channel(self.url)
            self.channels[title] = channel
            self.stubs[title] = stub_class(channel)

    async def close(self):
        """Закрыть все каналы"""
        for channel in self.channels.values():
            await channel.close()
        self.channels.clear()
        self.stubs.clear()

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
