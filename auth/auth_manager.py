from functools import wraps
import inspect
import grpc
from flask import request
from sqlalchemy.exc import SQLAlchemyError
from auth.enum import PermissionsEnum
from grpc_service.auth_service import AuthGRPCService
from auth.models import db, Users
from utils.exceptions import (
    PermissionsDeniedException,
    BadRequestException,
    UnauthorizedException,
)


def require(*required: tuple[PermissionsEnum, ...] | PermissionsEnum):
    """Authentication decorator for route handlers.

    Args:
        *required: Variable length argument of permissions. Each argument can be either:
            - A single PermissionsEnum value
            - A tuple of PermissionsEnum values (acts as OR condition)

    This decorator validates the user's authentication token and checks if the user
    has the required permissions to access the endpoint. It also automatically injects
    the authenticated user object into the decorated function's parameters if there is
    a parameter annotated with the Users type.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user: Users = AuthManager().require(list(required))

            sig = inspect.signature(f)
            for param_name, param in sig.parameters.items():
                if param.annotation == Users:
                    kwargs[param_name] = user
                    break

            return f(*args, **kwargs)

        return decorated

    return decorator


class AuthManager:
    def __init__(self):
        self.auth_service = AuthGRPCService()

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

    def require(
        self, required: list[tuple[PermissionsEnum, ...] | PermissionsEnum] = list()
    ):
        with self.auth_service as service:
            token = self._get_token_from_header()
            payload = service.get_payload(token)
            user = Users.query.get(payload.user_id)
            if not user:
                user = self._create_user(service.get_user_data(token))
            for permission in required:
                if not isinstance(permission, tuple):
                    if permission not in payload.permissions or not permission.check(
                        user, request
                    ):
                        raise PermissionsDeniedException()

                if isinstance(permission, tuple) and not any(
                    el in payload.permissions and el.check(user, request)
                    for el in permission
                ):
                    raise PermissionsDeniedException()

            return user
