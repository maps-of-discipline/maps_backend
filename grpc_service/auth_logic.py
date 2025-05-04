from functools import wraps
from typing import List, Dict, Optional
import grpc
from flask import request, jsonify
from sqlalchemy.exc import SQLAlchemyError
from grpc_service.auth_service import AuthGRPCService
from grpc_service.permission_service import permissionGRPCService
from grpc_service.dto.auth import UserData
from auth.models import db, Users
from grpc_service.permissions import permissions_pb2
import werkzeug.exceptions as http_exceptions

class AuthError(Exception):
    """Базовое исключение для ошибок авторизации"""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code

class PermissionDeniedError(http_exceptions.Forbidden):
    # мб возвращать json
    """Ошибка доступа"""
    def __init__(self):
        super().__init__("Permission denied")

class AuthManager:
    def __init__(self):
        self.auth_service = AuthGRPCService()

    def _get_token_from_header(self) -> str:
        """Извлекает и валидирует токен из заголовка Authorization"""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthError("Missing or invalid Authorization header")
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
            raise AuthError(f"Database error: {str(e)}", 500)
        except grpc.RpcError as e:
            raise AuthError(f"Auth service error: {e.code()}", 500)

    # убрать все что не нужно
    def require(self, required_permissions: List[str] = list()):
        try:
            with self.auth_service as service:
                token = self._get_token_from_header()
                payload = service.get_payload(token)
                user = Users.query.get(payload.user_id)
                if not user:
                    user = self._create_user(service.get_user_data(token))

                if any([el not in payload.permissions for el in required_permissions]):
                    raise PermissionDeniedError()

                return user

        except grpc.RpcError as e:
            code = e.code()
            if code == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthError("Invalid token")
            raise AuthError(f"Auth service error: {code}", 500)

    # штука для валидации доп логики\