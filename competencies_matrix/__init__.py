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
    return jsonify({'error': 'Internal server error'}), 500

# Optional settings for integration with main application
def init_app(app):
    """
    Initialize module when connecting to main application.
    This tries to set up the database tables if they don't exist.
    """
    try:
        # Attempt to create tables for this module
        from . import models  # Import models only when needed
        with app.app_context():
            models.create_tables_if_needed()
    except Exception as e:
        handle_initialization_error(e)

# Import routes AFTER creating Blueprint to avoid circular imports
from . import routes