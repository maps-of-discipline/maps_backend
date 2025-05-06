Отлично, следуя вашему плану и детализированным размышлениям, давайте сфокусируемся на реализации парсера ФГОС ВО (3++) из PDF и связанных с ним функций на бэкенде и фронтенде.

---
**План действий:**

1.  **Бэкенд: Реализация Парсера ФГОС ВО из PDF.**
    *   Выбор библиотеки для парсинга PDF (например, `pdfminer.six` или `pdfplumber`). Начнем с более простой, текстовой (`pdfminer.six`), чтобы минимизировать зависимости и сфокусироваться на извлечении текста и регулярных выражениях.
    *   Создание нового файла `fgos_parser.py`.
    *   Написание логики для извлечения:
        *   Метаданных ФГОС (номер, дата приказа, направление, уровень, поколение) из начальных разделов.
        *   Таблиц с УК/ОПК и ИУК/ИОПК.
        *   Списка рекомендованных ПС.
    *   Форматирование извлеченных данных в структурированный словарь.
2.  **Бэкенд: Дополнение `competencies_matrix/logic.py`.**
    *   Добавление функции `parse_fgos_file` для оркестрации вызова парсера.
    *   Добавление функции `save_fgos_data` для сохранения структурированных данных из парсера в БД (`FgosVo`, `CompetencyType` lookup, `Competency`, `Indicator`, `FgosRecommendedPs`). Эта функция должна уметь обрабатывать существующие записи (обновлять или создавать новые).
    *   Добавление функций `get_fgos_list` и `get_fgos_details`.
    *   Добавление функции `delete_fgos`.
3.  **Бэкенд: Дополнение `competencies_matrix/routes.py`.**
    *   Добавление эндпоинта `POST /fgos/upload` для загрузки файла ФГОС и вызова `parse_fgos_file` (возвращает данные без сохранения).
    *   Добавление эндпоинта `POST /fgos/save` для приема структурированных данных (после подтверждения в UI) и вызова `save_fgos_data`.
    *   Добавление эндпоинтов `GET /fgos` и `GET /fgos/<int:fgos_id>`.
    *   Добавление эндпоинта `DELETE /fgos/<int:fgos_id>` (для CLI-тестирования и админки).
    *   Применение соответствующих декораторов (`@login_required`, `@approved_required`, возможно `@admin_only`).
4.  **Бэкенд: Дополнение `cli_commands/fgos_import.py`.** (Новый файл)
    *   Создание Flask CLI команды `flask import-fgos <filepath>`.
    *   Реализация логики команды: чтение файла, вызов `parse_fgos_file`, затем вызов `save_fgos_data` (в рамках транзакции).
    *   Добавление флагов `--force` (удалить старый перед сохранением нового) и `--delete-only` (только удалить, если существует).
    *   Включение обработки ошибок и логирования.
5.  **Frontend: Дополнение Store и API Service.**
    *   В `competenciesMatrix.ts`: добавить состояние для списка ФГОС, выбранного ФГОС для просмотра деталей, загрузки, ошибки. Добавить экшены `fetchFgosList`, `fetchFgosDetails`, `uploadFgosFile` (вызывает API upload, получает парсенные данные), `saveFgosData` (вызывает API save), `deleteFgos`.
    *   В `CompetenciesApi.ts`: добавить методы для новых API эндпоинтов.
6.  **Frontend: Реализация UI для Управления ФГОС.**
    *   Создание нового компонента `FgosView.vue` (или переименование `ProgramsView.vue` с добавлением вкладок). В вашем макете уже есть `views/competencies/CompetenciesView.vue` с вкладками - добавим функционал туда или создадим новую страницу. Используем `FgosView.vue` как страницу списка и загрузки.
    *   Создание компонента `FgosPreviewModal.vue` для отображения парсенных данных, их сравнения с существующими (если есть) и подтверждения сохранения.
    *   Реализация списка ФГОС (используя `DataTable` как в `ProgramsView`).
    *   Кнопка "Загрузить ФГОС", открывающая окно выбора файла.
    *   После выбора файла - вызов `uploadFgosFile` из стора.
    *   При получении парсенных данных - открытие `FgosPreviewModal.vue`.
    *   В модальном окне: отображение данных, логика сравнения (если ФГОС с таким направлением, уровнем, поколением уже есть в БД). Кнопки "Сохранить" (вызывает `saveFgosData`) и "Отменить".
    *   Кнопка "Детали" в списке ФГОС, открывающая модальное окно (возможно, тот же `FgosPreviewModal.vue` в режиме просмотра, или отдельное) с полной информацией из БД (`get_fgos_details`).

---

Начнем с бэкенда.

**1. Бэкенд: Реализация Парсера ФГОС ВО из PDF (`fgos_parser.py`)**

Для парсинга PDF текста будем использовать `pdfminer.six`. Установите ее: `pip install pdfminer.six`.

```python
# competencies_matrix/fgos_parser.py
import io
import re
from typing import Dict, List, Any, Optional
from pdfminer.high_level import extract_text

def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Парсит содержимое PDF файла ФГОС ВО (для формата 3++)
    и извлекает структурированные данные.

    Args:
        file_bytes: Содержимое PDF файла в байтах.
        filename: Имя файла (для логирования/инфо).

    Returns:
        Dict[str, Any]: Словарь с извлеченными данными или raise ValueError/Exception.
                        Структура: {
                            'metadata': { ... },
                            'uk_competencies': [{ 'code': 'УК-N', 'name': '...', 'indicators': [{'code': 'ИУК-N.M', 'formulation': '...'}] }],
                            'opk_competencies': [{ 'code': 'ОПК-N', 'name': '...', 'indicators': [{'code': 'ИОПК-N.M', 'formulation': '...'}] }],
                            'recommended_ps_codes': ['06.001', '06.015', ...],
                            'raw_text': '...' # Полный извлеченный текст
                        }
    """
    try:
        # Извлекаем весь текст из PDF
        text = extract_text(io.BytesIO(file_bytes))
        # Удаляем переносы строк в середине слов, дефисы
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
        text = text.replace('-\n', '') # Удаляем висячие дефисы
        text = re.sub(r'\n{2,}', '\n\n', text) # Схлопываем множественные переносы строк
        
        parsed_data: Dict[str, Any] = {
            'metadata': {},
            'uk_competencies': [],
            'opk_competencies': [],
            'recommended_ps_codes': [],
            'raw_text': text # Сохраняем полный текст для отладки
        }

        # --- 1. Извлечение метаданных ---
        # Ищем "Федеральный государственный образовательный стандарт высшего образования..."
        metadata_section_match = re.search(
            r'Федеральный государственный образовательный стандарт высшего образования'
            r'.*?'
            r'(УТВЕРЖДЕН\s+приказом.*?\s+от\s+(\d{2}\.\d{2}\.\d{4})\s+№\s+(\d+))'
            r'.*?'
            r'(по\s+направлению\s+подготовки\s+(\d{2}\.\d{2}\.\d{2})\s+(.*?))'
            r'.*?'
            r'(уровень\s+(бакалавриата|магистратуры|специалитета))',
            text,
            re.DOTALL | re.IGNORECASE
        )

        if metadata_section_match:
            parsed_data['metadata']['order_info'] = metadata_section_match.group(1).strip()
            parsed_data['metadata']['order_date'] = metadata_section_match.group(2)
            parsed_data['metadata']['order_number'] = metadata_section_match.group(3)
            parsed_data['metadata']['direction_code'] = metadata_section_match.group(5)
            parsed_data['metadata']['direction_name'] = metadata_section_match_text = metadata_section_match.group(6).strip()
            parsed_data['metadata']['education_level'] = metadata_section_match.group(8).strip()
            
            # Попытка определить поколение (не всегда явно указано в тексте)
            # Это требует эвристики или знания структуры документа
            # В 3++ обычно есть упоминание в преамбуле или названии
            if re.search(r'ФГОС ВО 3\+\+', filename, re.IGNORECASE) or re.search(r'ФГОС ВО поколения 3\+\+', text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3++'
            elif re.search(r'ФГОС ВО 3\+', filename, re.IGNORECASE) or re.search(r'ФГОС ВО поколения 3\+', text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3+'
            else:
                 parsed_data['metadata']['generation'] = 'не определено' # Требует ручной верификации

        # --- 2. Извлечение компетенций и индикаторов ---
        # Ищем раздел "III. Требования к результатам освоения..."
        # А затем подразделы с таблицами компетенций (УК, ОПК)
        competencies_section_match = re.search(
            r'III\.\s+Требования\s+к\s+результатам\s+освоения\s+программы.*?$(.*?)' # Содержание раздела III
            r'(^IV\.\s+Требования\s+к\s+условиям\s+реализации\s+программы|\Z)', # До следующего раздела или конца файла
            text, re.DOTALL | re.MULTILINE
        )

        if competencies_section_match:
            comp_section_text = competencies_section_match.group(1)

            # Ищем блок УК
            uk_block_match = re.search(
                r'Универсальные\s+компетенции.*?$(.*?)' # Содержание блока УК
                r'(Общепрофессиональные\s+компетенции|Профессиональные\s+компетенции|\Z)', # До следующего блока или конца раздела
                comp_section_text, re.DOTALL | re.MULTILINE
            )

            if uk_block_match:
                uk_text = uk_block_match.group(1)
                parsed_data['uk_competencies'] = parse_competency_block(uk_text, 'УК')

            # Ищем блок ОПК
            opk_block_match = re.search(
                r'Общепрофессиональные\s+компетенции.*?$(.*?)' # Содержание блока ОПК
                r'(Профессиональные\s+компетенции|\Z)', # До следующего блока или конца раздела
                comp_section_text, re.DOTALL | re.MULTILINE
            )
             # Если нет отдельного блока ОПК, но есть в общем списке, его может найти парсер parse_competency_block
            if opk_block_match:
                opk_text = opk_block_match.group(1)
                parsed_data['opk_competencies'] = parse_competency_block(opk_text, 'ОПК')


            # Если УК и ОПК не были найдены в отдельных блоках (например, они идут сплошным списком)
            # Можно попробовать пропарсить весь раздел III как единый список, а затем разделить
            if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
                 print("Warning: УК/ОПК blocks not found. Attempting to parse entire section III as combined list.")
                 all_comp_list = parse_competency_block(comp_section_text, 'УК|ОПК') # Ищем и УК, и ОПК
                 # Разделяем по типу
                 parsed_data['uk_competencies'] = [c for c in all_comp_list if c.get('code', '').startswith('УК')]
                 parsed_data['opk_competencies'] = [c for c in all_comp_list if c.get('code', '').startswith('ОПК')]


        # --- 3. Извлечение списка рекомендованных ПС ---
        # Часто находится в приложении или в конце документа
        ps_section_match = re.search(
            r'(Приложение.*?^Перечень\s+профессиональных\s+стандартов.*?$|\Z)' # Начало раздела/приложения
            r'(.*?)' # Содержимое
            r'(\Z|^)', # Конец файла или другой явный маркер (трудно найти универсальный)
            text, re.DOTALL | re.MULTILINE
        )

        if ps_section_match:
             ps_section_text = ps_section_match.group(2)

             # Ищем коды ПС в формате XX.XXX (например, 06.001)
             ps_codes = re.findall(r'\b(\d{2}\.\d{3})\b', ps_section_text)
             parsed_data['recommended_ps_codes'] = list(set(ps_codes)) # Убираем дубликаты

        return parsed_data

    except Exception as e:
        print(f"Error parsing FGOS PDF file {filename}: {e}")
        # traceback.print_exc() # Для отладки
        raise ValueError(f"Ошибка при парсинге файла ФГОС: {e}")


def parse_competency_block(text: str, comp_type_prefix: str) -> List[Dict[str, Any]]:
    """
    Парсит текст, содержащий список компетенций и индикаторов,
    используя регулярные выражения.

    Args:
        text: Текст для парсинга.
        comp_type_prefix: Префикс типа компетенции ('УК', 'ОПК', 'ПК' или 'УК|ОПК').

    Returns:
        List[Dict[str, Any]]: Список словарей компетенций с их индикаторами.
                               Структура: [{ 'code': '...', 'name': '...', 'indicators': [{'code': '...', 'formulation': '...'}] }]
    """
    competencies: List[Dict[str, Any]] = []

    # Паттерн для поиска компетенции: начало строки, префикс, номер, точка, пробел, формулировка
    # Учитываем возможное наличие индикаторов после формулировки (текст до следующей компетенции или конца блока)
    comp_pattern = re.compile(
        rf'^\s*({comp_type_prefix})-\s*(\d+)\.\s*(.*?)$' # Группа 1: Префикс, Группа 2: Номер, Группа 3: Формулировка компетенции (до конца строки)
        r'(.*?)' # Группа 4: Текст после формулировки компетенции (предполагаем, что это индикаторы)
        rf'(?=\s*({comp_type_prefix})-\s*\d+\.\s*|\Z)', # Positive lookahead: до начала следующей компетенции или конца текста
        re.DOTALL | re.MULTILINE
    )

    matches = comp_pattern.finditer(text)

    for match in matches:
        comp_code = f"{match.group(1)}-{match.group(2)}"
        comp_name = match.group(3).strip()
        indicators_text = match.group(4).strip()

        # Парсим индикаторы внутри блока индикаторов
        indicators: List[Dict[str, Any]] = []
        # Паттерн для индикатора: начало строки, код ИДК (Префикс-НомерКомпетенции.НомерИндикатора), точка, пробел, формулировка
        # Учитываем, что формулировка индикатора может быть многострочной (re.DOTALL)
        ind_pattern = re.compile(
            rf'^\s*({comp_code})\.\s*(\d+)\.\s*(.*?)$', # Группа 1: Код компетенции, Группа 2: Номер индикатора, Группа 3: Формулировка
            re.DOTALL | re.MULTILINE
        )

        ind_matches = ind_pattern.finditer(indicators_text)

        for ind_match in ind_matches:
            ind_code = f"{ind_match.group(1)}.{ind_match.group(2)}"
            ind_formulation = ind_match.group(3).strip()
            indicators.append({
                'code': ind_code,
                'formulation': ind_formulation
            })
        
        # Если индикаторы не были найдены в стандартном формате "Компетенция.Номер.",
        # но текст индикаторов существует, возможно, они просто идут списком.
        # Это более сложный кейс, требующий дополнительных эвристик, пока оставим как есть.
        # Если индикаторов не нашлось, но индикаторный текст не пустой, можно его добавить как один индикатор
        # if not indicators and indicators_text:
        #      indicators.append({'code': f'{comp_code}.?', 'formulation': indicators_text})


        competencies.append({
            'code': comp_code,
            'name': comp_name,
            'indicators': indicators
        })

    return competencies

if __name__ == '__main__':
    # Пример использования из командной строки для тестирования
    # Замените на путь к реальному файлу ФГОС
    test_file_path = 'path/to/your/fgos_09_03_01_bak_3++.pdf' # <-- CHANGE THIS

    if not os.path.exists(test_file_path):
        print(f"Тестовый файл не найден: {test_file_path}")
    else:
        print(f"Парсинг тестового файла: {test_file_path}")
        try:
            with open(test_file_path, 'rb') as f:
                file_content = f.read()
            
            parsed_data = parse_fgos_pdf(file_content, os.path.basename(test_file_path))
            
            print("\n--- Результат парсинга ---")
            print("Метаданные:", parsed_data.get('metadata'))
            print("\nУК Компетенции:", len(parsed_data.get('uk_competencies', [])))
            for comp in parsed_data.get('uk_competencies', []):
                print(f"  - {comp['code']}: {comp['name'][:50]}...")
                for ind in comp.get('indicators', []):
                    print(f"    - {ind['code']}: {ind['formulation'][:50]}...")

            print("\nОПК Компетенции:", len(parsed_data.get('opk_competencies', [])))
            for comp in parsed_data.get('opk_competencies', []):
                print(f"  - {comp['code']}: {comp['name'][:50]}...")
                for ind in comp.get('indicators', []):
                    print(f"    - {ind['code']}: {ind['formulation'][:50]}...")

            print("\nРекомендованные ПС:", parsed_data.get('recommended_ps_codes'))
            # print("\nСырой текст (превью):", parsed_data.get('raw_text', '')[:1000], "...")

        except Exception as e:
            print(f"\nОшибка при выполнении парсера: {e}")

```

