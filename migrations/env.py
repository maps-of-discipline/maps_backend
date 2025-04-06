# migrations/env.py
import logging
from logging.config import fileConfig
import os # Добавим os для работы с путем

from flask import current_app
from sqlalchemy import engine_from_config, pool
from alembic import context

# Импортируем общий объект db и Base (если модели от него наследуются,
# но в нашем случае они наследуются от db.Model, так что db.metadata достаточно)
# Убедись, что путь импорта правильный!
from maps.models import db
# from yourapp.models import Base # Если используется declarative_base()

# --- КЛЮЧЕВОЙ МОМЕНТ: Импорт всех моделей, чтобы Alembic их увидел ---
# Импортируем модели всех модулей, которые должны управляться Alembic
# Убедись, что все нужные файлы models.py импортируются
import maps.models
import auth.models
import cabinet.models
import competencies_matrix.models
# import unification.models # Если модуль unification тоже использует Alembic
# ---------------------------------------------------------------------

# Это стандартная конфигурация Alembic
config = context.config

# Интерпретация файла конфигурации для логирования Python.
# Эта строка предполагает, что ваш alembic.ini находится в том же каталоге.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger('alembic.env')

# --- Получение URL БД из конфигурации Flask ---
# Добавляем более надежный способ получения URL, работающий вне контекста приложения Flask
# если это необходимо (например, при запуске alembic напрямую)
def get_url():
    flask_app_config_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
    if flask_app_config_url:
        return flask_app_config_url.replace('%', '%%') # Экранируем % для Alembic

    # Запасной вариант: чтение из переменной окружения или alembic.ini,
    # если запуск идет вне контекста Flask
    env_url = os.getenv('DATABASE_URL')
    if env_url:
         return env_url.replace('%', '%%')
    return config.get_main_option("sqlalchemy.url") # Из alembic.ini

config.set_main_option('sqlalchemy.url', get_url())
# -------------------------------------------------

# --- Определение метаданных ---
# Используем metadata из общего объекта Flask-SQLAlchemy 'db',
# так как все модели (включая новые) должны быть привязаны к нему
target_metadata = db.metadata
# Если бы использовался declarative_base():
# target_metadata = Base.metadata
# --------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata, # Используем общие метаданные
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Используем конфигурацию пула из alembic.ini
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata, # Используем общие метаданные
            process_revision_directives=process_revision_directives, # Для автогенерации
             **current_app.extensions['migrate'].configure_args # Для совместимости с Flask-Migrate
        )

        with context.begin_transaction():
            context.run_migrations()

# Функция для обработки автогенерации (чтобы не создавались пустые миграции)
def process_revision_directives(context, revision, directives):
    if config.cmd_opts.autogenerate:
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info('No changes in schema detected.')


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()