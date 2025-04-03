# competencies_matrix/__init__.py
from flask import Blueprint, jsonify

# Создаем Blueprint для нашего модуля
# 'competencies_matrix_bp' - уникальное имя для Blueprint
# __name__ - имя текущего модуля Python
# url_prefix='/api/competencies' - базовый URL для всех роутов этого модуля
competencies_matrix_bp = Blueprint(
    'competencies_matrix_bp',
    __name__,
    url_prefix='/api/competencies' # Префикс для всех API этого модуля
)

# Настраиваем обработчики ошибок для нашего blueprint
@competencies_matrix_bp.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@competencies_matrix_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Импортируем роуты ПОСЛЕ создания Blueprint, чтобы избежать циклических импортов
from . import routes

# Опциональные настройки для интеграции с основным приложением
def init_app(app):
    """
    Инициализация модуля при подключении к основному приложению.
    Здесь можно добавить дополнительные настройки.
    """
    pass

# Здесь можно добавить обработчики ошибок, контекстные процессоры и т.д., специфичные для модуля