**Пояснения к парсеру (`fgos_parser.py`):**

*   Использует `pdfminer.six` для извлечения всего текста из PDF.
*   Применяет базовые регулярные выражения для поиска ключевых разделов и элементов: метаданных в начале документа, раздела III с компетенциями, списка рекомендованных ПС.
*   Функция `parse_competency_block` специально разработана для поиска компетенций (по стандартному паттерну `ТИП-N. Формулировка`) и их индикаторов (по паттерну `ТИП-N.M. Формулировка`) внутри текстовых блоков.
*   Парсер **не идеален** и может некорректно работать с PDF, имеющими нестандартную структуру или сложное форматирование (таблицы, многоколоночный текст, картинки, разбивающие текст). Это **ограничение текущей реализации** и возможная точка для будущих улучшений (использовать `pdfplumber` для таблиц, например).
*   Возвращает структурированный словарь с извлеченными данными и полный сырой текст для отладки. В случае критической ошибки парсинга может выбросить `ValueError`.

**2. Бэкенд: Дополнение `competencies_matrix/logic.py`**

Добавим необходимые функции для работы с ФГОС в базу данных.

```python
# competencies_matrix/logic.py

# ... (существующие импорты) ...
from .fgos_parser import parse_fgos_pdf # Импортируем наш парсер

# --- Функции для работы с ФГОС ---

def parse_fgos_file(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """
    Оркестрирует парсинг загруженного файла ФГОС ВО.

    Args:
        file_bytes: Содержимое PDF файла в байтах.
        filename: Имя файла.

    Returns:
        Optional[Dict[str, Any]]: Структурированные данные ФГОС или None в случае ошибки парсинга.
    """
    try:
        # TODO: Добавить проверку типа файла (только PDF?)
        parsed_data = parse_fgos_pdf(file_bytes, filename)
        
        # Простая проверка, что извлечены хотя бы базовые метаданные
        if not parsed_data or not parsed_data.get('metadata'):
             print(f"parse_fgos_file: Parsing failed or returned no metadata for {filename}")
             return None

        # TODO: Добавить логику сравнения с существующим ФГОС в БД (если нужно для preview)
        # На этом этапе возвращаем просто парсенные данные
        return parsed_data
        
    except ValueError as e: # Ловим специфичные ошибки парсера
        print(f"parse_fgos_file: Parser ValueError for {filename}: {e}")
        return None
    except Exception as e:
        print(f"parse_fgos_file: Unexpected error parsing {filename}: {e}")
        traceback.print_exc()
        return None


def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    """
    Сохраняет структурированные данные ФГОС из парсера в БД.
    Обрабатывает обновление существующих записей (FgosVo, Competency, Indicator).

    Args:
        parsed_data: Структурированные данные, полученные от parse_fgos_file.
        filename: Имя исходного файла (для сохранения пути).
        session: Сессия SQLAlchemy.
        force_update: Если True, удаляет старый ФГОС и связанные сущности перед сохранением нового.
                      Если False, пытается найти существующий ФГОС и либо обновить его, либо пропустить,
                      либо вернуть ошибку (в зависимости от логики обновления).

    Returns:
        Optional[FgosVo]: Сохраненный (или обновленный) объект FgosVo или None в случае ошибки.
    """
    if not parsed_data or not parsed_data.get('metadata'):
        print("save_fgos_data: No parsed data or metadata provided.")
        return None

    metadata = parsed_data['metadata']
    fgos_number = metadata.get('order_number')
    fgos_date = metadata.get('order_date') # Строка в формате DD.MM.YYYY
    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    fgos_generation = metadata.get('generation')

    if not fgos_number or not fgos_date or not fgos_direction_code or not fgos_education_level:
        print("save_fgos_data: Missing core metadata for saving.")
        return None

    # Преобразуем дату из строки в объект Date
    try:
        fgos_date_obj = datetime.datetime.strptime(fgos_date, '%d.%m.%Y').date()
    except (ValueError, TypeError):
        print(f"save_fgos_data: Could not parse date '{fgos_date}'.")
        return None

    # --- 1. Ищем существующий ФГОС ---
    # Считаем ФГОС уникальным по комбинации код направления + уровень + номер + дата
    # Или только код направления + уровень + поколение? Поколение может быть "не определено".
    # Давайте использовать код направления, уровень, номер и дату приказа как основной ключ.
    existing_fgos = session.query(FgosVo).filter_by(
        direction_code=fgos_direction_code,
        education_level=fgos_education_level,
        number=fgos_number,
        date=fgos_date_obj # Сравниваем с объектом Date
    ).first()

    if existing_fgos:
        if force_update:
            print(f"save_fgos_data: Existing FGOS found ({existing_fgos.id}). Force update requested. Deleting old...")
            # Удаляем старый ФГОС и все связанные сущности (благодаря CASCADE DELETE)
            try:
                session.delete(existing_fgos)
                session.commit() # Коммит удаления
                print(f"save_fgos_data: Old FGOS ({existing_fgos.id}) and its dependencies deleted.")
            except SQLAlchemyError as e:
                session.rollback()
                print(f"save_fgos_data: Database error deleting old FGOS {existing_fgos.id}: {e}")
                return None
        else:
            # Если не force_update и ФГОС существует, мы его не перезаписываем
            print(f"save_fgos_data: FGOS with same code, level, number, date already exists ({existing_fgos.id}). Force update NOT requested. Skipping save.")
            # Можно вернуть существующий объект или None, в зависимости от требуемого поведения API POST /fgos/save
            # Если API должен вернуть ошибку 409 Conflict, то нужно выбросить исключение здесь.
            # Для простоты MVP вернем существующий объект и фронтенд решит, что с этим делать.
            return existing_fgos # Возвращаем существующий ФГОС


    # --- 2. Создаем или обновляем FgosVo ---
    try:
        # Создаем новый объект FgosVo
        fgos_vo = FgosVo(
            number=fgos_number,
            date=fgos_date_obj,
            direction_code=fgos_direction_code,
            direction_name=metadata.get('direction_name', 'Не указано'),
            education_level=fgos_education_level,
            generation=fgos_generation,
            file_path=filename # Сохраняем имя файла
            # TODO: Добавить другие поля метаданных, если извлекаются парсером
        )
        session.add(fgos_vo)
        session.commit() # Коммитим FgosVo, чтобы получить ID
        print(f"save_fgos_data: FGOS {fgos_vo.direction_code} ({fgos_vo.generation}) created with id {fgos_vo.id}.")

    except SQLAlchemyError as e:
        session.rollback()
        print(f"save_fgos_data: Database error creating FgosVo: {e}")
        return None

    # --- 3. Сохраняем Компетенции и Индикаторы ---
    # Получаем типы компетенций (УК, ОПК) из БД
    comp_types = {ct.code: ct for ct in session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()}

    try:
        saved_competencies = []
        # Объединяем УК и ОПК для итерации
        all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])

        for parsed_comp in all_parsed_competencies:
            comp_code = parsed_comp.get('code')
            comp_name = parsed_comp.get('name')
            parsed_indicators = parsed_comp.get('indicators', [])

            if not comp_code or not comp_name:
                print(f"save_fgos_data: Skipping competency due to missing code/name: {parsed_comp}")
                continue

            comp_prefix = comp_code.split('-')[0]
            comp_type = comp_types.get(comp_prefix)

            if not comp_type:
                print(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found in DB.")
                continue

            # Создаем компетенцию
            competency = Competency(
                competency_type_id=comp_type.id,
                fgos_vo_id=fgos_vo.id, # Связываем с новым ФГОС
                code=comp_code,
                name=comp_name,
                # description=... # Если есть описание в парсенных данных
            )
            session.add(competency)
            # db.session.flush() # Получим ID компетенции перед сохранением индикаторов

            # Создаем индикаторы для этой компетенции
            for parsed_ind in parsed_indicators:
                ind_code = parsed_ind.get('code')
                ind_formulation = parsed_ind.get('formulation')

                if not ind_code or not ind_formulation:
                    print(f"save_fgos_data: Skipping indicator due to missing code/formulation: {parsed_ind}")
                    continue

                indicator = Indicator(
                    # competency_id будет установлен SQLAlchemy после flush/commit
                    competency=competency, # Связываем с родителем
                    code=ind_code,
                    formulation=ind_formulation,
                    source=f"ФГОС {fgos_vo.direction_code} ({fgos_vo.generation})" # Указываем источник
                )
                session.add(indicator)
            
            saved_competencies.append(competency)

        session.commit() # Коммитим компетенции и индикаторы
        print(f"save_fgos_data: Saved {len(saved_competencies)} competencies and their indicators for FGOS {fgos_vo.id}.")

    except SQLAlchemyError as e:
        session.rollback()
        print(f"save_fgos_data: Database error saving competencies/indicators: {e}")
        return None # Вернем None, чтобы указать на ошибку

    # --- 4. Сохраняем рекомендованные ПС ---
    try:
        recommended_ps_codes = parsed_data.get('recommended_ps_codes', [])
        print(f"save_fgos_data: Found {len(recommended_ps_codes)} recommended PS codes.")
        
        # Ищем существующие Профстандарты по кодам
        existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(recommended_ps_codes)).all()
        ps_by_code = {ps.code: ps for ps in existing_prof_standards}

        for ps_code in recommended_ps_codes:
            prof_standard = ps_by_code.get(ps_code)
            if prof_standard:
                # Создаем связь FgosRecommendedPs
                link = FgosRecommendedPs(
                    fgos_vo_id=fgos_vo.id,
                    prof_standard_id=prof_standard.id,
                    is_mandatory=False # По умолчанию считаем рекомендованным, не обязательным
                    # description = ... # Если парсер найдет доп. описание связи
                )
                session.add(link)
            else:
                print(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Skipping link creation.")

        session.commit() # Коммитим связи ПС
        print(f"save_fgos_data: Linked {len(recommended_ps_codes)} recommended PS (if found in DB).")

    except SQLAlchemyError as e:
        session.rollback()
        print(f"save_fgos_data: Database error saving recommended PS links: {e}")
        return None # Вернем None, чтобы указать на ошибку


    # Если дошли сюда, все сохранено успешно
    return fgos_vo


def get_fgos_list() -> List[FgosVo]:
    """
    Получает список всех сохраненных ФГОС ВО.

    Returns:
        List[FgosVo]: Список объектов FgosVo.
    """
    try:
        # Просто возвращаем все ФГОС, можно добавить сортировку/фильтры позже
        fgos_list = db.session.query(FgosVo).order_by(FgosVo.direction_code, FgosVo.date.desc()).all()
        return fgos_list
    except SQLAlchemyError as e:
        print(f"Database error in get_fgos_list: {e}")
        return []


def get_fgos_details(fgos_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию по ФГОС ВО, включая связанные компетенции, индикаторы,
    и рекомендованные профстандарты.

    Args:
        fgos_id: ID ФГОС ВО.

    Returns:
        Optional[Dict[str, Any]]: Словарь с данными ФГОС или None, если не найден.
    """
    try:
        fgos = db.session.query(FgosVo).options(
            # Загружаем связанные сущности
            selectinload(FgosVo.competencies).selectinload(Competency.indicators),
            selectinload(FgosVo.recommended_ps_assoc).selectinload(FgosRecommendedPs.prof_standard)
        ).get(fgos_id)

        if not fgos:
            return None

        # Сериализуем основной объект ФГОС
        details = fgos.to_dict()

        # Сериализуем компетенции и индикаторы (фильтруем только те, что связаны с этим ФГОС)
        # Хотя relationship FgosVo.competencies уже должен был отфильтровать по FK,
        # явная проверка делает логику понятнее.
        uk_competencies_data = []
        opk_competencies_data = []

        # Сортируем компетенции и индикаторы для консистентности
        sorted_competencies = sorted(fgos.competencies, key=lambda c: c.code)

        for comp in sorted_competencies:
            # Убеждаемся, что компетенция относится к этому ФГОС и является УК/ОПК
            if comp.fgos_vo_id == fgos_id:
                 comp_dict = comp.to_dict(rules=['-fgos', '-based_on_labor_function']) # Избегаем циклических ссылок и лишних данных
                 comp_dict['indicators'] = []
                 if comp.indicators:
                      sorted_indicators = sorted(comp.indicators, key=lambda i: i.code)
                      comp_dict['indicators'] = [ind.to_dict() for ind in sorted_indicators]

                 if comp.competency_type and comp.competency_type.code == 'УК':
                      uk_competencies_data.append(comp_dict)
                 elif comp.competency_type and comp.competency_type.code == 'ОПК':
                      opk_competencies_data.append(comp_dict)
                 # ПК не должны быть напрямую связаны через fgos_vo_id, но могут быть в списке competencies
                 # Если ПК случайно сюда попали, они не будут добавлены в uk_comp или opk_comp списки

        details['uk_competencies'] = uk_competencies_data
        details['opk_competencies'] = opk_competencies_data


        # Сериализуем рекомендованные профстандарты
        recommended_ps_list = []
        if fgos.recommended_ps_assoc:
            for assoc in fgos.recommended_ps_assoc:
                if assoc.prof_standard:
                    recommended_ps_list.append({
                        'id': assoc.prof_standard.id,
                        'code': assoc.prof_standard.code,
                        'name': assoc.prof_standard.name,
                        'is_mandatory': assoc.is_mandatory,
                        'description': assoc.description,
                    })
        details['recommended_ps_list'] = recommended_ps_list

        return details

    except SQLAlchemyError as e:
        print(f"Database error in get_fgos_details for fgos_id {fgos_id}: {e}")
        # Нет необходимости в rollback для GET запросов
        return None
    except Exception as e:
        print(f"Unexpected error in get_fgos_details for fgos_id {fgos_id}: {e}")
        traceback.print_exc()
        return None


def delete_fgos(fgos_id: int, session: Session) -> bool:
    """
    Удаляет ФГОС ВО и все связанные сущности (Компетенции, Индикаторы, связи с ПС).
    Предполагается, что отношения в моделях настроены на CASCADE DELETE.

    Args:
        fgos_id: ID ФГОС ВО для удаления.
        session: Сессия SQLAlchemy.

    Returns:
        bool: True, если удаление выполнено успешно, False в противном случае.
    """
    try:
        fgos_to_delete = session.query(FgosVo).get(fgos_id)
        if not fgos_to_delete:
            print(f"delete_fgos: FGOS with id {fgos_id} not found.")
            return False

        # SQLAlchemy с CASCADE DELETE должен удалить:
        # - Competency, связанные с этим FgosVo
        # - Indicator, связанные с этими Competency (через CASCADE на Competency)
        # - FgosRecommendedPs, связанные с этим FgosVo

        session.delete(fgos_to_delete)
        session.commit()
        print(f"delete_fgos: FGOS with id {fgos_id} deleted successfully (cascading enabled).")
        return True

    except SQLAlchemyError as e:
        session.rollback()
        print(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}")
        return False
    except Exception as e:
        session.rollback()
        print(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}")
        traceback.print_exc()
        return False

```

