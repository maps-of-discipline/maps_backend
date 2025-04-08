Нужно исправить текущие ошибки, сделать `seed_db` рабочим и идемпотентным, и наметить дальнейшие шаги по реализации MVP (`logic.py`, `routes.py`) с фокусом на предоставление контекста для "агентной LLM" или разработчика.

**Подход:** Представим это как задачу в таск-трекере для разработчика (или LLM-агента).

---

## Задача: Исправление Сидера и Реализация Ядра API Матрицы Компетенций (MVP)

**Проект:** Академический Прогресс / Карты Дисциплин (Бэкенд)
**Модуль:** `competencies_matrix`
**Исполнитель:** [AI Agent / Developer]
**Статус:** К выполнению
**Приоритет:** Высокий

### 1. Общее Описание (Big Picture)

**Цель:** Довести модуль `competencies_matrix` до состояния, когда он корректно инициализируется, его структура БД соответствует миграции `a388922067b4...py`, тестовые данные успешно добавляются через `flask seed_db`, и реализован основной API-эндпоинт для получения данных матрицы (`GET /api/competencies/matrix/<aup_id>`).

**Архитектура:** Модуль `competencies_matrix` является Flask Blueprint, интегрированным в основной бэкенд `maps_backend`. Он использует общую БД (`db` из `maps.models`), аутентификацию (`auth`) и модели учебных планов (`AupInfo`, `AupData`, `SprDiscipline` из `maps.models`). Новые таблицы, специфичные для компетенций и матриц, определены в `competencies_matrix/models.py` и создаются через Alembic миграцию `a388922067b4...py`.

**Ключевой элемент MVP:** Обеспечить возможность **просмотра** матрицы компетенций для выбранного АУП, где строки - дисциплины АУП, столбцы - Компетенции, а ячейки показывают связанные **Индикаторы Достижения Компетенций (ИДК)**. Редактирование связей - следующий шаг.

**Definition of Done (DoD) для этой задачи:**

1.  Исправлены ошибки `TypeError` и `SAWarning` при запуске `flask seed_db`.
2.  Команда `flask seed_db` успешно выполняется, является идемпотентной и добавляет тестовые данные для таблиц `competencies_*` (ОП, ФГОС, АУП-ОП, Компетенции, ИДК, Матрица).
3.  Модели в `competencies_matrix/models.py` **полностью соответствуют** структуре таблиц, создаваемой миграцией `a388922067b4...py`.
4.  Функция `competencies_matrix.logic.get_matrix_for_aup(aup_id)` реализована: корректно извлекает данные из БД (включая связанные модели из `maps.models`) и возвращает структурированный словарь для API.
5.  Эндпоинт `GET /api/competencies/matrix/<aup_id>` в `competencies_matrix.routes` работает, вызывает `logic.get_matrix_for_aup`, защищен аутентификацией и возвращает корректный JSON (или 404).
6.  Избыточные файлы (`app_to_integrate.py`) и функции инициализации таблиц (`create_tables_if_needed`) удалены.

---

### 2. Подзадачи и Реализация

#### 2.1. Исправление Ошибок в `app.py` (`seed_db`) и Моделях

**Проблема:** `TypeError` при создании `EducationalProgram` (используется `name` вместо `title`). Многочисленные `SAWarning` из-за конфликтующих определений `relationship`.

**Решение:**

1.  **Исправить `TypeError` в `app.py :: seed_command`:**
    *   Заменить `name='Веб-технологии (09.03.01)'` на `title='Веб-технологии (09.03.01)'` при создании экземпляра `EducationalProgram`.

    ```python
    # app.py - внутри seed_command
    print("Seeding Educational Program...")
    program1 = EducationalProgram.query.get(1)
    if not program1:
        # ИСПРАВЛЕНО: Используем title вместо name
        program1 = EducationalProgram(id=1, fgos_vo_id=1, code='09.03.01', title='Веб-технологии (09.03.01)',
                                     profile='Веб-технологии', qualification='Бакалавр', form_of_education='очная', enrollment_year=2024)
        db.session.add(program1)
        print("  - Added Educational Program 'Веб-технологии'.")
    else:
        print("  - Educational Program 'Веб-технологии' already exists.")
    db.session.commit() # Коммитим сразу после merge/add
    ```

