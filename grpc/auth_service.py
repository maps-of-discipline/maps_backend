from grpc.dto.auth import UserData, TokenPayload
from grpc.auth import auth_pb2
from grpc.grpc_manager import get_auth_service

class AuthGRPCService:

    def __init__(self, auth_grpc_stub) -> None:
        self.stub = get_auth_service()

    async def get_payload(jwt: str) -> TokenPayload:
        pass
    
    async def get_user_data(self, jwt:str) -> UserData:
        pass