import uuid
from functools import wraps
from time import time
from typing import Any

import jwt
import sqlalchemy.exc
from flask import make_response

from auth.models import Users#, Token
from maps.models import db, AupInfo

from config import SECRET_KEY, ACCESS_TOKEN_LIFETIME, REFRESH_TOKEN_LIFETIME

def get_access_token(user_id) -> str:
    user: Users = Users.query.filter_by(id_user=user_id).first()

    can_edit = []

    if 2 in [role.id_role for role in user.roles]:  # faculty
        for faq in user.faculties:
            aup_infos = AupInfo.query.filter_by(id_faculty=faq.id_faculty).all()
            for aup in aup_infos:
                can_edit.append(aup.num_aup)

    elif 3 in [role.id_role for role in user.roles] :  # department
        aup_infos = AupInfo.query.filter_by(id_department=user.department_id)
        for aup in aup_infos:
            can_edit.append(aup.num_aup)

    payload = {
        'user_id': user.id_user,
        'login': user.login,
        'roles': [role.id_role for role in user.roles],
        'department_id': user.department_id,
        'faculties': [faq.id_faculty for faq in user.faculties],
        'exp': round(time()) + ACCESS_TOKEN_LIFETIME,
        'can_edit': can_edit
    }

    return str(jwt.encode(payload, SECRET_KEY, algorithm='HS256'))


def get_refresh_token(user_id: int, user_agent: str) -> str:
    refresh_token = str(uuid.uuid4())
    lifetime = round(time()) + REFRESH_TOKEN_LIFETIME

    '''current_tokens = Token.query.filter_by(user_id=user_id).all()

    for token in current_tokens:
        if token.ttl < time() or token.user_agent == user_agent:
            db.session.delete(token)

    db.session.add(Token(
        user_id=user_id,
        refresh_token=refresh_token,
        user_agent=user_agent,
        ttl=lifetime)
    )
    db.session.commit()
'''
    return refresh_token


def verify_jwt_token(jwt_token) -> tuple[Any, bool] | tuple[None, bool]:
    try:
        return jwt.decode(
            jwt=jwt_token,
            key=SECRET_KEY,
            algorithms=['HS256'],
            options={"verify_exp": False}
        ), True

    except jwt.exceptions.InvalidSignatureError:
        return None, False
    except jwt.exceptions.DecodeError:
        return None, False


def verify_refresh_token(token: str) -> bool:
    current_token = "sdfs"#Token.query.filter_by(refresh_token=token).first()
    return current_token and current_token.refresh_token == token and current_token.ttl > time()


def login_required(request):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'Authorization' not in request.headers or request.headers['Authorization'] is None:
                return make_response('Authorization header is required', 401)

            payload, verify_result = verify_jwt_token(request.headers["Authorization"])
            if not payload or not verify_result:
                return make_response('Authorization token is invalid', 401)

            result = f(*args, **kwargs)
            return result

        return decorated_function

    return decorator


def aup_require(request):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            payload, verify_result = verify_jwt_token(request.headers["Authorization"])

            user = Users.query.filter_by(id_user=payload['user_id']).one()
            if not ('Aup' in request.headers and request.headers['Aup']):
                return make_response('aup is required', 401)
            try:
                aup_info: AupInfo = AupInfo.query.filter_by(num_aup=request.headers['Aup']).one()
            except sqlalchemy.exc.NoResultFound:
                return make_response("No such aup found", 404)

            if 2 in payload['roles']:
                if aup_info.id_faculty not in [faq.id_faculty for faq in user.faculties]:
                    return make_response('Forbidden', 403)

            elif 3 in payload['roles']:
                if not user.department_id or aup_info.id_department != user.department_id:
                    return make_response('Forbidden', 403)

            result = f(*args, **kwargs)
            return result

        return decorated_function

    return decorator


def admin_only(request):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'Authorization' not in request.headers or request.headers['Authorization'] is None:
                return make_response('Authorization header is required', 401)

            payload, verify_result = verify_jwt_token(request.headers["Authorization"])
            if not payload or not verify_result:
                return make_response('Authorization token is invalid', 401)

            if 1 not in payload['roles']:
                return make_response('Forbidden', 403)

            result = f(*args, **kwargs)
            return result

        return decorated_function

    return decorator