2.  **Исправить `SAWarning` (Roles/Users):**
    *   Открыть `auth/models.py`.
    *   Найти определения `relationship` между `Users` и `Roles` (через `user_roles`).
    *   Убедиться, что **на обеих сторонах** используется `back_populates`.

    ```python
    # auth/models.py (Пример, проверь реальный код)
    class Roles(db.Model):
        # ...
        # users = db.relationship("Users", secondary="user_roles", lazy='subquery', backref=db.backref('roles', lazy=True)) # СТАРЫЙ вариант с backref
        # НОВЫЙ вариант:
        users = db.relationship("Users", secondary="user_roles", back_populates="roles")
        # ...

    class Users(db.Model):
        # ...
        # roles = db.relationship('Roles', secondary='user_roles', lazy='subquery', backref=db.backref('users', lazy=True)) # СТАРЫЙ вариант с backref
        # НОВЫЙ вариант:
        roles = db.relationship("Roles", secondary="user_roles", back_populates="users")
        # ...
    ```

3.  **Исправить `SAWarning` (Indicator/Matrix/AupData):**
    *   Открыть `competencies_matrix/models.py`.
    *   **В классе `Indicator`:** Удалить `relationship('AupData', secondary='competencies_matrix', back_populates='indicators', lazy='dynamic')`. Оставить только `matrix_entries = relationship('CompetencyMatrix', back_populates='indicator')`.
    *   **В классе `CompetencyMatrix`:** Добавить связь с `AupData`: `aup_data_entry = relationship('AupData', back_populates='matrix_entries')`. Убедиться, что `indicator = relationship('Indicator', back_populates='matrix_entries')` существует.
    *   **В классе `AupData` (Динамическое добавление):** Изменить код в `add_aupdata_relationships`, чтобы он соответствовал новым связям.

    ```python
    # competencies_matrix/models.py

    class Indicator(db.Model, BaseModel):
        # ... (остальные поля)
        competency = relationship('Competency', back_populates='indicators')
        matrix_entries = relationship('CompetencyMatrix', back_populates='indicator', cascade="all, delete-orphan") # Связь с матрицей
        # УДАЛЕНО: aup_data_entries = relationship(...) - доступ будет через matrix_entries
        labor_functions = relationship('LaborFunction', secondary='competencies_indicator_ps_link', back_populates='indicators') # Связь с ПС

    class CompetencyMatrix(db.Model, BaseModel):
        # ... (остальные поля)
        aup_data_id = db.Column(db.Integer, db.ForeignKey('aup_data.id'), nullable=False)
        indicator_id = db.Column(db.Integer, db.ForeignKey('competencies_indicator.id'), nullable=False)

        # ИСПРАВЛЕНО/ДОБАВЛЕНО: Четкие back_populates
        indicator = relationship('Indicator', back_populates='matrix_entries')
        aup_data_entry = relationship('AupData', back_populates='matrix_entries') # Добавлена связь с AupData

    # Исправляем динамическое добавление в AupData
    @db.event.listens_for(AupData, 'mapper_configured', once=True) # Добавлен once=True для надежности
    def add_aupdata_relationships(mapper, class_):
        # Проверяем наличие перед добавлением
        if not hasattr(class_, 'matrix_entries'):
            class_.matrix_entries = relationship(
                'CompetencyMatrix',
                # ИСПРАВЛЕНО: back_populates указывает на атрибут в CompetencyMatrix
                back_populates='aup_data_entry',
                cascade="all, delete-orphan", # Возможно, каскадное удаление нужно здесь?
                lazy='dynamic' # Оставляем dynamic, если нужен QueryableAttribute
            )
            print(f"Dynamically added 'matrix_entries' relationship to AupData")
        # Старую связь 'indicators' больше не добавляем
    ```

4.  **Исправить `SAWarning` (UnificationDiscipline):**
    *   Предположительно, модели находятся в `unification/models.py`.
    *   Найти `UnificationDiscipline` и `DisciplinePeriodAssoc`.
    *   Установить `back_populates` на обеих сторонах (`periods` в `UnificationDiscipline` и `unification_discipline` в `DisciplinePeriodAssoc`).

