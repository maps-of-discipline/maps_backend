from config import GRPC_URL
import grpc
from grpc_service.dto.auth import UserData, TokenPayload
from grpc_service.auth import auth_pb2, auth_pb2_grpc
from utils.exceptions import BadRequestException, UnauthorizedException


class AuthGRPCService:
    def __init__(self) -> None:
        self.url = GRPC_URL
        self.channel = None
        self.stub = None

    def __enter__(self):
        self.channel = grpc.insecure_channel(self.url)
        self.stub = auth_pb2_grpc.AuthServiceStub(self.channel)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.channel:
            self.channel.close()

    def get_payload(self, jwt: str) -> TokenPayload:
        try:
            request = auth_pb2.GetPayloadRequest(token=jwt)

            response = self.stub.GetPayload(request)

            return TokenPayload(
                user_id=response.user_id,
                role=response.role,
                expires_at=response.expires_at,
                service_name=response.service_name,
                permissions=response.permissions,
            )
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise UnauthorizedException("Invalid token")
            else:
                raise BadRequestException(f"Auth service error: {e.code()}")

    def get_user_data(self, jwt: str) -> UserData:
        try:
            request = auth_pb2.GetUserRequest(token=jwt)

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
                created_at=response.created_at,
            )
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise UnauthorizedException("Invalid token")
            else:
                raise BadRequestException(f"Auth service error: {e.code()}")

    def check_conn(self) -> bool:
        try:
            grpc.channel_ready_future(self.channel).result(timeout=15)
            return True
        except grpc.FutureTimeoutError:
            return False
        except AttributeError:
            return False

