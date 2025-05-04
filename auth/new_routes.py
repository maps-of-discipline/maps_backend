from flask import Blueprint, jsonify, request
from grpc_service.auth_logic import AuthManager
from dataclasses import asdict

auth = AuthManager()
new_auth = Blueprint('new_auth', __name__)

# Роут для проверки авторизации
