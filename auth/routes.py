import json

from flask import Blueprint, make_response, request, jsonify, url_for
import time
import secrets
from flask_mail import Mail, Message
from auth.logic import verify_jwt_token, verify_refresh_token, get_access_token, get_refresh_token
from auth.models import Users
from maps.models import db
from .cli import register_commands
from pprint import pprint
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app import mail

auth = Blueprint("auth", __name__, url_prefix='/api')
register_commands(auth)


# время жизни токена
PASSWORD_RESET_TOKEN_EXPIRATION = 3600 * 24


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


users_db = {}
s = URLSafeTimedSerializer('dkdf')


def generate_reset_token(email):
    token = s.dumps(email, salt='email-reset')
    users_db[email]['reset_token'] = token
    return token


def verify_reset_token(token, expiration=3600):
    try:
        email = s.loads(token, salt='email-reset', max_age=expiration)
        if users_db.get(email, {}).get('reset_token') == token:
            return email
    except (SignatureExpired, BadSignature):
        return None


def update_user_password(email, new_password):
    if email in users_db:
        users_db[email]['password'] = new_password
        return True
    return False


password_reset_tokens = {

}


@auth.route('/request-reset', methods=['POST'])
def request_reset():
    data = request.get_json()
    email = data.get('EMAIL')
    if not email:
        return jsonify({"error": "Invalid email"}), 400

    user: Users = Users.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 400

    # Генерация токена безопасности
    reset_token = secrets.token_urlsafe(16)

    password_reset_tokens[reset_token] = {"user_id": user.id_user,
                                          "ttl": PASSWORD_RESET_TOKEN_EXPIRATION + round(time.time())}

    # Отправка письма со ссылкой для сброса пароля
    reset_url = url_for('auth.reset_with_token', token=reset_token, _external=True)
    msg = Message("Password Reset", recipients=[email])
    msg.body = f"To reset your password, visit the following link: {reset_url}"

    mail.send(msg)

    return jsonify({"message": "Instructions to reset your password have been sent to your email."}), 200


@auth.route('/reset-password/<token>', methods=['POST'])
def reset_with_token(token):
    pprint(token)
    if not token:
        return jsonify({"error": "Invalid or expired token"}), 400
    email = verify_reset_token(token)

    if email is None:
        return jsonify({"error": "Invalid or expired token"}), 400

    data = request.get_json()
    new_password = data.get('password')
    if not new_password:
        return jsonify({"error": "New password is required"}), 400

    # Обновление пароля в базе данных
    if update_user_password(email, new_password):
        return jsonify({"message": "Your password has been updated."}), 200
    else:
        return jsonify({"error": "An error occurred"}), 400


def restore(token):
    data = request.get_json()
    new_password = data.get('password')
    user_id = password_reset_tokens[token]['user_id']

    user: Users = Users.query.filter_by(id_user=user_id).first()
    user.set_password(new_password)
    db.session.add(user)
    db.session.commit()
    pprint(token)
    del password_reset_tokens[token]
    return jsonify({"result": "Your password has been updated."}), 200
