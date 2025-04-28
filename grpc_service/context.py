from flask import g, current_app
from grpc_service.grpc_manager import GrpcChannelManager


from grpc_service.auth import auth_pb2_grpc
from grpc_service.permissions import permissions_pb2_grpc


async def get_grpc_context():
    """Получить или создать контекст gRPC для текущего запроса"""
    if 'grpc_manager' not in g:
        g.grpc_manager = GrpcChannelManager()
        await g.grpc_manager.__aenter__()

async def teardown_grpc_context(exc=None):
    """Закрыть соединения при завершении запроса"""
    if 'grpc_manager' in g:
        await g.grpc_manager.__aexit__(exc, None, None)
        g.pop('grpc_manager', None)


def get_auth_service() -> auth_pb2_grpc.AuthServiceStub:
    """Получить сервис аутентификации из контекста"""
    return g.grpc_manager.get_auth_stub()

def get_permissions_service() -> permissions_pb2_grpc.PermissionServiceStub:
    """Получить сервис разрешений из контекста"""
    return g.grpc_manager.get_permissions_stub()