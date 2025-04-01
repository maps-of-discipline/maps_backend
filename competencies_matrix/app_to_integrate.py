"""
Объяснение: Мы добавляем импорт и регистрацию нашего competencies_matrix_bp
в основной фабрике приложения (create_app). 
Теперь Flask знает о маршрутах, определенных в нашем модуле.
"""

# app.py (фрагмент)
from flask import Flask
# ... другие импорты ...
from maps.models import db # Предполагаем, что db инициализируется здесь или в maps/__init__.py
from config import Config

# Импортируем существующие блюпринты
from administration import admin_bp
from auth import auth_bp
from cabinet import cabinet_bp # Старый "Академический прогресс"
from maps import maps_bp     # Карты дисциплин

# <<<--- Импортируем НАШ новый Blueprint ---<<<
from competencies_matrix import competencies_matrix_bp

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    # ... инициализация других расширений (Migrate, CORS, etc.) ...

    # Регистрация существующих Blueprints
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cabinet_bp)
    app.register_blueprint(maps_bp)

    # <<<--- Регистрация НАШЕГО Blueprint ---<<<
    app.register_blueprint(competencies_matrix_bp)

    # ... прочий код app.py ...

    return app

# ... остальной код app.py ...

if __name__ == '__main__':
    app = create_app()
    # Запуск приложения (может отличаться в зависимости от gunicorn/waitress)
    app.run(host='0.0.0.0', port=5000) # Пример для локального запуска