**Пояснения к `logic.py`:**

*   Добавлены функции `parse_fgos_file` (обертка парсера), `save_fgos_data` (логика сохранения/обновления), `get_fgos_list`, `get_fgos_details`, `delete_fgos`.
*   `save_fgos_data` включает логику поиска существующего ФГОС по номеру, дате, направлению и уровню. Если `force_update=True`, старый ФГОС удаляется. Если `force_update=False` и ФГОС найден, функция возвращает существующий объект, не перезаписывая его.
*   При сохранении компетенции и индикаторы связываются с только что созданным `FgosVo` через `fgos_vo_id`. Рекомендованные ПС связываются через `FgosRecommendedPs`.
*   Настройка `ondelete="CASCADE"` в `models.py` на внешних ключах `Competency.fgos_vo_id` и `FgosRecommendedPs.fgos_vo_id` (и, возможно, от `Competency` к `Indicator`) **критически важна** для корректной работы `delete_fgos`. Убедитесь, что миграции Alembic правильно настроены для создания этих каскадов.

**3. Бэкенд: Дополнение `competencies_matrix/routes.py`**

Добавим новые маршруты.

```python
# competencies_matrix/routes.py

# ... (существующие импорты) ...
from .logic import (
    get_educational_programs_list, get_program_details, 
    get_matrix_for_aup, update_matrix_link,
    create_competency, create_indicator,
    parse_prof_standard_file,
    parse_fgos_file, save_fgos_data, get_fgos_list, get_fgos_details, delete_fgos
)
from auth.logic import login_required, approved_required, admin_only # Импортируем admin_only

# ... (существующая регистрация Blueprint) ...

# Группа эндпоинтов для работы с образовательными программами (ОП)
# ... (существующие эндпоинты /programs, /programs/<int:program_id>) ...

# Группа эндпоинтов для работы с матрицей компетенций
# ... (существующие эндпоинты /matrix/<int:aup_id>, /matrix/link) ...

# Группа эндпоинтов для работы с компетенциями и индикаторами
# ... (существующие эндпоинты /competencies (POST), /indicators (POST)) ...

# Группа эндпоинтов для работы с профессиональными стандартами (ПС)
# ... (существующий эндпоинт /profstandards/upload) ...

# --- Новая группа эндпоинтов для работы с ФГОС ВО ---
@competencies_matrix_bp.route('/fgos', methods=['GET'])
@login_required
@approved_required
# @admin_only # Возможно, просмотр доступен не только админам, но и методистам
def get_all_fgos():
    """Получение списка всех загруженных ФГОС ВО"""
    fgos_list = get_fgos_list()
    # Сериализуем результат в список словарей
    # Используем to_dict из BaseModel
    result = [f.to_dict() for f in fgos_list]
    return jsonify(result)

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['GET'])
@login_required
@approved_required
# @admin_only # Просмотр деталей тоже может быть шире
def get_fgos_details_route(fgos_id):
    """Получение детальной информации по ФГОС ВО"""
    details = get_fgos_details(fgos_id)
    if not details:
        return jsonify({"error": "ФГОС ВО не найден"}), 404
    return jsonify(details)

@competencies_matrix_bp.route('/fgos/upload', methods=['POST'])
@login_required
@approved_required
@admin_only # Загрузка и парсинг нового ФГОС - действие администратора
def upload_fgos():
    """
    Загрузка PDF файла ФГОС ВО, парсинг и возврат данных для предпросмотра.
    Не сохраняет данные в БД автоматически.
    Принимает multipart/form-data с полем 'file'.
    """
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400

    # TODO: Добавить проверку расширения файла на .pdf
    
    try:
        file_bytes = file.read()
        parsed_data = parse_fgos_file(file_bytes, file.filename)

        if not parsed_data:
            return jsonify({"error": "Не удалось распарсить файл ФГОС или извлечь основные данные"}), 400

        # TODO: Добавить в ответ информацию о существующем ФГОС, если найден (для сравнения на фронтенде)
        # Можно вызвать get_fgos_details, если найден ФГОС с такими же ключевыми параметрами
        
        return jsonify(parsed_data), 200 # Возвращаем парсенные данные

    except Exception as e:
        logger.error(f"Error processing FGOS upload for {file.filename}: {e}", exc_info=True)
        return jsonify({"error": f"Ошибка сервера при обработке файла: {e}"}), 500


@competencies_matrix_bp.route('/fgos/save', methods=['POST'])
@login_required
@approved_required
@admin_only # Сохранение ФГОС - действие администратора
def save_fgos():
    """
    Сохранение структурированных данных ФГОС в БД после подтверждения пользователя.
    Принимает JSON с парсенными данными и опциями.
    """
    data = request.get_json()
    # Ожидаем JSON: {'parsed_data': {...}, 'filename': '...', 'options': {'force_update': true/false}}
    
    parsed_data = data.get('parsed_data')
    filename = data.get('filename')
    options = data.get('options', {})
    
    if not parsed_data or not filename:
        return jsonify({"error": "Некорректные данные для сохранения"}), 400

    try:
        # Вызываем функцию сохранения данных
        # Передаем сессию явно
        saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=options.get('force_update', False))

        if saved_fgos is None:
            # Если save_fgos_data вернула None, значит произошла ошибка БД или валидации внутри
            # (логирование ошибки должно быть внутри save_fgos_data)
            return jsonify({"error": "Ошибка при сохранении данных ФГОС в базу данных"}), 500
            
        # Если save_fgos_data вернула объект, который уже существовал и force_update=False,
        # то это не ошибка, просто дубликат. Фронтенд должен был это обработать на шаге preview.
        # Но API все равно должен вернуть информацию.
        # Проверяем, был ли это новый объект или существующий
        is_new = saved_fgos._sa_instance_state.key is None or saved_fgos._sa_instance_state.key.persistent is None

        return jsonify({
            "success": True,
            "fgos_id": saved_fgos.id,
            "message": "Данные ФГОС успешно сохранены." if is_new else "Данные ФГОС успешно обновлены."
        }), 201 # 201 Created или 200 OK, 201 более уместен для создания/обновления


    except Exception as e:
        logger.error(f"Error saving FGOS data from file {filename}: {e}", exc_info=True)
        # Если произошла ошибка, и она не была поймана внутри save_fgos_data с откатом, откатываем здесь
        db.session.rollback()
        return jsonify({"error": f"Неожиданная ошибка сервера при сохранении: {e}"}), 500

@competencies_matrix_bp.route('/fgos/<int:fgos_id>', methods=['DELETE'])
@login_required
@approved_required
@admin_only # Удаление ФГОС - действие администратора
def delete_fgos_route(fgos_id):
    """Удаление ФГОС ВО по ID"""
    try:
        deleted = delete_fgos(fgos_id, db.session)
        if deleted:
            return jsonify({"success": True, "message": "ФГОС успешно удален"}), 200
        else:
            return jsonify({"success": False, "error": "ФГОС не найден или не удалось удалить"}), 404

    except Exception as e:
        logger.error(f"Error deleting FGOS {fgos_id}: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"success": False, "error": f"Неожиданная ошибка сервера при удалении: {e}"}), 500

```

