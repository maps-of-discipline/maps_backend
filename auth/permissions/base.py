from flask import Request

from auth.models import Users


class Permission(str):
    pass

    def check(self, user: Users, request: Request) -> bool:
        return True




