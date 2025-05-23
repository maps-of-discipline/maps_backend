class HttpException(Exception):
    status: int = 400

    def __init__(self, message: str):
        super().__init__(message)


class BadRequestException(HttpException):
    status: int = 400

    def __init__(self, message: str = "Bad request"):
        super().__init__(message)


class UnauthorizedException(HttpException):
    status: int = 401

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message)


class PermissionsDeniedException(HttpException):
    status: int = 403

    def __init__(self, message: str = "Permissions denied"):
        super().__init__(message)


class EntityNotFoundException(HttpException):
    status: int = 404

    def __init__(self, entity: str):
        super().__init__(f"{entity} not exists")

class MethodNotAllowed(HttpException):
    status: int = 405
    
    def __init__(self, message: str = "Method Not Allowed"):
        super().__init__(message)