**Пояснения к `routes.py`:**

*   Добавлены эндпоинты `GET /fgos`, `GET /fgos/<id>`, `POST /fgos/upload`, `POST /fgos/save`, `DELETE /fgos/<id>`.
*   Эндпоинт `/fgos/upload` принимает файл, вызывает парсер и возвращает **только парсенные данные** в формате JSON (без сохранения в БД).
*   Эндпоинт `/fgos/save` принимает JSON с парсенными данными и флагом `force_update`, вызывает `save_fgos_data` для сохранения в БД.
*   Применены декораторы `@login_required`, `@approved_required`. Для операций загрузки/сохранения/удаления ФГОС добавлен `@admin_only`.
*   Используется логгер для записи ошибок. Транзакции управляются в `logic.py` и в route при необходимости отката в случае неожиданной ошибки.

**4. Бэкенд: Дополнение CLI команды импорта ФГОС (`cli_commands/fgos_import.py`)**

Создадим новый файл для этой команды.

```python
# cli_commands/fgos_import.py
import click
from flask.cli import with_appcontext
import os
import traceback
import datetime

# --- Импортируем необходимые компоненты ---
from maps.models import db
from competencies_matrix.logic import parse_fgos_file, save_fgos_data, delete_fgos
from competencies_matrix.models import FgosVo # Нужно для поиска
import logging

logger = logging.getLogger(__name__)

@click.command(name='import-fgos')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force import/overwrite if FGOS with same identifying data exists.')
@click.option('--delete-only', is_flag=True, default=False,
              help='Only delete FGOS if it exists, do not import.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform read and validation without saving or deleting.')
@with_appcontext
def import_fgos_command(filepath, force, delete_only, dry_run):
    """
    Импортирует данные ФГОС ВО из PDF-файла, парсит и сохраняет в БД.
    Поиск существующего ФГОС производится по коду направления, уровню, номеру и дате приказа.

    FILEPATH: Путь к PDF файлу ФГОС для импорта.
    """
    print(f"\n---> Starting FGOS import from: {filepath}")
    filename = os.path.basename(filepath)

    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved/deleted from the database. <<<")

    try:
        # 1. Чтение и парсинг Excel файла
        print(f"Reading and parsing FGOS file: {filename}...")
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
        
        # Вызываем парсер
        # Ловим ValueError от парсера
        parsed_data = parse_fgos_file(file_bytes, filename)

        if not parsed_data:
            print("\n!!! PARSING FAILED !!!")
            print(f"   - Could not parse file or extract essential metadata from '{filename}'.")
            print("   - Please check the file format and content.")
            if not dry_run:
                db.session.rollback() # Откат, если сессия была изменена (хотя parse не меняет)
            return

        print("   - File parsed successfully.")
        
        # Выводим извлеченные метаданные для информации
        metadata = parsed_data.get('metadata', {})
        print("   - Extracted Metadata:")
        for key, value in metadata.items():
             print(f"     - {key}: {value}")
             
        if delete_only:
             # В режиме delete-only парсинг нужен только для получения ключевых данных для поиска
             print("\n---> DELETE ONLY mode enabled.")
             fgos_to_delete = None
             if metadata.get('direction_code') and metadata.get('education_level') and metadata.get('order_number') and metadata.get('order_date'):
                  try:
                       fgos_date_obj = datetime.datetime.strptime(metadata['order_date'], '%d.%m.%Y').date()
                       fgos_to_delete = db.session.query(FgosVo).filter_by(
                            direction_code=metadata['direction_code'],
                            education_level=metadata['education_level'],
                            number=metadata['order_number'],
                            date=fgos_date_obj
                       ).first()
                  except (ValueError, TypeError):
                        print(f"   - Could not parse date '{metadata['order_date']}' for lookup. Cannot perform delete.")
                        fgos_to_delete = None # Устанавливаем None, если дату не распарсили
                  except SQLAlchemyError as e:
                        print(f"   - Database error during lookup for delete: {e}")
                        db.session.rollback()
                        return
             else:
                  print("   - Missing identifying metadata for lookup. Cannot perform delete.")
             
             if fgos_to_delete:
                  if not dry_run:
                       print(f"   - Found existing FGOS (id: {fgos_to_delete.id}, code: {fgos_to_delete.direction_code}). Deleting...")
                       deleted = delete_fgos(fgos_to_delete.id, db.session)
                       if deleted:
                            print("   - FGOS deleted successfully.")
                       else:
                            print("   - Failed to delete FGOS (check logs).")
                  else:
                       print(f"   - DRY RUN: Found existing FGOS (id: {fgos_to_delete.id}). Would delete.")
             else:
                  print("   - No existing FGOS found matching identifying metadata. Nothing to delete.")

             print("---> FGOS import finished (delete only mode).\n")
             return # Выходим после удаления

        # 2. Сохранение данных в БД (только если не dry-run и не delete-only)
        if not dry_run:
            print("Saving data to database...")
            
            # Вызываем функцию сохранения данных
            # Передаем сессию явно
            saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=force)

            if saved_fgos is None:
                 print("\n!!! SAVE FAILED !!!")
                 print("   - Error occurred while saving FGOS data (check logs).")
                 # save_fgos_data уже откатил транзакцию при ошибке БД
            else:
                 print(f"\n---> FGOS from '{filename}' imported successfully with ID {saved_fgos.id}!\n")

        else:
            print("   - Skipping database save due to --dry-run flag.")
            print(f"---> DRY RUN for '{filename}' completed successfully (parsing passed).\n")


    except FileNotFoundError:
        print(f"\n!!! ERROR: File not found at '{filepath}' !!!")
    except ImportError as e:
        print(f"\n!!! ERROR: Missing dependency for reading PDF files: {e} !!!")
        print("   - Please ensure 'pdfminer.six' is installed.")
    except ValueError as e: # Ловим ошибки от parse_fgos_file
        print(f"\n!!! PARSING ERROR: {e} !!!")
        if not dry_run:
             db.session.rollback() # Откат, если сессия была изменена
    except Exception as e:
        if not dry_run:
            db.session.rollback()
            print("   - Database transaction might have been rolled back.")
        print(f"\n!!! UNEXPECTED ERROR during import: {e} !!!")
        print("   - Database transaction might have been rolled back.")
        traceback.print_exc()

```

**Пояснения к `fgos_import.py`:**

*   Создана новая CLI команда `flask import-fgos <filepath>`.
*   Принимает путь к PDF файлу.
*   Флаг `--force` (перезапись): При передаче, если ФГОС с теми же ключевыми параметрами найден, он будет удален перед сохранением нового (логика в `save_fgos_data`).
*   Флаг `--delete-only` (только удаление): При передаче, парсит файл для получения ключевых параметров ФГОС, и если найден соответствующий ФГОС в БД, вызывает `delete_fgos` и выходит. Не производит сохранения.
*   Флаг `--dry-run`: Выполняет только парсинг и валидацию, но не затрагивает базу данных.
*   Использует функции `parse_fgos_file`, `save_fgos_data`, `delete_fgos` из `competencies_matrix.logic`.
*   Настроена обработка ошибок и логирование.
*   Важно добавить эту команду в `app.py` для регистрации:

```python
# app.py
# ... (существующие импорты и инициализация) ...

# --- Import CLI Commands ---
# ... (существующие импорты команд) ...
from cli_commands.fgos_import import import_fgos_command # Импортируем новую команду

# ... (существующая регистрация blueprints) ...

# ... (существующие обработчики ошибок) ...

# --- Базовый маршрут ---
# ...

# Регистрируем команды сидера и ансидера
# ... (существующая регистрация команд) ...
app.cli.add_command(import_fgos_command) # Регистрируем новую команду ФГОС

# Точка входа для запуска через `python app.py`
if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)

```

**5. Frontend: Дополнение Store и API Service**

Добавим методы для новых эндпоинтов в Pinia store и API service.

