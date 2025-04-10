# Карты дисциплин и матрицы компетенций

## Веб-приложение для преподавателей и методистов для работы с академическими учебными планами, картами дисциплин и матрицами компетенций.

#### Ссылка на Сайт проекта: https://kd.mospolytech.ru/

## Структура проекта

### Основные модули:

#### Модуль maps (Карты дисциплин)
- `maps/models.py` - ORM модели для карт дисциплин, АУП и справочников
- `maps/routes.py` - API эндпоинты для работы с картами дисциплин
- `maps/logic/save_into_bd.py` - Функции загрузки карт в БД
- `maps/logic/excel_check.py` - Функции проверки загружаемых карт
- `maps/logic/take_from_bd.py` - Функции получения данных из БД
- `maps/logic/tools.py` - Утилиты для работы с картами дисциплин

#### Модуль competencies_matrix (Матрицы компетенций)
- `competencies_matrix/models.py` - ORM модели для компетенций, образовательных программ, профстандартов
- `competencies_matrix/routes.py` - API эндпоинты для работы с матрицами компетенций
- `competencies_matrix/logic.py` - Бизнес-логика модуля
- `competencies_matrix/parsers.py` - Парсеры профессиональных стандартов

#### Модуль cabinet (Академический кабинет)
- `cabinet/cabinet.py` - Основной файл с Blueprint и роутами
- `cabinet/models.py` - ORM модели для таблиц "Академического кабинета"
- `cabinet/lib/` - Вспомогательные библиотеки для операций с дисциплинами

#### Дополнительные модули
- `auth/` - Модуль аутентификации и авторизации
- `administration/` - Модуль администрирования системы
- `unification/` - Модуль унификации дисциплин
- `utils/` - Общие утилиты
- `migrations/` - Alembic миграции для управления схемой БД

### Конфигурационные файлы
- `app.py` - Главный файл приложения Flask
- `config.py` - Настройки подключения к БД, секреты и конфигурации
- `Dockerfile` - Конфигурация для сборки Docker-образа
- `requirements.txt` - Зависимости Python

## Запуск проекта

`python -m venv venv`

`venv/scripts/activate` or `source venv/bin/activate` for linux/mac

`pip install -r requirements.txt`

`flask run --reload`
