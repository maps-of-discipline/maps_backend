# filepath: competencies_matrix/logic/error_utils.py
import logging
import re
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Dict, Any

from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

logger = logging.getLogger(__name__)


class ErrorResponse:
    """Централизованное создание ответов об ошибках."""
    
    @staticmethod
    def db_connection_error(operation: str) -> Dict[str, Any]:
        return {
            "status": "connection_failed", 
            "message": f"Не удалось подключиться к базе данных. {operation} невозможна."
        }
    
    @staticmethod
    def not_found(item: str) -> Dict[str, Any]:
        return {"status": "error", "message": f"{item} не найдена."}
    
    @staticmethod
    def internal_error(operation: str) -> Dict[str, Any]:
        return {
            "status": "error", 
            "message": f"Произошла внутренняя ошибка сервера при {operation}."
        }

    @staticmethod
    def external_db_connection_error() -> Dict[str, Any]:
        try:
            db_url = current_app.config.get('EXTERNAL_KD_DATABASE_URL', 'неизвестный хост')
            host_match = re.search(r'@([\w.-]+)', db_url)
            host = host_match.group(1) if host_match else 'unknown'
        except Exception:
            host = 'unknown'
        return {
            "status": "connection_failed", 
            "message": f"Не удалось подключиться к серверу 'Карт Дисциплин' ({host}). Проверка версии невозможна."
        }


def handle_db_errors(default_return=None, log_errors=True):
    """Декоратор для обработки распространенных ошибок базы данных."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, OperationalError):
                    if log_errors:
                        logger.error(f"Database connection error in {func.__name__}: {e}")
                elif isinstance(e, SQLAlchemyError):
                    if log_errors:
                        logger.error(f"Database error in {func.__name__}: {e}")
                else:
                    if log_errors:
                        logger.exception(f"Unexpected error in {func.__name__}")
                
                if default_return is not None:
                    return default_return
                raise
        return wrapper
    return decorator


@contextmanager
def external_db_session():
    """Контекстный менеджер для сессий с внешней базой данных."""
    engine = None
    try:
        db_url = current_app.config.get('EXTERNAL_KD_DATABASE_URL')
        if not db_url:
            raise RuntimeError("EXTERNAL_KD_DATABASE_URL не настроен в конфигурации.")
        engine = create_engine(db_url)
        with Session(engine) as session:
            yield session
    except OperationalError:
        raise
    except Exception as e:
        logger.error(f"External database error: {e}")
        raise
    finally:
        if engine:
            engine.dispose()


def safe_get_program(session, program_id: int):
    """Безопасное получение программы по ID с надлежащей обработкой ошибок."""
    try:
        from ..models import EducationalProgram
        return session.get(EducationalProgram, program_id)
    except Exception as e:
        logger.error(f"Database error retrieving program {program_id}: {e}")
        raise


def handle_aup_import_error(operation: str, aup_num: str):
    """Обработка ошибок импорта АУП с единообразными сообщениями."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                try:
                    from ..logic.educational_programs import AupImportError
                except ImportError:
                    AupImportError = RuntimeError

                if isinstance(e, OperationalError):
                    logger.error(f"Database connection failed during AUP {operation} '{aup_num}': {e}")
                    error_msg = f"Не удалось подключиться к базе данных для {operation} АУП '{aup_num}'."
                elif isinstance(e, SQLAlchemyError):
                    logger.error(f"Database error during AUP {operation} '{aup_num}': {e}")
                    error_msg = f"Ошибка базы данных при {operation} АУП '{aup_num}'."
                else:
                    logger.exception(f"Unexpected error during AUP {operation} '{aup_num}'")
                    error_msg = f"Не удалось выполнить {operation} АУП '{aup_num}'."
                
                raise AupImportError(error_msg)
        return wrapper
    return decorator