```typescript
// src/services/CompetenciesApi.ts

// ... (существующие импорты) ...

/**
 * Service for interacting with the Competencies Matrix API
 * This service contains methods for all competencies_matrix endpoints
 */
class CompetenciesApi {
  // ... (существующие методы) ...

  /**
   * Get a list of all saved FGOS VO records
   * @returns Promise with array of FGOS records
   */
  async getFgosList() {
    const { data } = await axios.get('/competencies/fgos')
    return data
  }

  /**
   * Get detailed information about a specific FGOS VO record
   * @param fgosId ID of the FGOS VO record
   * @returns Promise with FGOS details including competencies, indicators, recommended PS
   */
  async getFgosDetails(fgosId) {
    const { data } = await axios.get(`/competencies/fgos/${fgosId}`)
    return data
  }

  /**
   * Upload a FGOS VO PDF file for parsing (does NOT save to DB)
   * @param file File object to upload
   * @returns Promise with parsed FGOS data or error
   */
  async uploadFgosFile(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    
    const { data } = await axios.post(
      '/competencies/fgos/upload', 
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      }
    )
    return data // This should return parsed data, not success status
  }

  /**
   * Save parsed FGOS data to the database
   * @param parsedData Parsed FGOS data object
   * @param filename Original filename
   * @param options Save options (e.g., { force_update: boolean })
   * @returns Promise with operation result
   */
  async saveFgosData(parsedData: any, filename: string, options: { force_update: boolean } = { force_update: false }) {
     // Send the parsed data and options to the save endpoint
    const { data } = await axios.post(
      '/competencies/fgos/save', 
      {
        parsed_data: parsedData,
        filename: filename,
        options: options
      }
    )
    return data // Should return success status and fgos_id
  }

  /**
   * Delete a FGOS VO record
   * @param fgosId ID of the FGOS VO record to delete
   * @returns Promise with operation result
   */
  async deleteFgos(fgosId) {
    const { data } = await axios.delete(`/competencies/fgos/${fgosId}`)
    return data // Should return success status
  }

  // ... (остальные методы CompetenciesApi) ...
}

// Экспортируем как синглтон
export default new CompetenciesApi()
```

```typescript
// src/stores/competenciesMatrix.ts

// ... (существующие импорты и интерфейсы) ...
import CompetenciesApi from '@/services/CompetenciesApi'; // Импорт нашего нового сервиса API ФГОС

// Define interface for FGOS VO
interface FgosVo {
  id: number | string;
  number: string;
  date: string; // Store as string for now
  direction_code: string;
  direction_name: string;
  education_level: string;
  generation: string;
  file_path?: string;
  created_at: string;
  updated_at: string;
  // Add nested structures if needed for details view
  uk_competencies?: any[];
  opk_competencies?: any[];
  recommended_ps_list?: any[];
}


/**
 * Pinia store for managing competencies matrix state
 * This store handles state management for educational programs, matrix data, and interactions
 * 
 * Backend endpoints used:
 * ... (existing endpoints) ...
 * 
 * - GET /competencies/fgos - Get list of saved FGOS
 *   Implementation: maps_backend/competencies_matrix/routes.py (get_all_fgos)
 *   Logic: maps_backend/competencies_matrix/logic.py (get_fgos_list)
 * 
 * - GET /competencies/fgos/<fgos_id> - Get details of a specific FGOS
 *   Implementation: maps_backend/competencies_matrix/routes.py (get_fgos_details_route)
 *   Logic: maps_backend/competencies_matrix/logic.py (get_fgos_details)
 * 
 * - POST /competencies/fgos/upload - Upload and parse FGOS file
 *   Implementation: maps_backend/competencies_matrix/routes.py (upload_fgos)
 *   Logic: maps_backend/competencies_matrix/logic.py (parse_fgos_file)
 * 
 * - POST /competencies/fgos/save - Save parsed FGOS data to DB
 *   Implementation: maps_backend/competencies_matrix/routes.py (save_fgos)
 *   Logic: maps_backend/competencies_matrix/logic.py (save_fgos_data)
 * 
 * - DELETE /competencies/fgos/<fgos_id> - Delete FGOS
 *   Implementation: maps_backend/competencies_matrix/routes.py (delete_fgos_route)
 *   Logic: maps_backend/competencies_matrix/logic.py (delete_fgos)
 * 
 * Database tables accessed:
 * ... (existing tables) ...
 * - competencies_fgos_vo
 */
export const useCompetenciesMatrixStore = defineStore('competenciesMatrix', {
  state: () => ({
    // ... (существующие состояния) ...
    
    // FGOS related state
    fgosList: [] as FgosVo[],
    selectedFgosId: null as number | string | null,
    selectedFgosDetails: null as FgosVo | null, // Use the FgosVo interface
    
    // State for FGOS Upload/Preview modal
    showFgosPreviewModal: false,
    fgosParsedData: null as any | null, // Parsed data before saving
    fgosUploadFilename: '' as string, // Filename of the uploaded FGOS
    fgosExistingRecord: null as FgosVo | null, // Existing FGOS found during upload preview
    
    // Loading/Error states for FGOS
    isLoadingFgosList: false,
    isLoadingFgosDetails: false,
    isLoadingFgosUpload: false,
    isSavingFgos: false,
    fgosError: null as string | null,
  }),
  
  getters: {
    // ... (существующие геттеры) ...
    
    getFgosList: (state) => state.fgosList,
    getSelectedFgosDetails: (state) => state.selectedFgosDetails,
    
    // Getters for FGOS Upload/Preview modal
    getShowFgosPreviewModal: (state) => state.showFgosPreviewModal,
    getFgosParsedData: (state) => state.fgosParsedData,
    getFgosUploadFilename: (state) => state.fgosUploadFilename,
    getFgosExistingRecord: (state) => state.fgosExistingRecord,
  },
  
  actions: {
    // ... (существующие экшены) ...

    // --- Actions for FGOS VO ---
    
    /**
     * Fetch the list of all saved FGOS VO records
     */
    async fetchFgosList() {
      try {
        this.isLoadingFgosList = true;
        this.fgosError = null;
        
        const data = await CompetenciesApi.getFgosList(); // Используем новый сервис
        this.fgosList = data;
        
        return data;
      } catch (error: any) {
        console.error("Error fetching FGOS list:", error);
        this.fgosError = error.message || "Failed to fetch FGOS list";
        throw error;
      } finally {
        this.isLoadingFgosList = false;
      }
    },
    
    /**
     * Fetch details for a specific FGOS VO record
     * @param fgosId ID of the FGOS VO record
     */
    async fetchFgosDetails(fgosId) {
      try {
        this.isLoadingFgosDetails = true;
        this.fgosError = null;
        this.selectedFgosId = fgosId;
        this.selectedFgosDetails = null; // Clear previous details
        
        const data = await CompetenciesApi.getFgosDetails(fgosId); // Используем новый сервис
        this.selectedFgosDetails = data;
        
        console.log("FGOS details fetched:", data);
        return data;
      } catch (error: any) {
        console.error("Error fetching FGOS details:", error);
        this.fgosError = error.message || "Failed to fetch FGOS details";
        throw error;
      } finally {
        this.isLoadingFgosDetails = false;
      }
    },
    
    /**
     * Upload and parse a FGOS VO PDF file.
     * Shows a preview modal with parsed data.
     * @param file File object to upload
     */
    async uploadFgosFile(file: File) {
      try {
        this.isLoadingFgosUpload = true;
        this.fgosError = null;
        this.fgosParsedData = null; // Clear previous parsed data
        this.fgosUploadFilename = ''; // Clear previous filename
        this.fgosExistingRecord = null; // Clear previous existing record

        const parsedData = await CompetenciesApi.uploadFgosFile(file); // Используем новый сервис

        if (parsedData && parsedData.metadata) {
            this.fgosParsedData = parsedData;
            this.fgosUploadFilename = file.name;

            // TODO: Implement logic to find if this FGOS already exists in DB
            // based on parsedData.metadata (e.g., direction_code, education_level, order_number, order_date)
            // If found, fetch the existing record and set this.fgosExistingRecord
            const metadata = parsedData.metadata;
            if (metadata.direction_code && metadata.education_level && metadata.order_number && metadata.order_date) {
                 try {
                      // Find existing FGOS in the already loaded list
                      const existing = this.fgosList.find(fgos => 
                          fgos.direction_code === metadata.direction_code &&
                          fgos.education_level === metadata.education_level &&
                          fgos.number === metadata.order_number &&
                          // Compare dates, maybe convert string date from metadata to Date object
                          new Date(fgos.date).getTime() === new Date(metadata.order_date.split('.').reverse().join('-')).getTime() // Simple date comparison
                      );
                      if (existing) {
                           // If found in list, fetch full details for preview comparison
                           this.fgosExistingRecord = await CompetenciesApi.getFgosDetails(existing.id);
                      }
                 } catch(lookupError) {
                     console.warn("Could not perform lookup for existing FGOS:", lookupError);
                     // Continue without existing record if lookup fails
                 }
            }


            this.showFgosPreviewModal = true; // Show the preview modal
        } else {
            this.fgosError = "Failed to parse FGOS file or extracted no data.";
            throw new Error(this.fgosError);
        }
        
      } catch (error: any) {
        console.error("Error uploading FGOS file:", error);
        this.fgosError = this.fgosError || error.message || "Failed to upload and parse FGOS file";
        throw error;
      } finally {
        this.isLoadingFgosUpload = false;
      }
    },
    
    /**
     * Save parsed FGOS data to the database after user confirmation.
     * @param options Save options (e.g., { force_update: boolean })
     */
    async saveFgosData(options: { force_update: boolean } = { force_update: false }) {
        if (!this.fgosParsedData || !this.fgosUploadFilename) {
             console.error("saveFgosData: No parsed data available to save.");
             return; // Cannot save if no data
        }
        
        try {
            this.isSavingFgos = true;
            this.fgosError = null;
            
            const result = await CompetenciesApi.saveFgosData(this.fgosParsedData, this.fgosUploadFilename, options); // Используем новый сервис
            
            console.log("FGOS save result:", result);
            
            // After successful save, refresh the FGOS list
            await this.fetchFgosList();
            
            this.showFgosPreviewModal = false; // Close the modal on success
            this.fgosParsedData = null; // Clear parsed data
            this.fgosUploadFilename = ''; // Clear filename
            this.fgosExistingRecord = null; // Clear existing record info

            // TODO: Show success message
            
            return result;
        } catch (error: any) {
            console.error("Error saving FGOS data:", error);
            this.fgosError = error.message || "Failed to save FGOS data";
            throw error;
        } finally {
            this.isSavingFgos = false;
        }
    },
    
    /**
     * Delete a FGOS VO record
     * @param fgosId ID of the FGOS VO record to delete
     */
    async deleteFgos(fgosId) {
      // TODO: Implement delete logic and confirmation modal
      try {
          this.loading = true; // Use general loading for simplicity
          this.fgosError = null;
          
          const result = await CompetenciesApi.deleteFgos(fgosId); // Используем новый сервис
          
          console.log("FGOS delete result:", result);
          
          // Remove from the local list
          this.fgosList = this.fgosList.filter(fgos => fgos.id !== fgosId);

          // If the deleted FGOS was currently viewed, clear details
          if (this.selectedFgosId === fgosId) {
              this.selectedFgosDetails = null;
              this.selectedFgosId = null;
          }

          // TODO: Show success message
          
          return result;
      } catch (error: any) {
          console.error("Error deleting FGOS:", error);
          this.fgosError = error.message || "Failed to delete FGOS";
          throw error;
      } finally {
          this.loading = false;
      }
    },

    /**
     * Clear the FGOS upload/preview state (e.g., when closing modal)
     */
    clearFgosPreviewState() {
        this.showFgosPreviewModal = false;
        this.fgosParsedData = null;
        this.fgosUploadFilename = '';
        this.fgosExistingRecord = null;
        this.fgosError = null; // Clear error as well
    }
  }
})
```

**Пояснения к Store:**

