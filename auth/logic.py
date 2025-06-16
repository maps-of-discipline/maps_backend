import uuid
from functools import wraps
from time import time
from typing import Any

import jwt
import sqlalchemy.exc
from flask import make_response, request, current_app, g # Added current_app and g

from auth.models import Users, Token
from maps.models import db, AupInfo

from config import SECRET_KEY, ACCESS_TOKEN_LIFETIME, REFRESH_TOKEN_LIFETIME

import logging
logger = logging.getLogger(__name__)

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
    logger.debug(f"Encoding token with SECRET_KEY: '{secret_for_encoding}'")
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
    logger.debug(f"Decoding token with SECRET_KEY: '{secret_for_decoding}'")
    try:
        payload = jwt.decode(
            jwt=jwt_token,
            key=secret_for_decoding,
            algorithms=['HS256'],
            # Verify expiration
            options={"verify_exp": True}
        )
        logger.debug(f"Token decoded successfully. Payload user_id: {payload.get('user_id')}")
        return payload, True

    except jwt.ExpiredSignatureError:
        logger.debug("Token verification failed: Expired")
        return None, False
    except jwt.InvalidSignatureError:
        logger.debug("Token verification failed: Invalid Signature")
        return None, False
    except jwt.DecodeError:
        logger.debug("Token verification failed: Decode Error")
        return None, False
    except Exception as e:
        logger.debug(f"Token verification failed: Unexpected error {e}")
        return None, False


def verify_refresh_token(token: str) -> bool:
    current_token = Token.query.filter_by(refresh_token=token).first()
    return current_token and current_token.refresh_token == token and current_token.ttl > time()


# Extracts token, verifies it, and sets user in g
def _verify_token_and_set_user(request_obj):
    auth_header = request_obj.headers.get("Authorization")
    g.user = None
    g.auth_payload = None

    if not auth_header or not auth_header.startswith("Bearer "):
        logger.debug("_verify_token: No/Invalid Bearer token format.")
        return False

    token = auth_header.split(" ")[1]

    payload, verify_result = verify_jwt_token(token)
    logger.debug(f"_verify_token: verify_jwt_token result: payload is None? {payload is None}, verify_result: {verify_result}")

    if payload and verify_result:
        user = Users.query.get(payload.get('user_id'))
        if user:
            g.user = user
            g.auth_payload = payload
            logger.debug(f"_verify_token: Verification successful for user_id {g.user.id_user}. User set in g.")
            return True
        else:
            logger.debug(f"_verify_token: User ID {payload.get('user_id')} from token not found in DB.")
            return False
    else:
        logger.debug("_verify_token: Token verification failed.")
        return False


# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return make_response('Token is missing or invalid format!', 401)

        token = auth_header.split(" ")[1] # Extract token

        payload, verify_result = verify_jwt_token(token)

        if not verify_result:
            return make_response('Token is invalid!', 401)

        # For consistency, consider using g.user/g.auth_payload if set by a prior filter
        user = Users.query.filter_by(id_user=payload['user_id']).one_or_none()

        if not user:
             logger.debug(f"login_required: User ID {payload.get('user_id')} from token not found in DB.")
             return make_response('Token is invalid!', 401) # User from token not found

        # Redundant user.approved check if approved_required decorator is used.
        # if not user.approved:
        #     return make_response('User is not approved', 403)

        # Set user/payload in g for other decorators (e.g., approved_required)
        g.user = user
        g.auth_payload = payload
        logger.debug(f"login_required: Access granted for user {g.user.id_user}. Proceeding.")

        result = f(*args, **kwargs)
        return result
    return decorated_function


# Approval required decorator (use AFTER @login_required)
def approved_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user') or g.user is None or not hasattr(g, 'auth_payload') or g.auth_payload is None:
            logger.debug("approved_required: g.user/g.auth_payload not set! Ensure @login_required runs first. Returning 401.")
            # login_required should handle initial auth failure. This indicates decorator order issue.
            return make_response('Authentication required', 401)

        if not g.auth_payload.get('approved_lk', False):
            logger.debug(f"approved_required: User {g.user.id_user} not approved (approved_lk is {g.auth_payload.get('approved_lk')}). Returning 403.")
            return make_response('User approval required', 403)

        logger.debug(f"approved_required: User {g.user.id_user} approved. Proceeding.")
        return f(*args, **kwargs)
    return decorated_function


# Admin only decorator (use AFTER @login_required)
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user') or g.user is None or not hasattr(g, 'auth_payload') or g.auth_payload is None:
            logger.debug("admin_only: g.user/g.auth_payload not set! Ensure @login_required runs first. Returning 401.")
            return make_response('Authentication required', 401)

        roles = g.auth_payload.get('roles', [])
        if not any(role.get('id') == 1 for role in roles): # Check for admin role (ID 1)
            logger.debug(f"admin_only: User {g.user.id_user} does not have admin role. Roles: {roles}. Returning 403.")
            return make_response('Admin role required', 403)

        logger.debug(f"admin_only: User {g.user.id_user} has admin role. Proceeding.")
        result = f(*args, **kwargs)
        return result
    return decorated_function


# AUP required decorator (use AFTER @login_required)
def aup_require(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user') or g.user is None or not hasattr(g, 'auth_payload') or g.auth_payload is None:
            logger.debug("aup_require: g.user/g.auth_payload not set! Ensure @login_required runs first. Returning 401.")
            return make_response('Authentication required', 401)

        user = g.user
        payload = g.auth_payload

        aup_header = request.headers.get('Aup')
        if not aup_header:
            return make_response('Aup header is required', 400)

        try:
            # Ensure Aup header is valid number if needed
            aup_info: AupInfo = AupInfo.query.filter_by(num_aup=aup_header).one()
        except sqlalchemy.exc.NoResultFound:
            return make_response(f"No such aup found: {aup_header}", 404)
        except ValueError:
            return make_response('Invalid Aup header format', 400)

        user_roles_ids = [role.get('id') for role in payload.get('roles', [])]

        if 2 in user_roles_ids: # faculty role
            # Use faculties from payload or query user.faculties
            user_faculties = payload.get('faculties', [faq.id_faculty for faq in user.faculties])
            if aup_info.id_faculty not in user_faculties:
                logger.debug(f"aup_require: User {user.id_user} (Faculty) forbidden for AUP {aup_header}. AUP Faculty: {aup_info.id_faculty}, User Faculties: {user_faculties}")
                return make_response('Forbidden for this faculty', 403)

        elif 3 in user_roles_ids: # department role
            user_department_id = payload.get('department_id', user.department_id)
            if not user_department_id or aup_info.id_department != user_department_id:
                logger.debug(f"aup_require: User {user.id_user} (Department) forbidden for AUP {aup_header}. AUP Department: {aup_info.id_department}, User Department: {user_department_id}")
                return make_response('Forbidden for this department', 403)
        # Admin role (1) implicitly has access

        logger.debug(f"aup_require: User {user.id_user} access granted for AUP {aup_header}.")
        result = f(*args, **kwargs)
        return result
    return decorated_function