5.  **Удалить Избыточный Код:**
    *   Удалить файл `competencies_matrix/app_to_integrate.py`.
    *   Удалить функции `create_tables_if_needed` и `initialize_lookup_data` из `competencies_matrix/models.py`.

#### 2.2. Доработка `app.py :: seed_command`

**Проблема:** Сидер не идемпотентный и неполный.

**Решение:**

*   **Идемпотентность:** Использовать `db.session.merge(object)` вместо `db.session.add(object)`. `merge` либо добавляет новый объект (если PK нет в сессии/БД), либо обновляет существующий объект в сессии данными из переданного объекта. Это безопаснее для сидера.
*   **Полнота:** Пройти по коду `seed_command` (пример в предыдущем ответе) и **добавить `merge()`** для *всех* тестовых данных, которые должны присутствовать в MVP: ФГОС, ОП, АУП, Связь ОП-АУП, Дисциплины, Записи AupData, Компетенции, Индикаторы, Связи в Матрице.
*   **Коммиты:** Делать `db.session.commit()` после логических блоков добавления данных (например, после всех типов компетенций, потом после ОП, потом после АУП и т.д.), чтобы зафиксировать изменения и избежать слишком больших транзакций.

```python
# app.py - Фрагмент seed_command с использованием merge
@click.command(name='seed_db')
@with_appcontext
def seed_command():
    """Заполняет базу данных начальными/тестовыми данными (Идемпотентно)."""
    print("Starting database seeding...")
    try:
        # --- 1. Базовые справочники ---
        print("Seeding Competency Types...")
        db.session.merge(CompetencyType(id=1, code='УК', name='Универсальная'))
        db.session.merge(CompetencyType(id=2, code='ОПК', name='Общепрофессиональная'))
        db.session.merge(CompetencyType(id=3, code='ПК', name='Профессиональная'))
        db.session.commit() # Коммит после блока
        print("  - Competency types checked/merged.")

        # ... (Аналогично для Roles) ...
        db.session.commit() # Коммит после блока

        # --- 3. Основные тестовые данные ---
        print("Seeding FGOS...")
        fgos1 = FgosVo(id=1, ...) # Как раньше
        db.session.merge(fgos1)
        db.session.commit()

        print("Seeding Educational Program...")
        # ИСПОЛЬЗУЕМ title
        program1 = EducationalProgram(id=1, fgos_vo_id=1, code='09.03.01', title='Веб-технологии (09.03.01)', ...)
        db.session.merge(program1)
        db.session.commit()

        # ... (AUP, AUP-Program Link, Disciplines, AupData - используем merge) ...
        db.session.commit() # Коммит после блока AupData

        print("Seeding Competencies & Indicators...")
        # Используем merge для компетенций
        comp_uk1 = Competency(id=1, competency_type_id=1, fgos_vo_id=1, code='УК-1', name='...')
        db.session.merge(comp_uk1)
        # ... (другие компетенции) ...
        db.session.commit() # Коммит компетенций ПЕРЕД индикаторами

        # Используем merge для индикаторов
        # ВАЖНО: merge работает по Primary Key. Если ID уже занят, он обновит запись.
        ind_iuk1_1 = Indicator(id=10, competency_id=1, code='ИУК-1.1', formulation='...')
        db.session.merge(ind_iuk1_1)
        # ... (другие индикаторы) ...
        db.session.commit() # Коммит индикаторов

        print("Seeding Competency Matrix links...")
        # Используем merge для связей (у CompetencyMatrix должен быть свой PK - 'id')
        # Убедись, что ID AupData и Indicator корректны
        link1 = CompetencyMatrix(aup_data_id=501, indicator_id=10, is_manual=True) # Пример
        # Проверяем существование перед merge, т.к. у нас нет уникального PK для merge по FK
        existing_link1 = CompetencyMatrix.query.filter_by(aup_data_id=501, indicator_id=10).first()
        if not existing_link1:
            db.session.add(link1) # Используем add, если проверяем вручную
        # ... (другие связи) ...
        db.session.commit() # Коммит связей

        print("Database seeding finished successfully.")
    except Exception as e:
        db.session.rollback()
        print(f"ERROR during database seeding: {e}")
        import traceback
        traceback.print_exc()

# Не забудь зарегистрировать команду
# app.cli.add_command(seed_command)

```

