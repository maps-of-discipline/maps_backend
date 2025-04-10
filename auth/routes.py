import json
import time
import secrets
import requests
from flask import Blueprint, make_response, request, jsonify, url_for, current_app
from flask_mail import Message
from pprint import pprint

# Import the new decorators for protected endpoints
from auth.logic import verify_jwt_token, verify_refresh_token, get_access_token, get_refresh_token, login_required, approved_required
from auth.models import Users, Roles
from cabinet.models import StudyGroups
from maps.models import db
from .cli import register_commands

auth = Blueprint("auth", __name__, url_prefix='/api')
register_commands(auth)

PASSWORD_RESET_TOKEN_EXPIRATION = 3600 * 24

# Now protected with @login_required and @approved_required
@auth.route('/user/<int:user_id>')
@login_required  # New decorator: requires a valid authenticated user
@approved_required  # New decorator: requires the user to be approved
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

    if 'login' not in request_data:
        print("Login key missing, returning 401/400")
        return make_response("Login is required", 400)

    if 'password' not in request_data:
        print("Password key missing, returning 401/400")
        return make_response("Password is required", 400)

    user = Users.query.filter_by(login=request_data['login']).first()

    if not user:
        print("User not found, returning 400")
        return make_response("No such user", 400)

    password_correct = user.check_password(request_data['password'])

    if not password_correct:
        print("Incorrect password, returning 400")
        return make_response('Incorrect password', 400)

    response = {
        'access': get_access_token(user.id_user),
        'refresh': get_refresh_token(user.id_user, request.headers.get('User-Agent', 'Unknown')),
    }

    print(f"Login successful for user {user.id_user}, returning 200")
    return make_response(json.dumps(response, ensure_ascii=False), 200)


password_reset_tokens = {}


@auth.route('/request-reset', methods=['POST'])
def request_reset():
    # Clean expired tokens
    for token, token_data in list(password_reset_tokens.items()):
        if token_data['ttl'] < time.time():
            password_reset_tokens.pop(token)

    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({"error": "Invalid email"}), 400

    user: Users = Users.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 400

    reset_token = secrets.token_urlsafe(16)
    password_reset_tokens[reset_token] = {
        "user_id": user.id_user,
        "ttl": PASSWORD_RESET_TOKEN_EXPIRATION + round(time.time())
    }

    reset_url = url_for('auth.reset_with_token', token=reset_token, _external=True)
    msg = Message("Password Reset", recipients=[email])
    msg.body = f"To reset your password, visit the following link: {reset_url}"

    current_app.extensions['mail'].send(msg)
    print(password_reset_tokens)
    return jsonify({"message": "Instructions to reset your password have been sent to your email."}), 200


@auth.route('/reset-password/<token>', methods=['POST'])
def reset_with_token(token):
    pprint(token)
    if not token or token not in password_reset_tokens:
        return jsonify({"error": "Invalid or expired token"}), 400

    token_data = password_reset_tokens.pop(token)
    user: Users = Users.query.get(token_data['user_id'])

    password = request.get_json()['password']
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({'result': 'ok'}), 200


@auth.route('/login/lk', methods=['POST'])
def lk_login():
    request_data = request.get_json()

    if 'username' not in request_data or 'password' not in request_data:
        return make_response("Username and password are required", 401)

    response = requests.post(current_app.config.get('LK_URL'), data={
        'ulogin': request_data['username'],
        'upassword': request_data['password'],
    }).json()

    res = requests.get(current_app.config.get('LK_URL'), params={'getUser': '', 'token': response['token']}).json()
    res = res['user']
    name = ' '.join([res['surname'], res['name'], res['patronymic']])
    email = res['email']

    user = Users.query.filter_by(login=request_data['username']).first()
    if not user:
        user = Users()
        user.auth_type = 'lk'
        user.lk_id = res['id']

        name_role = 'Guest'
        if res['user_status'] == 'stud':
            name_role = 'student'

        guest_role = Roles.query.filter_by(name_role=name_role).first()
        if guest_role:
            user.roles.append(guest_role)

    user.login = request_data['username']
    user.set_password(request_data['password'])
    user.name = name
    user.email = email

    db.session.add(user)
    db.session.commit()

    response = {
        'access': get_access_token(user.id_user),
        'refresh': get_refresh_token(user.id_user, request.headers['User-Agent']),
        'token': response['token'],
        'approved': user.approved_lk,
    }

    return make_response(json.dumps(response, ensure_ascii=False), 200)
