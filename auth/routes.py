import json
import time
import secrets
import requests
from flask import Blueprint, make_response, request, jsonify, url_for, current_app, g
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


@auth.route('/user')
@login_required
def get_current_user_info():
    # g.user is set by the @login_required decorator
    # g.auth_payload contains the decoded JWT token payload
    
    # Use logging instead of print for production
    # logging.debug(f"/api/auth/user called for user ID: {g.user.id_user}, login: {g.user.login}")
    # logging.debug(f"Original JWT payload (g.auth_payload): {g.auth_payload}")

    # Start with the existing payload
    response_payload = g.auth_payload.copy()
    # logging.debug(f"Initial response payload: {response_payload}")

    # --- CRUTCH FIX START ---
    # Manually add permissions object if user is admin
    is_admin = any(role.id_role == 1 for role in g.user.roles) # Check if user has role ID 1 (Admin)
    
    if is_admin:
        # logging.debug(f"User {g.user.login} IS an admin. Adding admin permissions.")
        if 'permissions' not in response_payload:
            response_payload['permissions'] = {}
            
        # Add admin-specific permissions (adjust as needed)
        response_payload['permissions']['admin'] = {
            'isAdmin': True,
            'canAccessAdminPanel': True,
            'canManageUsers': True,
        }
        # You could potentially add permissions for other roles here too if needed for testing
        # Example: Add student permissions if admin should also see student views
        # response_payload['permissions']['student'] = { ... }
    else:
        # logging.debug(f"User {g.user.login} is NOT an admin. No permissions added.")
        # Ensure permissions object exists even if empty for non-admins
        if 'permissions' not in response_payload:
             response_payload['permissions'] = {}

    # --- CRUTCH FIX END ---

    # logging.debug(f"Final response payload for /api/auth/user: {response_payload}")
    
    # Return the modified payload
    return jsonify(response_payload)


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
        # logging.warning("Login key missing, returning 401/400")
        return make_response("Login is required", 400)

    if 'password' not in request_data:
        # logging.warning("Password key missing, returning 401/400")
        return make_response("Password is required", 400)

    user = Users.query.filter_by(login=request_data['login']).first()

    if not user:
        # logging.warning("User not found, returning 400")
        return make_response("No such user", 400)

    password_correct = user.check_password(request_data['password'])

    if not password_correct:
        # logging.warning("Incorrect password, returning 400")
        return make_response('Incorrect password', 400)

    # Generate tokens
    access_token = get_access_token(user.id_user)
    refresh_token = get_refresh_token(user.id_user, request.headers.get('User-Agent', 'Unknown'))
    
    # Create response with user information
    response = {
        'access': access_token,
        'refresh': refresh_token,
        'token': access_token,  # Include this for compatibility
        'user': {
            'id': user.id_user,
            'name': user.name or '',
            'login': user.login,
            'surname': '',  # Add surname if available in your user model
            'roles': [{'id': role.id_role, 'name': role.name_role} for role in user.roles],
            'permissions': {},  # Will be populated if needed
            'approved': user.approved_lk
        }
    }

    # logging.info(f"Login successful for user {user.id_user}, returning 200")
    # logging.debug(f"Login response: {response}")
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
    # logging.debug(f"Password reset tokens: {password_reset_tokens}") # Remove or use proper logging
    return jsonify({"message": "Instructions to reset your password have been sent to your email."}), 200


@auth.route('/reset-password/<token>', methods=['POST'])
def reset_with_token(token):
    # pprint(token) # Remove or use proper logging
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

    # Check if we can perform direct login (for development/test without LK)
    user = Users.query.filter_by(login=request_data['username']).first()
    lk_url = current_app.config.get('LK_URL')
    
    if not lk_url:
        # logging.warning("LK_URL not configured, attempting direct login") # Use logging
        # LK integration is not available, try direct login
        if not user:
            return make_response("No such user", 400)
        
        password_correct = user.check_password(request_data['password'])
        if not password_correct:
            return make_response('Incorrect password', 400)
        
        # Create a minimal response that works for both auth flows
        response = {
            'access': get_access_token(user.id_user),
            'refresh': get_refresh_token(user.id_user, request.headers.get('User-Agent', 'Unknown')),
            'approved': user.approved_lk or False,
        }
        
        # logging.debug(f"Login response: {response}") # Use logging
        return make_response(json.dumps(response, ensure_ascii=False), 200)
    
    # If LK_URL is configured, proceed with normal LK auth flow
    try:
        response = requests.post(lk_url, data={
            'ulogin': request_data['username'],
            'upassword': request_data['password'],
        }).json()

        res = requests.get(lk_url, params={'getUser': '', 'token': response['token']}).json()
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
    except Exception as e:
        # logging.error(f"LK authentication failed: {str(e)}") # Use logging
        return make_response(f"LK authentication failed: {str(e)}", 500)

    db.session.add(user)
    db.session.commit()

    response = {
        'access': get_access_token(user.id_user),
        'refresh': get_refresh_token(user.id_user, request.headers['User-Agent']),
        'token': response['token'],
        'user': {
            'id': user.id_user,
            'name': user.name or '',
            'login': user.login,
            'surname': '',
            'roles': [{'id': role.id_role, 'name': role.name_role} for role in user.roles],
            'permissions': {},
            'approved': user.approved_lk
        }
    }

    # logging.debug(f"Login response: {response}") # Use logging
    return make_response(json.dumps(response, ensure_ascii=False), 200)
