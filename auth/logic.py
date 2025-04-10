import uuid
from functools import wraps
from time import time
from typing import Any

import jwt
import sqlalchemy.exc
# Add g and current_app imports
from flask import make_response, g, current_app, request as flask_request

from auth.models import Users, Token
from maps.models import db, AupInfo

# Get config values from current_app
ACCESS_TOKEN_LIFETIME = 3600  # Default value
REFRESH_TOKEN_LIFETIME = 86400*30  # Default value

def get_access_token(user_id) -> str:
    user: Users = Users.query.filter_by(id_user=user_id).first()

    can_edit = []

    if 2 in [role.id_role for role in user.roles]:  # faculty
        for faq in user.faculties:
            aup_infos = AupInfo.query.filter_by(id_faculty=faq.id_faculty).all()
            for aup in aup_infos:
                can_edit.append(aup.num_aup)

    elif 3 in [role.id_role for role in user.roles]:  # department
        aup_infos = AupInfo.query.filter_by(id_department=user.department_id)
        for aup in aup_infos:
            can_edit.append(aup.num_aup)

    roles = [{
        "id": role.id_role,
        "name": role.name_role,
    } for role in user.roles]

    payload = {
        'user_id': user.id_user,
        'name': user.name,
        'login': user.login,
        'roles': roles,
        'department_id': user.department_id,
        'faculties': [faq.id_faculty for faq in user.faculties],
        'exp': round(time()) + ACCESS_TOKEN_LIFETIME,
        'can_edit': can_edit,
        'approved_lk': bool(user.approved_lk)
    }

    secret_for_encoding = current_app.config['SECRET_KEY']
    print(f"DEBUG: Encoding token with SECRET_KEY: '{secret_for_encoding}'") 
    return str(jwt.encode(payload, secret_for_encoding, algorithm='HS256'))


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

def verify_jwt_token(jwt_token) -> tuple[Any, bool]:
    secret_for_decoding = current_app.config['SECRET_KEY']
    print(f"DEBUG: Decoding token with SECRET_KEY: '{secret_for_decoding}'")
    try:
        payload = jwt.decode(
            jwt=jwt_token,
            key=secret_for_decoding,
            algorithms=['HS256'],
            # Verify expiration when decoding
            options={"verify_exp": True}
        )
        print(f"DEBUG: Token decoded successfully. Payload user_id: {payload.get('user_id')}")
        return payload, True

    except jwt.ExpiredSignatureError:
        print("DEBUG: Token verification failed: Expired")
        return None, False
    except jwt.InvalidSignatureError:
        print("DEBUG: Token verification failed: Invalid Signature")
        return None, False
    except jwt.DecodeError:
        print("DEBUG: Token verification failed: Decode Error")
        return None, False
    except Exception as e:
        print(f"DEBUG: Token verification failed: Unexpected error {e}")
        return None, False


def verify_refresh_token(token: str) -> bool:
    current_token = Token.query.filter_by(refresh_token=token).first()
    return current_token and current_token.refresh_token == token and current_token.ttl > time()


# This function extracts and verifies the token, and sets the user in g
def _verify_token_and_set_user(request_obj):
    auth_header = request_obj.headers.get("Authorization")
    g.user = None  # Reset user for each request
    g.auth_payload = None

    if not auth_header or not auth_header.startswith("Bearer "):
        print("DEBUG: _verify_token: No/Invalid Bearer token format.")
        return False

    token = auth_header.split(" ")[1]

    payload, verify_result = verify_jwt_token(token)
    print(f"DEBUG: _verify_token: verify_jwt_token result: payload is None? {payload is None}, verify_result: {verify_result}")

    if payload and verify_result:
        # Find user in DB by ID from token
        user = Users.query.get(payload.get('user_id'))
        if user:
            g.user = user  # Save user object
            g.auth_payload = payload  # Save payload
            print(f"DEBUG: _verify_token: Verification successful for user_id {g.user.id_user}. User set in g.")
            return True
        else:
            print(f"DEBUG: _verify_token: User ID {payload.get('user_id')} from token not found in DB.")
            return False
    else:
        print("DEBUG: _verify_token: Token verification failed.")
        return False


# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _verify_token_and_set_user(flask_request):
            print("DEBUG: login_required: Verification failed. Returning 401.")
            return make_response('Invalid or missing Authorization token', 401)
        # If _verify_token_and_set_user returned True, then g.user is set
        print(f"DEBUG: login_required: Access granted for user {g.user.id_user}. Proceeding.")
        return f(*args, **kwargs)
    return decorated_function


# Approval required decorator
def approved_required(f):
    # This decorator should be used AFTER @login_required
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user') or g.user is None or not hasattr(g, 'auth_payload') or g.auth_payload is None:
            print("DEBUG: approved_required: g.user or g.auth_payload not set! Misconfigured decorators? Returning 401.")
            return make_response('Authentication required', 401)

        if not g.auth_payload.get('approved_lk', False):
            print(f"DEBUG: approved_required: User {g.user.id_user} not approved (approved_lk is {g.auth_payload.get('approved_lk')}). Returning 403.")
            return make_response('User approval required', 403)

        print(f"DEBUG: approved_required: User {g.user.id_user} approved. Proceeding.")
        return f(*args, **kwargs)
    return decorated_function


# Admin only decorator
def admin_only(f):
    # This decorator should be used AFTER @login_required
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user') or g.user is None:
            return make_response('Authentication required', 401)

        if not any(role.id_role == 1 for role in g.user.roles):
            print(f"DEBUG: admin_only: User {g.user.id_user} does not have 'admin' role. Returning 403.")
            return make_response('Admin privileges required', 403)

        print(f"DEBUG: admin_only: User {g.user.id_user} has 'admin' role. Proceeding.")
        return f(*args, **kwargs)
    return decorated_function


def aup_require(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user') or g.user is None:
            return make_response('Authentication required', 401)

        if not ('Aup' in flask_request.headers and flask_request.headers['Aup']):
            return make_response('aup is required', 401)
        try:
            aup_info: AupInfo = AupInfo.query.filter_by(num_aup=flask_request.headers['Aup']).one()
        except sqlalchemy.exc.NoResultFound:
            return make_response("No such aup found", 404)

        if 2 in [role.id_role for role in g.user.roles]:  # faculty
            if aup_info.id_faculty not in [faq.id_faculty for faq in g.user.faculties]:
                return make_response('Forbidden', 403)

        elif 3 in [role.id_role for role in g.user.roles]:  # department
            if not g.user.department_id or aup_info.id_department != g.user.department_id:
                return make_response('Forbidden', 403)

        return f(*args, **kwargs)
    return decorated_function
