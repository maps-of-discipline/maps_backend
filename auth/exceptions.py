import werkzeug.exceptions as http_exceptions

class AuthError(http_exceptions.HTTPException):
    def __init__(self, description="Invalid token", status_code=401):
        super().__init__(description=description)
        self.code = status_code

class PermissionDeniedError(http_exceptions.Forbidden):
    """Ошибка доступа"""
    def __init__(self, description="Permission denied"):
        super().__init__(description=description)