*   Добавлено состояние для списка ФГОС (`fgosList`), деталей выбранного ФГОС (`selectedFgosDetails`), и состояния для модального окна предпросмотра (`showFgosPreviewModal`, `fgosParsedData`, `fgosUploadFilename`, `fgosExistingRecord`).
*   Добавлены экшены `fetchFgosList`, `fetchFgosDetails`, `uploadFgosFile`, `saveFgosData`, `deleteFgos`, `clearFgosPreviewState`.
*   `uploadFgosFile` вызывает API для парсинга, и если успешно, заполняет состояние для модального окна предпросмотра (`fgosParsedData`, `fgosUploadFilename`). **Необходимо добавить логику поиска существующего ФГОС в `fgosList` и загрузки его деталей (`fgosExistingRecord`) для сравнения в модальном окне.**
*   `saveFgosData` вызывает API для сохранения, а затем обновляет список ФГОС (`fetchFgosList`) и закрывает модальное окно.
*   `deleteFgos` вызывает API для удаления и удаляет запись из локального списка.
*   `clearFgosPreviewState` сбрасывает состояние, связанное с модальным окном.

**6. Frontend: Реализация UI для Управления ФГОС**

Создадим страницу списка ФГОС (`FgosView.vue`) и компонент модального окна предпросмотра (`FgosPreviewModal.vue`).

```vue
<!-- src/views/competencies/FgosView.vue -->
<template>
  <div class="FgosView">
    <h2>ФГОС ВО</h2>
    
    <div class="FgosView__header-actions">
        <!-- Кнопка загрузки нового ФГОС -->
        <Button
            label="Загрузить ФГОС"
            icon="mdi mdi-upload"
            @click="openFileUpload"
            :loading="isLoadingFgosUpload"
            :disabled="isLoadingFgosUpload"
        />
         <input
            ref="fileInput"
            type="file"
            accept=".pdf"
            @change="handleFileUpload"
            style="display: none;"
         />
    </div>

    <!-- Список ФГОС -->
    <div class="FgosView__content">
      <div class="FgosView__table-wrapper">
        <DataTable
          :value="fgosList"
          :loading="isLoadingFgosList"
          dataKey="id"
          class="FgosView__table"
          :paginator="fgosList.length > 10"
          :rows="10"
          stripedRows
          removableSort
          showGridlines
          v-model:sortField="sortField"
          v-model:sortOrder="sortOrder"
          scrollable
          scrollHeight="flex"
        >
        <Column field="number" header="Номер приказа" :sortable="true"></Column>
        <Column field="date" header="Дата приказа" :sortable="true">
            <template #body="slotProps">
                {{ formatDate(slotProps.data.date) }}
            </template>
        </Column>
        <Column field="direction_code" header="Код направления" :sortable="true"></Column>
        <Column field="direction_name" header="Название направления" :sortable="true"></Column>
        <Column field="education_level" header="Уровень" :sortable="true"></Column>
        <Column field="generation" header="Поколение" :sortable="true"></Column>
        <Column headerStyle="width: 8rem" header="Действия">
          <template #body="slotProps">
            <div class="action-buttons">
              <Button
                icon="mdi mdi-eye"
                class="p-button-sm action-button"
                @click.stop="viewFgosDetails(slotProps.data)"
                v-tooltip.top="'Просмотреть детали ФГОС'"
              />
               <Button
                icon="mdi mdi-delete"
                class="p-button-sm p-button-danger action-button"
                @click.stop="confirmDeleteFgos(slotProps.data)"
                v-tooltip.top="'Удалить ФГОС'"
              />
            </div>
          </template>
        </Column>
      </DataTable>

      <!-- Empty state -->
      <div v-if="!isLoadingFgosList && fgosList.length === 0" class="FgosView__empty">
        <i class="mdi mdi-file-document-outline text-4xl text-gray-400"></i>
        <p>Нет загруженных ФГОС ВО</p>
      </div>
    </div>
    
    <!-- Модальное окно предпросмотра / деталей ФГОС -->
    <FgosPreviewModal
        v-model:visible="showFgosPreviewModal"
        :parsed-data="fgosParsedData"
        :filename="fgosUploadFilename"
        :existing-fgos-record="fgosExistingRecord"
        :is-view-mode="!fgosParsedData"
        @save="saveFgosData"
        @hide="clearFgosPreviewState"
    />

    <!-- Модальное окно подтверждения удаления -->
    <ConfirmDialog group="deleteFgosConfirmation"></ConfirmDialog>

  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useCompetenciesMatrixStore } from '@/stores/competenciesMatrix';
import CompetenciesApi from '@/services/CompetenciesApi'; // Импорт API сервис
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog'; // Возможно, не понадобится, если используем модалку из компонента
import ProgressSpinner from 'primevue/progressspinner'; // Возможно, не понадобится
import Tooltip from 'primevue/tooltip'; // Директива
import FgosPreviewModal from '@/components/competencies/FgosPreviewModal.vue'; // Наш компонент модального окна
import ConfirmDialog from 'primevue/confirmdialog'; // Для модалки подтверждения
import { useConfirm } from "primevue/useconfirm"; // Для модалки подтверждения
import { useToast } from "primevue/usetoast"; // Для сообщений пользователю

const router = useRouter();
const competenciesStore = useCompetenciesMatrixStore();
const confirm = useConfirm(); // Для модалки подтверждения
const toast = useToast(); // Для сообщений пользователю

// State from store
const fgosList = computed(() => competenciesStore.fgosList);
const isLoadingFgosList = computed(() => competenciesStore.isLoadingFgosList);
const isLoadingFgosUpload = computed(() => competenciesStore.isLoadingFgosUpload);
const showFgosPreviewModal = computed({ // Связываем видимость модалки с состоянием в сторе
    get: () => competenciesStore.getShowFgosPreviewModal,
    set: (value) => { if (!value) competenciesStore.clearFgosPreviewState(); } // При закрытии - очищаем состояние
});
const fgosParsedData = computed(() => competenciesStore.getFgosParsedData);
const fgosUploadFilename = computed(() => competenciesStore.getFgosUploadFilename);
const fgosExistingRecord = computed(() => competenciesStore.getFgosExistingRecord);


// Local state
const sortField = ref('direction_code'); // Default sort field
const sortOrder = ref(1); // Default sort order (1 for ascending, -1 for descending)
const fileInput = ref(null); // Ссылка на скрытый input type="file"

// Methods
const fetchFgosList = async () => {
  await competenciesStore.fetchFgosList();
};

const openFileUpload = () => {
    fileInput.value.click(); // Инициируем клик по скрытому input[type="file"]
};

const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (file) {
        await competenciesStore.uploadFgosFile(file);
        // Очищаем input, чтобы можно было загрузить тот же файл повторно
        event.target.value = null;
    }
};

const viewFgosDetails = async (fgos) => {
    // Открываем модальное окно в режиме просмотра, передавая ID
    // FgosPreviewModal должен уметь загрузить детали по ID, если parsedData нет, но передан ID
    // Или же мы фетчим детали здесь и передаем их как prop existing-fgos-record
    // Давайте фетчим детали здесь и передаем их в модалку, используя поле existing-fgos-record
    
    // Устанавливаем state для модалки в режим просмотра
    competenciesStore.showFgosPreviewModal = true; // Открываем модалку
    competenciesStore.fgosParsedData = null; // Указываем, что это не предпросмотр нового файла
    competenciesStore.fgosUploadFilename = ''; // Указываем, что это не новый файл
    
    // Загружаем детали существующего ФГОС
    await competenciesStore.fetchFgosDetails(fgos.id); // fetchFgosDetails сохранит результат в selectedFgosDetails
    // FgosPreviewModal будет использовать getSelectedFgosDetails геттер, если parsedData нет
};


const confirmDeleteFgos = (fgos) => {
    confirm.require({
        group: 'deleteFgosConfirmation',
        message: `Вы уверены, что хотите удалить ФГОС "${fgos.direction_code} (${fgos.generation}) Приказ №${fgos.number} от ${formatDate(fgos.date)}"? Это действие необратимо и удалит все связанные компетенции и индикаторы.`,
        header: 'Подтверждение удаления',
        icon: 'mdi mdi-information-outline',
        acceptClass: 'p-button-danger',
        acceptLabel: 'Удалить',
        rejectLabel: 'Отмена',
        accept: async () => {
            await competenciesStore.deleteFgos(fgos.id);
            // Уведомление об успехе показывается в экшене стора или здесь
             toast.add({severity:'success', summary: 'Удалено', detail:'ФГОС успешно удален', life: 3000});
        },
        reject: () => {
            // Действия при отмене
        }
    });
};


const saveFgosData = async (options) => {
    // Этот метод вызывается из FgosPreviewModal при нажатии "Сохранить"
    // options = { force_update: boolean }
    try {
        await competenciesStore.saveFgosData(options);
        // Успех обрабатывается в сторе (закрытие модалки, обновление списка)
        toast.add({severity:'success', summary: 'Сохранено', detail:'Данные ФГОС успешно сохранены', life: 3000});
    } catch (error) {
        // Ошибка обрабатывается в сторе и/или здесь
         toast.add({severity:'error', summary: 'Ошибка', detail:'Не удалось сохранить данные ФГОС', life: 3000});
    }
};

const clearFgosPreviewState = () => {
    // Этот метод вызывается при скрытии модалки
    competenciesStore.clearFgosPreviewState();
    // Важно: selectedFgosDetails очищается в сторе при закрытии модалки,
    // если это был режим просмотра, или при начале нового upload
};

// Helper to format date (reuse from other helpers)
const formatDate = (dateString) => {
    if (!dateString) return 'Не указано';
    try {
         const date = new Date(dateString);
         return date.toLocaleDateString('ru-RU', { year: 'numeric', month: 'long', day: 'numeric' });
    } catch (e) {
         console.error("Failed to format date:", dateString, e);
         return dateString; // Return original if formatting fails
    }
};


// Lifecycle hook
onMounted(() => {
  fetchFgosList(); // Fetch list of FGOS on mount
});

// Добавляем директиву v-tooltip локально
const vTooltip = Tooltip;

</script>

<style lang="scss" scoped>
@import '@styles/_variables.scss';

.FgosView {
  display: flex;
  flex-direction: column;
  height: 100%;
  
  h2 {
    margin-bottom: 16px;
    
    @media (max-width: 640px) {
      font-size: 1.3rem;
      margin-bottom: 12px;
    }
  }
  
   &__header-actions {
       margin-bottom: 16px;
   }

  &__content {
    flex: 1;
    overflow: auto;
    min-width: 0; // Fix flexbox overflow issues
  }
  
  &__table-wrapper {
    overflow-x: auto; // Enable horizontal scrolling
    width: 100%;
    margin-bottom: 16px;
    -webkit-overflow-scrolling: touch; // Smooth scrolling on iOS
  }
  
  &__table {
    min-width: 750px; // Minimum width to ensure proper display
    width: 100%;
    
    ::v-deep(.p-datatable-wrapper) {
      overflow-x: auto; // Ensure scrolling works inside the wrapper
      scrollbar-width: thin; // Thin scrollbar for Firefox
    }
    
    // Make the table rows have pointer cursor
    ::v-deep(.p-datatable-tbody > tr) {
      cursor: default; // Default cursor for rows without specific action
    }
    
    // Optimize header and cell padding for better space usage
    ::v-deep(.p-datatable-thead > tr > th) {
      padding: 0.6rem 0.5rem;
      position: sticky; // Keep headers visible on scroll
      top: 0;
      z-index: 1;
      
      // Only show sort icons when actively sorted
      .p-sortable-column-icon {
        &:not(.p-highlight) {
          opacity: 0; // Hide when not sorted
        }
      }
      
      // Show sort icons on hover
      &:hover .p-sortable-column-icon {
        opacity: 0.5; // Show with reduced opacity on hover
      }
    }
    
    ::v-deep(.p-datatable-sm .p-datatable-tbody > tr > td) {
      padding: 0.6rem 0.5rem;
    }
    
    // Responsive adjustments
    @media (max-width: 768px) {
      min-width: 650px;
      
      ::v-deep(.p-datatable-thead > tr > th),
      ::v-deep(.p-datatable-tbody > tr > td) {
        padding: 0.4rem 0.4rem;
        font-size: 0.9rem;
      }
    }

    @media (max-width: 576px) {
      min-width: 550px;
      font-size: 0.85rem;
    }
  }
  
  // Style for the action buttons container
  .action-buttons {
    display: flex;
    justify-content: center;
    gap: 0.3rem;
    flex-wrap: nowrap;
  }
  
  // Style for action buttons
  .action-button {
    border: 1px solid rgba(255, 255, 255, 0.1);
    min-width: 2.2rem;
    height: 2.2rem;
    padding: 0.3rem;
    
    &:hover {
      background-color: rgba(255, 255, 255, 0.1);
    }
    
    @media (max-width: 768px) {
      min-width: 1.8rem;
      height: 1.8rem;
    }
  }
  
  &__empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    gap: 16px;
    color: $shade400;
  }
}
</style>

```

