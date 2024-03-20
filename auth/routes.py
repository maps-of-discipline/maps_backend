import json

from flask import Blueprint, make_response, request

from auth.logic import verify_jwt_token, verify_refresh_token, get_access_token, get_refresh_token
from auth.models import Users
from .cli import register_commands

auth = Blueprint("auth", __name__, url_prefix='/api')
register_commands(auth)


@auth.route('/user/<int:user_id>')
def get_user_info(user_id):
    user = Users.query.filter_by(id_user=user_id).first()
    return make_response(json.dumps({
        'id': user.id_user,
        'login': user.login,
        'role': user.id_role,
        'department': user.department_id
    }, sort_keys=False))


@auth.route('/refresh', methods=['POST'])
def refresh_view():
    request_data = request.get_json()

    if "access" not in request_data:
        return make_response("Access token required", 401)

    if "refresh" not in request_data:
        return make_response("Refresh token required", 401)

    access = request_data['access']

    payload, verify_result = verify_jwt_token(access)

    if not payload:
        return make_response("Invalid access token", 401)

    if verify_refresh_token(request_data['refresh']):
        response = {
            'access': get_access_token(payload['user_id']),
            'refresh': get_refresh_token(payload['user_id'], request.headers['User-Agent']),
        }

        return make_response(json.dumps(response), 200)
    else:
        return make_response('Refresh token lifetime expired', 401)


@auth.route("/login", methods=['POST'])
def login():
    request_data = request.get_json()

    if 'username' not in request_data:
        return make_response("Username is required", 401)

    if 'password' not in request_data:
        return make_response("Password is required", 401)

    user = Users.query.filter_by(login=request_data['username']).first()

    if not user:
        return make_response("No such user", 400)  # 400?

    if not user.check_password(request_data['password']):
        return make_response('Incorrect password', 400)

    response = {
        'access': get_access_token(user.id_user),
        'refresh': get_refresh_token(user.id_user, request.headers['User-Agent']),
    }

    return make_response(json.dumps(response, ensure_ascii=False), 200)
