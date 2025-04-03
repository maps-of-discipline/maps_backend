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

# competencies_matrix/app_to_integrate.py
"""
Файл для интеграции модуля матрицы компетенций с основным приложением.
Этот файл выполняет роль точки входа и инициализации для модуля.
"""
from flask import Flask
from . import competencies_matrix_bp  # Импортируем Blueprint из __init__.py

def init_app(app: Flask):
    """
    Инициализирует модуль competencies_matrix в основном приложении Flask.
    Эта функция вызывается из основного app.py при инициализации приложения.
    
    Args:
        app (Flask): Экземпляр приложения Flask
    """
    # Регистрируем Blueprint
    app.register_blueprint(competencies_matrix_bp)
    
    # Здесь может быть дополнительная инициализация модуля:
    # - Настройка конфигурации
    # - Регистрация обработчиков ошибок
    # - Настройка перехватчиков запросов
    # - Инициализация объектов, специфичных для модуля
    
    # Логируем успешную инициализацию
    app.logger.info("Модуль 'competencies_matrix' успешно инициализирован")