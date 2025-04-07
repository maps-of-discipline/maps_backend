from grpc.dto.auth import UserData, TokenPayload
from grpc.auth import auth_pb2
from grpc.grpc_manager import get_auth_service

class AuthGRPCService:

    def __init__(self, auth_grpc_stub) -> None:
        self.stub = get_auth_service()

    async def get_payload(jwt: str) -> TokenPayload:
        request = auth_pb2.GetPayloadRequest(token=jwt)

        response = self.stub.GetPayload(request)

        return TokenPayload(
            user_id=response.user_id,
            role=response.role,
            expires_at=response.expires_at,
            service_name=response.service_name,
            permissions=response.permissions,
        )
    
    async def get_user_data(self, jwt:str) -> UserData:
        request = auth_pb2.GetUserRequest(jwt)

        response = self.stub.GetUser(request)

        return UserData(
            id=response.id,
            external_id=response.external_id,
            role=response.role,
            external_role=response.external_role,
            name=response.name,
            surname=response.surname,
            patronymic=response.patronymic,
            email=response.email,
            faculty=response.faculty,
            login=response.login,
            last_login=response.last_login,
            created_at=response.created_at,)