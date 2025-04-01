# competencies_matrix/__init__.py
from flask import Blueprint

# Создаем Blueprint для нашего модуля
# 'competencies_matrix_bp' - уникальное имя для Blueprint
# __name__ - имя текущего модуля Python
# url_prefix='/api/competencies' - базовый URL для всех роутов этого модуля
competencies_matrix_bp = Blueprint(
    'competencies_matrix_bp',
    __name__,
    url_prefix='/api/competencies' # Префикс для всех API этого модуля
)

# Импортируем роуты ПОСЛЕ создания Blueprint, чтобы избежать циклических импортов
from . import routes

# Здесь можно добавить обработчики ошибок, контекстные процессоры и т.д., специфичные для модуля