#### 2.3. Реализация Логики `get_matrix_for_aup`

**Проблема:** Функция `logic.get_matrix_for_aup` написана, но требует проверки и, возможно, доработки связей с моделями, соответствующими миграции.

**Решение:** Код функции `get_matrix_for_aup` из предыдущего ответа уже довольно близок к цели. Основные моменты для проверки и доработки:

*   **Связь `Competency` с `FgosVo`:** Добавить FK `fgos_vo_id` в модель `Competency`, сгенерировать миграцию, применить ее, и раскомментировать блок фильтрации УК/ОПК в `get_matrix_for_aup`.
*   **Выборка ПК:** Определиться с логикой связи ПК с ОП. **Для MVP:** оставить текущую логику (брать все ПК). **Полноценное решение:** фильтровать ПК по ТФ (`based_on_labor_function_id`), которые принадлежат ПС (`ProfStandard`), выбранным для данной ОП (`EducationalProgramPs`). Это потребует запроса с JOIN'ами через `EducationalProgramPs -> ProfStandard -> GeneralizedLaborFunction -> LaborFunction -> Competency`.
*   **Производительность:** Для больших матриц использовать `selectinload` и `joinedload` критически важно. Текущий код уже их использует, это хорошо.
*   **Сериализация:** Проверить `to_dict` и `rules`/`only`, чтобы API возвращал только нужные поля и не было циклических ссылок.

#### 2.4. Реализация API Роута `GET /matrix/<aup_id>`

**Проблема:** Роут есть, но нужно убедиться, что он корректно вызывает логику и обрабатывает результаты/ошибки.

**Решение:** Код в `routes.py` из предыдущего ответа в целом корректен. Нужно:

*   Убедиться, что декоратор `@login_required(request)` (или его аналог из `auth.logic`) правильно импортирован и используется.
*   Добавить (когда будет готова система прав) декоратор `@check_permission('view_matrix')`.
*   Протестировать возврат 404, если `get_matrix_for_aup` вернул `None`.
*   Протестировать возврат 500 при возникновении исключений в `logic.py`.

---

### 3. Контекст для LLM/Разработчика

*   **Главная Цель:** Создать API для отображения Матрицы Компетенций. Матрица связывает **Дисциплины** (из существующего модуля `maps`, таблицы `aup_data`) с **Индикаторами Достижения Компетенций (ИДК)** (из нового модуля `competencies_matrix`, таблица `competencies_indicator`).
*   **Источник Данных:**
    *   **Дисциплины и АУП:** Модели `AupInfo`, `AupData`, `SprDiscipline` из `maps.models`.
    *   **УК/ОПК и их ИДК:** Модели `Competency`, `Indicator` из `competencies_matrix.models`, связанные с `FgosVo`. Данные берутся из ФГОС и Распоряжения 505-Р.
    *   **ПК и их ИДК:** Модели `Competency`, `Indicator` из `competencies_matrix.models`. ПК создаются пользователем (методистом) на основе ТФ из ПС. ИДК для ПК также создаются пользователем.
    *   **Матрица Связей:** Таблица `competencies_matrix` хранит пары (`aup_data_id`, `indicator_id`).
*   **Управление Схемой:** Используется **Alembic**. Все изменения схемы делаются через миграции (`flask db migrate`, `flask db upgrade`). Миграция `a388922067b4...py` уже создает основные таблицы.
*   **Наполнение Данными:** Используется команда **`flask seed_db`**. Она должна быть **идемпотентной** (использовать `db.session.merge()` или проверки на существование) и содержать **все необходимые тестовые данные** для MVP.
*   **Текущий Фокус:** Реализовать чтение данных для матрицы (`GET /matrix/<aup_id>`) и базовое добавление/удаление связей (`POST/DELETE /matrix/link`).
*   **Взаимодействие:** Код `competencies_matrix` должен корректно импортировать `db` и модели из `maps.models`.
*   **Будущее:** Парсинг ПС (`parsers.py`), интеграция NLP, CRUD для всех сущностей, система прав доступа.