from typing import List
import grpc
from flask import request
from sqlalchemy.exc import SQLAlchemyError
from grpc_service.auth_service import AuthGRPCService
from auth.models import db, Users
from auth.permission_mapper import PermissionMapper
from utils.exceptions import (
    PermissionsDeniedException,
    BadRequestException,
    UnauthorizedException,
)


class AuthManager:
    def __init__(self):
        self.auth_service = AuthGRPCService()
        self._permissions_checker = PermissionMapper()

    def _get_token_from_header(self) -> str:
        """Извлекает и валидирует токен из заголовка Authorization"""

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise BadRequestException("Missing or invalid Authorization header")

        return auth_header.replace("Bearer ", "").strip()

    def _create_user(self, user_data) -> Users:
        """Получает или создает пользователя в БД"""
        try:
            user = Users(
                id=user_data.id,
                login=user_data.login,
                email=user_data.email,
            )
            db.session.add(user)
            db.session.commit()

            return user

        except SQLAlchemyError as e:
            db.session.rollback()
            raise BadRequestException(f"Database error: {str(e)}")
        except grpc.RpcError as e:
            raise BadRequestException(f"Auth service error: {e.code()}")

    def require(self, required_permissions: List[str] = list()):
        try:
            with self.auth_service as service:
                token = self._get_token_from_header()
                payload = service.get_payload(token)
                user = Users.query.get(payload.user_id)
                if not user:
                    user = self._create_user(service.get_user_data(token))

                if any([el not in payload.permissions for el in required_permissions]):
                    raise PermissionsDeniedException()

                self._permissions_checker.check_permissions(
                    required_permissions, user, request
                )

                return user

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise UnauthorizedException("Invalid token")
            else:
                raise BadRequestException(f"Auth service error: {e.code()}")