```vue
<!-- src/components/competencies/FgosPreviewModal.vue -->
<template>
    <Dialog
        v-model:visible="visible"
        :header="modalTitle"
        :style="{width: '80vw'}"
        :modal="true"
        :closable="true"
        @hide="$emit('hide')"
    >
        <div v-if="isLoadingDetails || isSavingFgos" class="text-center p-4"> <ProgressSpinner /> </div>
        <div v-else-if="currentFgosData" class="FgosPreviewModal__content">
            <!-- Раздел Метаданные -->
            <div class="FgosPreviewModal__section">
                <h3>Основная информация</h3>
                <div class="FgosPreviewModal__details-grid">
                     <template v-if="currentFgosData.metadata">
                        <div class="FgosPreviewModal__details-item">
                            <span class="FgosPreviewModal__details-label">Номер приказа</span>
                            <span :class="getDiffClass(existingFgosData?.number, currentFgosData.metadata.order_number)" class="FgosPreviewModal__details-value">{{ formatDiff(existingFgosData?.number, currentFgosData.metadata.order_number, currentFgosData.metadata.order_number) }}</span>
                        </div>
                         <div class="FgosPreviewModal__details-item">
                            <span class="FgosPreviewModal__details-label">Дата приказа</span>
                            <span :class="getDiffClass(formatDate(existingFgosData?.date), currentFgosData.metadata.order_date)" class="FgosPreviewModal__details-value">{{ formatDiff(formatDate(existingFgosData?.date), currentFgosData.metadata.order_date, currentFgosData.metadata.order_date) }}</span>
                        </div>
                        <div class="FgosPreviewModal__details-item">
                            <span class="FgosPreviewModal__details-label">Код направления</span>
                            <span :class="getDiffClass(existingFgosData?.direction_code, currentFgosData.metadata.direction_code)" class="FgosPreviewModal__details-value">{{ formatDiff(existingFgosData?.direction_code, currentFgosData.metadata.direction_code, currentFgosData.metadata.direction_code) }}</span>
                        </div>
                        <div class="FgosPreviewModal__details-item">
                            <span class="FgosPreviewModal__details-label">Название направления</span>
                            <span :class="getDiffClass(existingFgosData?.direction_name, currentFgosData.metadata.direction_name)" class="FgosPreviewModal__details-value">{{ formatDiff(existingFgosData?.direction_name, currentFgosData.metadata.direction_name, currentFgosData.metadata.direction_name) }}</span>
                        </div>
                        <div class="FgosPreviewModal__details-item">
                            <span class="FgosPreviewModal__details-label">Уровень образования</span>
                             <span :class="getDiffClass(existingFgosData?.education_level, currentFgosData.metadata.education_level)" class="FgosPreviewModal__details-value">{{ formatDiff(existingFgosData?.education_level, currentFgosData.metadata.education_level, currentFgosData.metadata.education_level) }}</span>
                        </div>
                        <div class="FgosPreviewModal__details-item">
                            <span class="FgosPreviewModal__details-label">Поколение</span>
                            <span :class="getDiffClass(existingFgosData?.generation, currentFgosData.metadata.generation)" class="FgosPreviewModal__details-value">{{ formatDiff(existingFgosData?.generation, currentFgosData.metadata.generation, currentFgosData.metadata.generation) }}</span>
                        </div>
                        <div class="FgosPreviewModal__details-item">
                             <span class="FgosPreviewModal__details-label">Имя файла</span>
                             <span class="FgosPreviewModal__details-value">{{ currentFgosData.file_path || filename }}</span>
                        </div>
                     </template>
                     <div v-else class="FgosPreviewModal__empty-section">
                        Метаданные не извлечены.
                     </div>
                </div>
            </div>

            <!-- Раздел УК Компетенции -->
            <div class="FgosPreviewModal__section">
                <h3>Универсальные компетенции (УК)</h3>
                <div v-if="currentFgosData.uk_competencies?.length > 0">
                    <DataTable :value="currentFgosData.uk_competencies" responsiveLayout="scroll">
                        <Column field="code" header="Код" style="width: 100px;"></Column>
                        <Column field="name" header="Формулировка компетенции"></Column>
                        <Column header="Индикаторы">
                            <template #body="slotProps">
                                <ul v-if="slotProps.data.indicators?.length > 0">
                                    <li v-for="ind in slotProps.data.indicators" :key="ind.code">
                                        <strong>{{ ind.code }}:</strong> {{ ind.formulation }}
                                    </li>
                                </ul>
                                <span v-else>Нет индикаторов</span>
                            </template>
                        </Column>
                    </DataTable>
                </div>
                 <div v-else class="FgosPreviewModal__empty-section">
                     УК компетенции не извлечены.
                 </div>
            </div>
            
            <!-- Раздел ОПК Компетенции -->
            <div class="FgosPreviewModal__section">
                <h3>Общепрофессиональные компетенции (ОПК)</h3>
                 <div v-if="currentFgosData.opk_competencies?.length > 0">
                     <DataTable :value="currentFgosData.opk_competencies" responsiveLayout="scroll">
                         <Column field="code" header="Код" style="width: 100px;"></Column>
                         <Column field="name" header="Формулировка компетенции"></Column>
                         <Column header="Индикаторы">
                             <template #body="slotProps">
                                 <ul v-if="slotProps.data.indicators?.length > 0">
                                     <li v-for="ind in slotProps.data.indicators" :key="ind.code">
                                         <strong>{{ ind.code }}:</strong> {{ ind.formulation }}
                                     </li>
                                 </ul>
                                 <span v-else>Нет индикаторов</span>
                             </template>
                         </Column>
                     </DataTable>
                 </div>
                  <div v-else class="FgosPreviewModal__empty-section">
                      ОПК компетенции не извлечены.
                  </div>
            </div>

            <!-- Раздел Рекомендованные ПС -->
            <div class="FgosPreviewModal__section">
                <h3>Рекомендованные профессиональные стандарты (ПС)</h3>
                <div v-if="currentFgosData.recommended_ps_codes?.length > 0">
                    <ul>
                        <li v-for="code in currentFgosData.recommended_ps_codes" :key="code">
                            {{ code }}
                            <!-- TODO: Добавить поиск по коду в БД и отображение названия ПС, если он уже загружен -->
                        </li>
                    </ul>
                </div>
                <div v-else class="FgosPreviewModal__empty-section">
                    Коды рекомендованных ПС не извлечены.
                </div>
            </div>
            
            <!-- Сообщения о сравнении -->
            <div v-if="existingFgosRecord && !isViewMode" class="FgosPreviewModal__section">
                 <h3>Сравнение с существующим ФГОС</h3>
                 <InlineMessage severity="warn" class="my-2">
                     В базе данных уже существует ФГОС с номером <strong>{{ existingFgosRecord.number }}</strong> от <strong>{{ formatDate(existingFgosRecord.date) }}</strong> для направления <strong>{{ existingFgosRecord.direction_code }}</strong> ({{ existingFgosRecord.education_level }}).
                     <br/> Загружаемый файл, по всей видимости, является обновлением существующего. Сохранение перезапишет старую запись и связанные УК/ОПК/ИДК.
                 </InlineMessage>
                 <!-- TODO: Добавить более детальное сравнение УК/ОПК/ИДК, если нужно -->
            </div>
            <div v-else-if="isViewMode && selectedFgosDetails" class="FgosPreviewModal__section">
                 <h3>Связанные Компетенции и Индикаторы в БД</h3>
                 <!-- Тут можно отобразить списки УК/ОПК с ИДК из selectedFgosDetails -->
                 <div v-if="selectedFgosDetails.uk_competencies?.length > 0 || selectedFgosDetails.opk_competencies?.length > 0">
                      <h4>УК из БД</h4>
                      <DataTable :value="selectedFgosDetails.uk_competencies" responsiveLayout="scroll" class="mb-4">
                           <Column field="code" header="Код" style="width: 100px;"></Column>
                           <Column field="name" header="Формулировка"></Column>
                           <Column header="Индикаторы">
                               <template #body="slotProps">
                                   <ul v-if="slotProps.data.indicators?.length > 0">
                                       <li v-for="ind in slotProps.data.indicators" :key="ind.code">
                                           <strong>{{ ind.code }}:</strong> {{ ind.formulation }}
                                       </li>
                                   </ul>
                                   <span v-else>Нет индикаторов</span>
                               </template>
                           </Column>
                      </DataTable>
                       <h4>ОПК из БД</h4>
                      <DataTable :value="selectedFgosDetails.opk_competencies" responsiveLayout="scroll">
                           <Column field="code" header="Код" style="width: 100px;"></Column>
                           <Column field="name" header="Формулировка"></Column>
                            <Column header="Индикаторы">
                                <template #body="slotProps">
                                    <ul v-if="slotProps.data.indicators?.length > 0">
                                        <li v-for="ind in slotProps.data.indicators" :key="ind.code">
                                            <strong>{{ ind.code }}:</strong> {{ ind.formulation }}
                                        </li>
                                    </ul>
                                    <span v-else>Нет индикаторов</span>
                                </template>
                            </Column>
                       </DataTable>
                 </div>
                  <div v-else class="FgosPreviewModal__empty-section">
                      Связанные УК/ОПК компетенции и индикаторы не найдены в БД.
                  </div>

                  <h4>Рекомендованные ПС в БД</h4>
                  <div v-if="selectedFgosDetails.recommended_ps_list?.length > 0">
                      <ul>
                          <li v-for="ps in selectedFgosDetails.recommended_ps_list" :key="ps.id">
                              <strong>{{ ps.code }}:</strong> {{ ps.name }}
                              <!-- TODO: Добавить ссылку на просмотр ПС -->
                          </li>
                      </ul>
                  </div>
                   <div v-else class="FgosPreviewModal__empty-section">
                       Связанные рекомендованные ПС не найдены в БД.
                   </div>

            </div>


        </div>
        <div v-else class="text-center p-4">
             <InlineMessage severity="error">
                 Не удалось загрузить данные ФГОС.
             </InlineMessage>
        </div>

        <template #footer>
             <div v-if="!isLoadingDetails && !isSavingFgos">
                <Button
                    v-if="!isViewMode"
                    label="Отменить"
                    icon="mdi mdi-close"
                    @click="visible = false"
                    text
                />
                <Button
                     v-if="!isViewMode"
                     label="Сохранить"
                     icon="mdi mdi-content-save"
                     @click="$emit('save', { force_update: !!existingFgosRecord })"
                     :loading="isSavingFgos"
                     :disabled="!currentFgosData || isSavingFgos"
                 />
                 <Button
                    v-if="isViewMode"
                     label="Закрыть"
                     icon="mdi mdi-close"
                     @click="visible = false"
                     text
                 />
             </div>
        </template>
    </Dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import Dialog from 'primevue/dialog';
import Button from 'primevue/button';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import ProgressSpinner from 'primevue/progressspinner'; // Для индикатора загрузки
import InlineMessage from 'primevue/inlinemessage'; // Для сообщений
import Tooltip from 'primevue/tooltip'; // Директива

import { useCompetenciesMatrixStore } from '@/stores/competenciesMatrix';

// Props
const props = defineProps({
    visible: {
        type: Boolean,
        required: true
    },
    // Данные парсинга нового файла (присутствуют только в режиме предпросмотра нового файла)
    parsedData: {
        type: Object,
        default: null
    },
     // Имя парсенного файла (присутствуют только в режиме предпросмотра нового файла)
    filename: {
        type: String,
        default: ''
    },
    // Существующая запись ФГОС в БД, если найдена (присутствует в режиме предпросмотра обновления)
    existingFgosRecord: {
        type: Object,
        default: null
    },
    // Режим отображения: true - просмотр существующего, false - предпросмотр/сохранение нового
    isViewMode: {
        type: Boolean,
        default: false
    }
});

// Emits
const emit = defineEmits(['update:visible', 'save', 'hide']);

// Pinia Store
const competenciesStore = useCompetenciesMatrixStore();

// State from store
const isLoadingDetails = computed(() => competenciesStore.isLoadingFgosDetails); // Загрузка деталей существующего
const isSavingFgos = computed(() => competenciesStore.isSavingFgos); // Сохранение
const selectedFgosDetails = computed(() => competenciesStore.getSelectedFgosDetails); // Детали существующего из стора


// Computed properties
const visible = computed({
    get: () => props.visible,
    set: (value) => emit('update:visible', value)
});

const modalTitle = computed(() => {
    if (props.isViewMode) {
        return props.existingFgosRecord ? `Детали ФГОС ВО: ${props.existingFgosRecord.direction_code}` : 'Детали ФГОС ВО';
    } else {
         // Режим предпросмотра нового файла
         const metadata = props.parsedData?.metadata;
         if (metadata) {
              return `Предпросмотр ФГОС: ${metadata.direction_code} (${metadata.generation})`;
         }
        return 'Предпросмотр ФГОС ВО';
    }
});

const currentFgosData = computed(() => {
    // В режиме просмотра используем данные из selectedFgosDetails из стора
    // В режиме предпросмотра используем данные из props.parsedData
    return props.isViewMode ? selectedFgosDetails.value : props.parsedData;
});


// Helper for formatting date
const formatDate = (dateString) => {
    if (!dateString) return 'Не указано';
    try {
         // If it's a Date object from backend (details), use toLocaleDateString
         if (dateString instanceof Date) {
              return dateString.toLocaleDateString('ru-RU', { year: 'numeric', month: 'long', day: 'numeric' });
         }
         // If it's a string from metadata (parsedData), try parsing
         // Assuming metadata date is DD.MM.YYYY
         if (typeof dateString === 'string') {
              const parts = dateString.split('.');
              if (parts.length === 3) {
                   const date = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
                   return date.toLocaleDateString('ru-RU', { year: 'numeric', month: 'long', day: 'numeric' });
              }
         }
         return dateString; // Return original if parsing fails
    } catch (e) {
         console.error("Failed to format date:", dateString, e);
         return dateString;
    }
};

// Helper for diff styling
const getDiffClass = (oldValue, newValue) => {
    if (props.isViewMode || !props.existingFgosRecord) return ''; // Нет сравнения в режиме просмотра или если нет старой записи
    // Сравниваем значения после форматирования (например, даты) или как есть
    const formattedOld = typeof oldValue === 'string' ? oldValue.trim() : oldValue;
    const formattedNew = typeof newValue === 'string' ? newValue.trim() : newValue;

    if (formattedOld !== formattedNew && formattedOld !== undefined && formattedOld !== null && formattedOld !== '') {
         return 'diff-changed'; // Изменилось значение
    } else if (formattedOld === undefined || formattedOld === null || formattedOld === '') {
         return 'diff-new'; // Новое значение (не было в старой записи)
    }
    return ''; // Без изменений
};

const formatDiff = (oldValue, newValue, displayedValue) => {
    if (props.isViewMode || !props.existingFgosRecord) return displayedValue;

     const formattedOld = typeof oldValue === 'string' ? oldValue.trim() : oldValue;
     const formattedNew = typeof newValue === 'string' ? newValue.trim() : newValue;

     if (formattedOld !== formattedNew && formattedOld !== undefined && formattedOld !== null && formattedOld !== '') {
          // Значение изменилось, показываем старое зачеркнутым и новое
          return `${formattedOld} → ${displayedValue}`;
     }
     // Если значение новое или не изменилось, показываем просто новое
     return displayedValue;
};


// Watchers
watch(() => props.visible, (isVisible) => {
    if (isVisible && props.isViewMode && props.existingFgosRecord) {
        // Если модалка открывается в режиме просмотра и есть существующая запись,
        // она должна сама загрузить детали, если их нет в сторе.
        // Но мы фетчим детали в FgosView перед открытием модалки,
        // так что они должны быть доступны в selectedFgosDetails геттере.
        // Убедимся, что selectedFgosDetails соответствует existingFgosRecord
        if (!selectedFgosDetails.value || selectedFgosDetails.value.id !== props.existingFgosRecord.id) {
             // Этого не должно происходить при правильном вызове из FgosView
             console.error("FgosPreviewModal: Mismatch between existingFgosRecord and selectedFgosDetails");
             // Возможно, стоит вызвать fetchFgosDetails(props.existingFgosRecord.id);
        }
    }
});

// Добавляем директиву v-tooltip локально
const vTooltip = Tooltip;

</script>

<style lang="scss">
@import '@styles/_variables.scss';

.FgosPreviewModal__content {
    padding: 0 16px; // Внутренние отступы модалки
    
    @media (max-width: 768px) {
         padding: 0 8px;
    }
}

.FgosPreviewModal__section {
    margin-bottom: 24px;
    
    h3 {
        margin-bottom: 12px;
        font-size: 1.2rem;
        color: $shade100;
        
        @media (max-width: 640px) {
             font-size: 1.1rem;
             margin-bottom: 8px;
        }
    }
     
    // Стили для таблиц внутри секции
    .p-datatable {
        font-size: 0.9rem;
        
         @media (max-width: 768px) {
             font-size: 0.85rem;
         }
        
        .p-datatable-thead > tr > th {
             padding: 0.5rem;
             background-color: $shade800;
        }
         .p-datatable-tbody > tr > td {
             padding: 0.5rem;
         }
    }
    
    // Стили для списков индикаторов
    ul {
        padding-left: 20px;
         margin: 0;
    }
    li {
        margin-bottom: 5px;
         word-break: break-word; // Перенос длинных формулировок
    }

     @media (max-width: 640px) {
        margin-bottom: 16px;
     }
}

.FgosPreviewModal__details-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    margin-bottom: 16px;

    @media (max-width: 768px) {
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 12px;
    }

    @media (max-width: 480px) {
        grid-template-columns: 1fr;
        gap: 8px;
    }
}

.FgosPreviewModal__details-item {
    display: flex;
    flex-direction: column;
    background-color: $shade800;
    padding: 12px;
    border-radius: $borderRadius;

    @media (max-width: 640px) {
        padding: 8px;
    }
}

.FgosPreviewModal__details-label {
    font-size: 0.9rem;
    color: $shade300;
    margin-bottom: 4px;

    @media (max-width: 640px) {
        font-size: 0.8rem;
    }
}

.FgosPreviewModal__details-value {
    font-weight: 500;
     word-break: break-word; // Перенос длинных названий

    @media (max-width: 640px) {
        font-size: 0.95rem;
    }
}

.FgosPreviewModal__empty-section {
    padding: 16px;
    background-color: $shade800;
    border-radius: $borderRadius;
    color: $shade400;
    text-align: center;

    @media (max-width: 640px) {
        padding: 12px 8px;
        font-size: 0.9rem;
    }
}

// Diff styling
.diff-changed {
    // Старое значение будет показано в formatDiff, но без зачеркивания по умолчанию
    // Придется вручную стилизовать, если хотим зачеркивание старого
    color: $yellow-500; // Пример подсветки измененных полей
    // text-decoration: line-through; /* Это применится ко всему значению */
}
.diff-new {
    color: $green-500; // Пример подсветки новых полей
    font-weight: bold;
}

</style>
```

