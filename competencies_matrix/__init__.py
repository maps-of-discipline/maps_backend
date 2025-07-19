# competencies_matrix/__init__.py
from flask import Blueprint, jsonify
from maps.models import db

# Create Blueprint for our module
competencies_matrix_bp = Blueprint(
    'competencies_matrix_bp',
    __name__,
    url_prefix='/api/competencies'  # Префикс для всех API этого модуля
)

def handle_initialization_error(error):
    """Handle errors during module initialization gracefully"""
    print(f"Warning: Competencies Matrix initialization error: {error}")
    return True  # Continue initialization

# Configure error handlers for our blueprint
@competencies_matrix_bp.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@competencies_matrix_bp.errorhandler(500)
def internal_error(error):
    # В production стоит логировать полную ошибку
    # current_app.logger.error(f"Internal server error: {error}", exc_info=True)
    # Для пользователя можно вернуть более общее сообщение
    return jsonify({'error': 'Internal server error'}), 500

# Optional settings for integration with main application
def init_app(app):
    """
    Initialize module when connecting to main application.
    
    Note: Table creation is handled by Alembic migrations,
    not dynamically at runtime.
    """
    try:
        # Import models to ensure they're registered with SQLAlchemy
        from . import models
        # We don't create tables dynamically anymore - using Alembic migrations instead
    except Exception as e:
        handle_initialization_error(e)

# Import routes AFTER creating Blueprint to avoid circular imports
from .routes import educational_programs_routes
from .routes import matrix_operations_routes
from .routes import competencies_indicators_routes
from .routes import fgos_routes
from .routes import prof_standards_routes
from .routes import aup_external_routes
from .routes import uk_pk_generation_routes