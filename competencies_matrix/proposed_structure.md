maps_backend/
├── administration/
├── auth/
├── cabinet/          # Существующий модуль "Академический Прогресс"
├── maps/             # Существующий модуль "Карты Дисциплин" (с AUP, Disciplines и т.д.)
├── competencies_matrix/   # <<<--- НАШ НОВЫЙ МОДУЛЬ
│   ├── __init__.py        # Регистрация Blueprint
│   ├── routes.py          # API эндпоинты для компетенций, ИДК, ПС, матрицы
│   ├── models.py          # SQLAlchemy модели для НОВЫХ таблиц (компетенции, ИДК, ПС, связи, матрица и т.д.)
│   ├── logic.py           # Бизнес-логика: обработка запросов, взаимодействие с БД и NLP
│   ├── parsers.py         # Логика парсинга ПС (адаптированный profstandard-lean.py)
│   ├── schemas.py         # (Опционально, но рекомендуется) Pydantic/Marshmallow схемы для валидации API
│   └── utils.py           # Вспомогательные функции для модуля
├── migrations/
├── static/
├── templates/
├── .env
├── .gitignore
├── app.py               # Главный файл приложения Flask (здесь регистрируем новый Blueprint)
├── config.py
├── Dockerfile
├── requirements.txt     # Добавить сюда новые зависимости (если будут)
└── ... прочие файлы ...