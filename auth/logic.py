import uuid
from functools import wraps
from time import time
from typing import Any

import jwt
import sqlalchemy.exc
from flask import make_response

from auth.models import Users
from maps.models import db, AupInfo

def login_required(request):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'Authorization' not in request.headers or request.headers['Authorization'] is None:
                return make_response('Authorization header is required', 401)

            #payload, verify_result = verify_jwt_token(request.headers["Authorization"])
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
            #payload, verify_result = verify_jwt_token(request.headers["Authorization"])

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

            #payload, verify_result = verify_jwt_token(request.headers["Authorization"])
            if not payload or not verify_result:
                return make_response('Authorization token is invalid', 401)

            if 1 not in payload['roles']:
                return make_response('Forbidden', 403)

            result = f(*args, **kwargs)
            return result

        return decorated_function

    return decorator