**Пояснения к Frontend UI:**

*   `FgosView.vue` создает страницу со списком загруженных ФГОС (`DataTable`), кнопкой "Загрузить ФГОС" и ссылкой на скрытый input `type="file"`.
*   При выборе файла вызывается `uploadFgosFile` из стора.
*   При успешном парсинге и получении данных от API (`/fgos/upload`), стор заполняет `fgosParsedData` и `fgosUploadFilename`, а также пытается найти существующий ФГОС (`fgosExistingRecord`) и открывает модальное окно `FgosPreviewModal`.
*   `FgosPreviewModal.vue` отображает данные из `fgosParsedData` (для нового файла) или `selectedFgosDetails` (для просмотра существующего).
*   Используются вычисляемые свойства для определения заголовка модалки и данных для отображения (`currentFgosData`).
*   Добавлены базовые стили для сравнения (`diff-changed`, `diff-new`). Форматирование сравнения (`formatDiff`, `getDiffClass`) реализовано на стороне Vue.
*   Кнопка "Сохранить" вызывает `saveFgosData` из стора, передавая флаг `force_update` (если `existingFgosRecord` не null).
*   Добавлены ConfirmDialog и useConfirm/useToast для подтверждения удаления и уведомлений пользователя.

**Необходимо сделать после применения этих изменений:**

1.  **Применить изменения:** Скопировать код в соответствующие файлы в вашем репозитории. Установить `pdfminer.six`.
2.  **Сгенерировать и применить миграцию:** `flask db migrate -m "Add FGOS and related tables/columns"` (если модели были изменены или добавлены новые FK) и `flask db upgrade`. Убедитесь, что `ondelete="CASCADE"` правильно настроены.
3.  **Обновить `seed_db`:** Добавить сидинг для `FgosVo`, УК, ОПК, ИУК, ИОПК, связей `FgosRecommendedPs` в `cli_commands/db_seed.py`, чтобы были тестовые данные для просмотра и сравнения. Коды и формулировки взять из Распоряжения 505-Р для 09.03.01.
4.  **Тестирование Backend (CLI):** Протестировать `flask import-fgos` с разными сценариями:
    *   Импорт нового файла (`--dry-run`, без флагов).
    *   Импорт нового файла, когда он уже есть (`--force` vs без флага).
    *   Удаление существующего (`--delete-only`).
    *   Попытка импорта не-PDF файла.
    *   Попытка импорта PDF с ошибками парсинга.
5.  **Тестирование Backend (API):** Протестировать новые эндпоинты `/fgos` через `curl`/Postman: `GET /fgos`, `GET /fgos/<id>`, `POST /fgos/upload`, `POST /fgos/save`, `DELETE /fgos/<id>`. Проверить статусы ответов, структуру JSON, корректность данных в БД. Проверить права доступа (`admin_only`).
6.  **Тестирование Frontend:** Проверить UI:
    *   Отображение списка ФГОС.
    *   Просмотр деталей существующего ФГОС.
    *   Загрузка нового файла, появление модального окна предпросмотра.
    *   Предпросмотр нового ФГОС (данные из файла).
    *   Предпросмотр обновленной версии (сравнение с существующим).
    *   Сохранение нового/обновленного ФГОС через модалку.
    *   Удаление ФГОС из списка.
    *   Обработка ошибок (не удалось распарсить, не удалось сохранить).
7.  **Обновление `tasks.md`:** Отметить выполненные задачи в разделе 1 и актуализировать статус.

Это большой шаг. Удачи в реализации и тестировании!