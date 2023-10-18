from flask import make_response

from config import SECRET_KEY
from models import Token, Users, AupInfo, db

from time import time, sleep
import jwt
import uuid
from functools import wraps


ACCESS_TOKEN_LIFETIME = 3600    # 1 hour in seconds
REFRESH_TOKEN_LIFETIME = 7*24*3600      # 7 days in seconds


def get_access_token(user_id) -> str:
    user = Users.query.filter_by(id_user=user_id).first()
    payload = {
        "user_id": user.id_user,
        'role_id': user.id_role,
        'faculties': [faq.id_faculty for faq in user.faculties],
        'exp': round(time()) + ACCESS_TOKEN_LIFETIME
    }

    return str(jwt.encode(payload, SECRET_KEY, algorithm='HS256'))


def get_refresh_token(user_id: int, user_agent: str) -> str:
    refresh_token = str(uuid.uuid4())
    lifetime = round(time()) + REFRESH_TOKEN_LIFETIME

    current_tokens = Token.query.filter_by(user_id=user_id).all()

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

    return refresh_token


def verify_jwt_token(jwt_token) -> dict | None:
    try:
        return jwt.decode(
            jwt=jwt_token,
            key=SECRET_KEY,
            algorithms=['HS256'],
            options = {
                "verify_exp": False
            }
        ), True

    except jwt.exceptions.InvalidSignatureError:
        return None, False
    except jwt.exceptions.DecodeError:
        return None, False


def verify_refresh_token(token: str) -> bool:
    current_token = Token.query.filter_by(refresh_token=token).one()
    print(f'{current_token=}')
    return current_token.refresh_token == token and current_token.ttl > time()


def login_required(request):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'Authorization' not in request.headers or request.headers['Authorization'] is None:
                return make_response('Authorization header is required', 401)

            payload, verify_result = verify_jwt_token(request.headers["Authorization"])
            if not payload or not verify_result:
                return make_response('Authorization token is invalid', 401)

            user = Users.query.filter_by(id_user=payload['user_id']).one()
            aup_info: AupInfo = AupInfo.query.filter_by(num_aup=kwargs['aup']).one()

            if payload['role_id'] == 2:
                if aup_info.id_faculty not in [faq.id_faculty for faq in user.faculties]:
                    return make_response('Forbidden', 403)

            elif payload['role_id'] == 3:
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

            if payload['role_id'] != 1:
                return make_response('Forbidden', 403)

            result = f(*args, **kwargs)
            return result
        return decorated_function
    return decorator



