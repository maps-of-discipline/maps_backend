Отлично, план действий становится более конкретным. Давайте сфокусируемся на интерфейсе "Индикаторы Компетенций" или, как вы предложили, "Конструктор Компетенций", и на том, как методист будет вручную создавать ПК и ИПК, сверяясь с информацией из ФГОС и ПС.

**Начнем с Парсера ФГОС ВО 3++ и CLI Команды**

Прежде чем мы перейдем к интерфейсу, нам нужен механизм для загрузки данных ФГОС в нашу БД. Это позволит нам в UI отображать УК/ОПК и рекомендованные ПС.

**1. Определение структуры данных для ФГОС ВО и Компетенций/Индикаторов (БД):**

У нас уже есть модели:
*   `FgosVo`: номер, дата, код направления, название, уровень, поколение, `file_path`.
*   `CompetencyType`: УК, ОПК, ПК.
*   `Competency`: `competency_type_id`, `fgos_vo_id` (для УК/ОПК), `code`, `name`.
*   `Indicator`: `competency_id`, `code`, `formulation`, `source`.
*   `FgosRecommendedPs`: `fgos_vo_id`, `prof_standard_id`.

**Что нужно извлечь из PDF ФГОС ВО 3++:**
*   **Метаданные ФГОС:**
    *   Номер приказа (например, "929")
    *   Дата приказа (например, "19.09.2017")
    *   Код направления подготовки/специальности (например, "09.03.01")
    *   Наименование направления подготовки/специальности (например, "Информатика и вычислительная техника")
    *   Уровень высшего образования (например, "бакалавриат")
    *   Поколение ФГОС (например, "3++")
*   **Универсальные Компетенции (УК):**
    *   Код (например, "УК-1")
    *   Формулировка
*   **Общепрофессиональные Компетенции (ОПК):**
    *   Код (например, "ОПК-1")
    *   Формулировка
*   **Рекомендованные Профессиональные Стандарты:**
    *   Список кодов ПС (например, "06.001", "06.015")

**Индикаторы (ИУК/ИОПК) из ФГОС обычно не извлекаются, они часто идут из Распоряжения 505-Р или определяются вузом. Для парсера ФГОС мы их пока опускаем.**

**2. Разработка CLI команды для импорта ФГОС:**

Создадим новый файл `cli_commands/fgos_import.py` и соответствующий парсер в `competencies_matrix/fgos_parser.py`.

**`competencies_matrix/fgos_parser.py` (Новый файл или доработка существующего `parsers.py`)**
*   **Задача:** Функции для извлечения вышеописанных данных из текста, полученного из PDF. PDF-парсер (например, `pdfminer.six`) будет читать текст, а наши функции – его анализировать регулярными выражениями.

**`cli_commands/fgos_import.py`**
*   **Задача:** Команда `flask import-fgos <filepath> [--force] [--delete-only] [--dry-run]`
    *   Принимает путь к PDF-файлу ФГОС.
    *   Вызывает парсер из `competencies_matrix.fgos_parser`.
    *   **Логика работы с БД:**
        *   **Поиск существующего ФГОС:** Перед вставкой/обновлением искать существующую запись `FgosVo` по уникальному набору: `direction_code`, `education_level`, `number` (приказа), `date` (приказа).
        *   **`--force`:** Если ФГОС существует, удалить все связанные с ним `Competency` (УК/ОПК) и `FgosRecommendedPs`, затем обновить поля `FgosVo` и вставить новые компетенции/связи с ПС.
        *   **Без `--force` (по умолчанию):** Если ФГОС существует, выдать ошибку и ничего не делать. Если не существует – создать новую запись.
        *   **`--delete-only`:** Если ФГОС существует, удалить его и все связанные `Competency` (УК/ОПК) и `FgosRecommendedPs`. Ничего не вставлять. Если не существует – ничего не делать.
        *   **`--dry-run`:** Выполнить парсинг, показать, что было бы сделано (найден/не найден, будет создан/обновлен/удален), но не вносить изменения в БД.
    *   **Сохранение данных:**
        *   Запись в `FgosVo`.
        *   Записи в `Competency` для УК и ОПК (с привязкой к `FgosVo.id` и `CompetencyType.id`).
        *   Записи в `FgosRecommendedPs` (с привязкой к `FgosVo.id` и поиском/созданием `ProfStandard.id` по коду ПС – **ВАЖНО: если ПС с таким кодом нет, его нужно будет создать как "заглушку" только с кодом, или выдать предупреждение и пропустить связь**). Для MVP, если ПС не найден, просто пропускаем связь и логируем.

**Формат команды `fgos_import.py` (пример):**

```
1. Функция `import_fgos_command` в `cli_commands/fgos_import.py`
2. Функции `parse_fgos_pdf`, `_extract_fgos_metadata`, `_extract_uk_opk`, `_extract_recommended_ps` в `competencies_matrix/fgos_parser.py`
3. Функция `save_fgos_data` и `delete_fgos` в `competencies_matrix/logic.py`
```

**`cli_commands/fgos_import.py`:**
```python
# cli_commands/fgos_import.py
import click
from flask.cli import with_appcontext
import os
import traceback
import datetime
import logging

# --- Импортируем необходимые компоненты ---
from maps.models import db
# Импортируем функции из логики модуля компетенций
from competencies_matrix.logic import save_fgos_data, delete_fgos, parse_fgos_file
from competencies_matrix.models import FgosVo # Нужно для поиска
# Импортируем парсер напрямую, чтобы управлять его логированием
from competencies_matrix import fgos_parser # Import the module itself

# Настройка логирования
logger = logging.getLogger(__name__)

@click.command(name='import-fgos')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force import/overwrite if FGOS with same identifying data exists.')
@click.option('--delete-only', is_flag=True, default=False,
              help='Only delete FGOS if it exists, do not import.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform read and validation without saving or deleting.')
@click.option('--debug-parser', is_flag=True, default=False,
              help='Enable DEBUG logging for the FGOS parser.')
@with_appcontext
def import_fgos_command(filepath, force, delete_only, dry_run, debug_parser):
    """
    Импортирует данные ФГОС ВО из PDF-файла, парсит и сохраняет в БД.
    Поиск существующего ФГОС производится по коду направления, уровню, номеру и дате приказа.

    FILEPATH: Путь к PDF файлу ФГОС для импорта.
    """
    # Временно повышаем уровень логирования для парсера, если включен флаг отладки
    parser_logger = logging.getLogger(fgos_parser.__name__)
    original_parser_level = parser_logger.level
    if debug_parser:
        parser_logger.setLevel(logging.DEBUG)

    print(f"\n---> Starting FGOS import from: {filepath}")
    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved/deleted from the database. <<<")
    filename = os.path.basename(filepath)

    try:
        # 1. Чтение и парсинг PDF файла
        logger.info(f"Reading and parsing FGOS file: {filename}...")
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
        
        # Вызываем функцию parse_fgos_file из logic.py, которая внутри вызовет parse_fgos_pdf
        # parse_fgos_file из logic.py может содержать доп. логику перед/после парсинга
        parsed_data = parse_fgos_file(file_bytes, filename) # Эта функция в logic.py вызовет fgos_parser.parse_fgos_pdf

        if not parsed_data:
            logger.error("\n!!! PARSING FAILED: parse_fgos_file returned None unexpectedly !!!")
            # Откат не нужен, если ошибка на этапе парсинга до взаимодействия с БД
            # if not dry_run: db.session.rollback() # Неправильно здесь, db.session еще не использовалась
            return

        logger.info("   - File parsed successfully.")
        
        # Выводим извлеченные метаданные для информации
        metadata = parsed_data.get('metadata', {})
        print("   - Extracted Metadata:")
        for key, value in metadata.items():
             print(f"     - {key}: {value}")
             
        print(f"   - Found {len(parsed_data.get('uk_competencies', []))} УК competencies.")
        print(f"   - Found {len(parsed_data.get('opk_competencies', []))} ОПК competencies.")
        print(f"   - Found {len(parsed_data.get('recommended_ps_codes', []))} recommended PS codes.")

        # Логика для --delete-only
        if delete_only:
             logger.info("\n---> DELETE ONLY mode enabled.")
             fgos_to_delete = None
             # Ищем существующий ФГОС по ключевым метаданным
             if metadata.get('direction_code') and metadata.get('education_level') and metadata.get('order_number') and metadata.get('order_date'):
                  try:
                       # Преобразуем order_date в datetime.date, если это строка
                       order_date_obj = metadata['order_date']
                       if isinstance(order_date_obj, str):
                           # Попытка парсить из DD.MM.YYYY, если парсер вернул строку
                           try:
                               order_date_obj = datetime.datetime.strptime(order_date_obj, '%d.%m.%Y').date()
                           except ValueError:
                               # Если парсер вернул строку, которую не удалось преобразовать, логируем и выходим
                               logger.error(f"   - Invalid date format in metadata for order_date: '{metadata['order_date']}'. Expected datetime.date or parsable string.")
                               return
                       elif not isinstance(order_date_obj, datetime.date):
                           logger.error(f"   - Invalid type for order_date in metadata: {type(order_date_obj)}. Expected datetime.date.")
                           return

                       fgos_to_delete = db.session.query(FgosVo).filter_by(
                            direction_code=metadata['direction_code'],
                            education_level=metadata['education_level'],
                            number=metadata['order_number'],
                            date=order_date_obj # Используем объект datetime.date
                       ).first()
                  except SQLAlchemyError as e: # Исправлено на SQLAlchemyError
                        logger.error(f"   - Database error during lookup for delete: {e}")
                        db.session.rollback() # Откат сессии при ошибке БД
                        return # Выход из функции
             else:
                  logger.error("   - Missing identifying metadata from parsed file for lookup. Cannot perform delete.")
                  # Не выходим, т.к. это не ошибка БД, а неполные данные парсинга
                  
             if fgos_to_delete:
                  if not dry_run:
                       logger.info(f"   - Found existing FGOS (id: {fgos_to_delete.id}, code: {fgos_to_delete.direction_code}). Deleting...")
                       deleted = delete_fgos(fgos_to_delete.id, db.session) # delete_fgos управляет своей транзакцией
                       if deleted: logger.info("   - FGOS deleted successfully.")
                       else: logger.error("   - Failed to delete FGOS (check logs).")
                       # db.session.commit() # Коммит уже внутри delete_fgos
                  else:
                       logger.info(f"   - DRY RUN: Found existing FGOS (id: {fgos_to_delete.id}). Would delete.")
             else:
                  logger.warning("   - No existing FGOS found matching identifying metadata. Nothing to delete.")

             logger.info("---> FGOS import finished (delete only mode).\n")
             return # Завершаем, если был delete_only

        # Логика для сохранения (если не --delete-only)
        if not dry_run:
            logger.info("Saving data to database...")
            # save_fgos_data будет искать существующий ФГОС и либо обновлять (если force), либо создавать новый
            # Передаем сессию db.session
            saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=force)

            if saved_fgos is None:
                 # Ошибка уже залогирована внутри save_fgos_data
                 logger.error("\n!!! SAVE FAILED !!!")
                 # db.session.rollback() # Откат уже должен быть внутри save_fgos_data при ошибке
            else:
                 # db.session.commit() # Коммит уже внутри save_fgos_data
                 logger.info(f"\n---> FGOS from '{filename}' imported successfully with ID {saved_fgos.id}!\n")

        else: # dry_run
            logger.info("   - Skipping database save due to --dry-run flag.")
            # Дополнительно, можно показать, что было бы сделано
            # (например, будет ли создан новый или обновлен существующий)
            # Это потребует немного логики поиска из save_fgos_data здесь
            logger.info(f"---> DRY RUN for '{filename}' completed successfully (parsing passed).\n")

    except FileNotFoundError:
        logger.error(f"\n!!! ERROR: File not found at '{filepath}' !!!")
    except ImportError as e:
        logger.error(f"\n!!! ERROR: Missing dependency for reading PDF files: {e} !!!")
        logger.error("   - Please ensure 'pdfminer.six' is installed.")
    except ValueError as e: # Ошибки парсинга, которые мы сами выбрасываем
        logger.error(f"\n!!! PARSING ERROR: {e} !!!")
        logger.error(f"   - Error occurred during parsing file '{filename}'.")
        # Откат не нужен, если ошибка на этапе парсинга до взаимодействия с БД
    except Exception as e:
        # Откат нужен, если ошибка произошла ПОСЛЕ начала взаимодействия с БД,
        # но до вызова save_fgos_data или delete_fgos, которые управляют своими транзакциями
        if not dry_run and db.session.dirty: # Проверяем, есть ли изменения в сессии
            db.session.rollback()
            logger.warning("   - Rolled back session due to unexpected error before save/delete call.")
        logger.error(f"\n!!! UNEXPECTED ERROR during import: {e} !!!", exc_info=True)
    finally:
         # Возвращаем уровень логирования парсера к исходному
         parser_logger.setLevel(original_parser_level)

```

**`competencies_matrix/fgos_parser.py` (фрагменты для иллюстрации):**
```python
# competencies_matrix/fgos_parser.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
from pdfminer.high_level import extract_text
# ... (другие импорты, если нужны, например, для логирования)
import logging # Добавлено

logger = logging.getLogger(__name__) # Используем стандартный подход Flask

def _clean_text(text: str) -> str:
    """Базовая очистка текста от лишних пробелов и переносов."""
    # Улучшенная очистка: Удаляем переносы в середине слов, дефисы в конце строк,
    # схлопываем пробелы/табуляции, схлопываем переносы строк
    text = text.replace('\r\n', '\n').replace('\r', '\n') # Нормализуем переносы строк
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text) # Слово- перенос слово -> Словослово
    text = re.sub(r'-\n', '', text) # Удаляем висячие дефисы в конце строк
    text = re.sub(r'[ \t]+', ' ', text) # Заменяем множественные пробелы/табуляции на один пробел
    text = re.sub(r'\n[ \t]*\n', '\n\n', text) # Схлопываем пустые строки до одной пустой строки (\n\n)
    text = text.strip() # Убираем пробелы/переносы в начале и конце
    return text

def _parse_date_from_text(date_str: str) -> Optional[datetime.date]:
    """Парсит дату из строки, поддерживая форматы DD.MM.YYYY и 'D месяца YYYY г.'."""
    date_str = date_str.strip()
    if not date_str: 
        logger.debug("_parse_date_from_text: Input date string is empty.")
        return None

    month_names = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
        'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }

    # Try DD.MM.YYYY format first
    try:
        parsed_date = datetime.datetime.strptime(date_str, '%d.%m.%Y').date()
        logger.debug(f"_parse_date_from_text: Successfully parsed '{date_str}' as DD.MM.YYYY.")
        return parsed_date
    except ValueError:
        logger.debug(f"_parse_date_from_text: '{date_str}' did not match DD.MM.YYYY format. Trying other formats.")
        pass # Try other formats

    # Try DD MonthName YYYY format (e.g., '7 августа 2020')
    # Added optional 'года' and optional ' г.' at the end
    match = re.match(r'(\d{1,2})\s+([а-яА-Я]+)(?:\s+года)?\s+(\d{4})\s*г?\.?', date_str, re.IGNORECASE)
    if match:
        day_str, month_name_str, year_str = match.groups()[:3] # Берем только первые 3 группы
        month = month_names.get(month_name_str.lower())
        if month:
            try:
                parsed_date = datetime.date(int(year_str), month, int(day_str))
                logger.debug(f"_parse_date_from_text: Successfully parsed '{date_str}' as DD MonthName YYYY.")
                return parsed_date
            except ValueError:
                logger.warning(f"_parse_date_from_text: Invalid date components for format 'DD MonthName YYYY': {year_str}-{month}-{day_str}")
                return None
        else:
            logger.warning(f"_parse_date_from_text: Unknown month name '{month_name_str}' for format 'DD MonthName YYYY'.")
            return None

    logger.warning(f"_parse_date_from_text: Could not parse date string: '{date_str}' using any known format.")
    return None


def _extract_fgos_metadata(text: str) -> Dict[str, Any]:
    """
    Извлекает метаданные (номер/дата приказа, код/название направления, уровень, поколение)
    из текста ФГОС PDF. Использует регулярные выражения для поиска ключевых фраз.
    """
    metadata = {}
    # Область поиска для метаданных (обычно в начале документа)
    # Увеличим search_area, т.к. метаданные могут быть не сразу
    search_area = text[:4000] # Увеличим еще немного на всякий случай
    logger.debug(f"--- METADATA SEARCH AREA (first 500 chars) ---\n{search_area[:500]}\n--------------------------------------")

    # --- Номер и дата приказа ---
    # Ищем "от" затем дату, затем "г." опционально, затем "№" опционально, затем номер приказа.
    # Захватываем текст между "от" и "№" как потенциальную дату
    # Паттерн: 'от' + DATE_PART + 'г.'(опц) + '№'(опц) + NUMBER_PART
    # Учитываем, что дата может содержать точки (например, 26.11.2020 г.)
    order_match = re.search(
        r'от\s+(.+?)\s*г\.?\s*[N№#]\s*(\d+[а-яА-Я0-9-]*)', # .+? - нежадный захват любых символов до 'г.' (включая точки)
        search_area, re.IGNORECASE | re.DOTALL
    )
    if order_match:
        date_str_raw = order_match.group(1).strip()
        number_str = order_match.group(2).strip()
        logger.debug(f"Attempting to parse date_str_raw: '{date_str_raw}'")
        metadata['order_date'] = _parse_date_from_text(date_str_raw) # Используем новую функцию
        metadata['order_number'] = number_str
        if metadata.get('order_date'): # Проверяем, что дата была успешно распознана
             logger.info(f"_extract_fgos_metadata: Found order: №{metadata['order_number']} от {metadata['order_date']}")
        else:
             logger.warning(f"_extract_fgos_metadata: Found order number '{metadata['order_number']}', но дата '{date_str_raw}' не смогла быть распознана.")
    else:
        logger.warning("_extract_fgos_metadata: Order number and date not found using pattern 'от DATE г. № NUMBER'.")
        # Дополнительный поиск номера приказа, если основной паттерн не сработал (менее надежный)
        alt_order_number_match = re.search(r'(?:приказом|утвержден)\s.*?от\s+.+?\s*[№N#]\s*(\d+[а-яА-Я0-9-]*)', search_area, re.IGNORECASE | re.DOTALL)
        if alt_order_number_match:
            metadata['order_number'] = alt_order_number_match.group(1).strip()
            logger.warning(f"_extract_fgos_metadata: Found order number '{metadata['order_number']}' using ALTERNATIVE pattern (date not found or parsed separately).")
        else:
            logger.error("_extract_fgos_metadata: CRITICAL - Order number could not be found by any pattern.")


    # --- Код и название направления подготовки ---
    # Более гибкий паттерн для названия, допускающий скобки в названии и заканчивающийся
    # либо началом следующего важного блока, либо двумя переносами строки, либо концом строки.
    # Используем нежадный захват для названия.
    direction_match = re.search(
        r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
        r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s+'  # Код направления
        # Нежадный захват до явного признака конца или перевода строки
        r'([^\n(]+?(?:\([^)]+\))?[^\n(]*?)(?=\s*(?:\(с изменениями|\n\s*I\.\s+Общие положения|\n\s*С изменениями|Зарегистрировано в Минюсте|$))',
        search_area, re.IGNORECASE
    )
    if direction_match:
        logger.debug(f"Direction_match primary found: group(1)='{direction_match.group(1)}', group(2)='{direction_match.group(2)}'")
        metadata['direction_code'] = direction_match.group(1).strip()
        name_raw = direction_match.group(2).strip()
        # Убираем возможные кавычки, пробелы и тире в конце названия
        metadata['direction_name'] = re.sub(r'[\s"-]+$', '', name_raw).strip().replace('"', '')
        logger.info(f"_extract_fgos_metadata: Found direction: Code '{metadata['direction_code']}', Name '{metadata['direction_name']}'")
    else:
        logger.warning("_extract_fgos_metadata: Primary direction pattern not found. Trying simple fallback...")
        # Более простой запасной вариант, если первый не сработал
        direction_match_simple = re.search(
            r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
            r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s*"?([^\n"]+?)"?\s*$', # Захватываем название до конца строки, опционально в кавычках
            search_area, re.IGNORECASE | re.MULTILINE
        )
        if direction_match_simple:
            logger.debug(f"Direction_match_simple found: group(1)='{direction_match_simple.group(1)}', group(2)='{direction_match_simple.group(2)}'")
            metadata['direction_code'] = direction_match_simple.group(1).strip()
            name_raw = direction_match_simple.group(2).strip()
            metadata['direction_name'] = re.sub(r'[\s"-]+$', '', name_raw).strip().replace('"', '')
            logger.info(f"_extract_fgos_metadata: Found direction (simple fallback): Code '{metadata['direction_code']}', Name '{metadata['direction_name']}'")
        else:
            logger.error("_extract_fgos_metadata: CRITICAL - Direction code and name not found by any pattern.")

    # --- Уровень образования ---
    # Ищем "бакалавриат", "магистратура", "специалитет" после слов "уровень" или "высшего образования -"
    level_match = re.search(r'(?:высшего образования\s*-\s*|уровень\s+)(бакалавриата|магистратуры|специалитета)', search_area, re.IGNORECASE)
    if level_match:
        logger.debug(f"Level_match found: group(1)='{level_match.group(1)}'")
        # Используем group(1), так как у нас одна захватывающая группа для уровня
        metadata['education_level'] = level_match.group(1).lower().strip()
        logger.info(f"_extract_fgos_metadata: Found education level: '{metadata['education_level']}'")
    else:
        logger.error("_extract_fgos_metadata: CRITICAL - Education level not found.")

    # --- Поколение ФГОС ---
    # Попробуем найти "ФГОС ВО" и если после него есть (3++) или (3+) или просто 3++
    generation_match_main = re.search(r'ФГОС\s+ВО(?:\s*\(?(3\+\+?)\)?)?', search_area, re.IGNORECASE)
    if generation_match_main and generation_match_main.group(1):
        gen_text = generation_match_main.group(1).lower().strip()
        # Убираем возможные точки или скобки в конце
        metadata['generation'] = re.sub(r'[().,]+$', '', gen_text).strip()
        logger.info(f"_extract_fgos_metadata: Found generation (main pattern): '{metadata['generation']}'")
    else:
        logger.debug(f"FGOS generation_match_main not found or group(1) is None. Trying fallback.")
        # Если не нашли с "ВО", ищем просто "ФГОС 3++" или "ФГОС 3+"
        generation_match_fallback = re.search(r'ФГОС\s+(3\+\+?)\b', search_area, re.IGNORECASE)
        if generation_match_fallback:
            metadata['generation'] = generation_match_fallback.group(1).lower().strip()
            logger.info(f"_extract_fgos_metadata: Found generation (fallback): '{metadata['generation']}'")
        else:
            logger.warning("_extract_fgos_metadata: FGOS generation explicitly not found. Setting to 'unknown'.")
            metadata['generation'] = 'unknown' # Устанавливаем значение по умолчанию, т.к. оно не критично

    # Проверка критических полей
    # order_date теперь не является критическим для самого парсера метаданных, т.к. его может не быть в легко парсимом формате
    critical_fields = ['order_number', 'direction_code', 'education_level']
    missing_critical = [field for field in critical_fields if not metadata.get(field)]
    if not metadata.get('order_date'):
         logger.warning("_extract_fgos_metadata: 'order_date' could not be extracted successfully.")

    if missing_critical:
         logger.error(f"_extract_fgos_metadata: Отсутствуют следующие КРИТИЧЕСКИЕ метаданные: {', '.join(missing_critical)}")
    else:
         logger.info("_extract_fgos_metadata: Все КРИТИЧЕСКИЕ метаданные извлечены.")

    logger.debug(f"   - Final extracted metadata before return: {metadata}")
    return metadata


def _extract_uk_opk(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """Извлекает УК и ОПК компетенции (код, название) из текста раздела III ФГОС."""
    competencies = {'uk_competencies': [], 'opk_competencies': []}

    # Улучшенный поиск начала раздела III (без ^, гибче к пробелам вокруг III.)
    # Ищем III. Требования...
    section_iii_start_match = re.search(
        r'III\.\s*Требования\s+к\s+результатам\s+освоения\s+программы',
        text, re.IGNORECASE | re.MULTILINE
    )

    if section_iii_start_match:
        logger.debug("_extract_uk_opk: Section III start marker ('III. Требования к результатам...') found.")

        text_after_section_iii = text[section_iii_start_match.end():]

        # Более гибкий поиск начала раздела IV (используем новую строку и необязательные пробелы)
        # Ищем IV. Требования...
        section_iv_start_match = re.search(
            r'\n[ \t]*IV\.\s*Требования\s+к\s+условиям\s+реализации\s+программы',
            text_after_section_iii, re.IGNORECASE | re.MULTILINE
        )

        # Определяем текст раздела III: от конца маркера III до начала маркера IV или конца текста после III
        section_iii_text = text_after_section_iii[:section_iv_start_match.start()] if section_iv_start_match else text_after_section_iii
        
        if not section_iii_text.strip():
            logger.warning("_extract_uk_opk: Section III text is empty after markers search.")
            return competencies

        logger.debug(f"_extract_uk_opk: Successfully isolated Section III text (length: {len(section_iii_text)} chars). Preview: {section_iii_text[:500]}...")

        # --- Парсинг блоков УК и ОПК внутри section_iii_text ---
        # (?s) для DOTALL
        # Ищем блок УК: "Универсальные компетенции" ... до следующего блока или конца раздела/текста
        uk_block_re = r'(?s)Универсальные\s+компетенци(?:и|я).*?:\s*(.*?)(?=\n[ \t]*(?:Общепрофессиональные|Профессиональные)\s+компетенци(?:и|я)|\n[ \t]*IV\.\s*Требования|\Z)'
        # Ищем блок ОПК: "Общепрофессиональные компетенции" ... до следующего блока или конца раздела/текста
        opk_block_re = r'(?s)Общепрофессиональные\s+компетенци(?:и|я).*?:\s*(.*?)(?=\n[ \t]*Профессиональные\s+компетенци(?:и|я)|\n[ \t]*IV\.\s*Требования|\Z)'

        # --- Парсинг самих УК компетенций ---
        uk_block_match = re.search(uk_block_re, section_iii_text, re.IGNORECASE)
        if uk_block_match:
            uk_block_text = uk_block_match.group(1)
            logger.debug(f"_extract_uk_opk: Found UK block (length: {len(uk_block_text)} chars). Preview: {uk_block_text[:500]}...")
            
            # Паттерн: (Код УК) (опц. разделители) (Формулировка: ...)
            # Lookahead ищет:
            # 1. Начало следующей УК ((?:\n[ \t]*|^)УК-\d+)
            # 2. Начало блока ОПК ((?:\n[ \t]*|^)Общепрофессиональные\s+компетенции)
            # 3. Начало блока ПК ((?:\n[ \t]*|^)Профессиональные\s+компетенции)
            # 4. Конец текста (\Z)
            # Убрали ^ в начале УК-паттерна, т.к. он может быть не в начале строки блока
            uk_matches = re.finditer(
                r'(УК-\d+)\s*[).:]?\s*(.+?)(?=(?:\n[ \t]*|^)(?:УК-\d+\s*[).:]?|Общепрофессиональные\s+компетенци|Профессиональные\s+компетенци)|\Z)',
                uk_block_text, re.IGNORECASE | re.MULTILINE | re.DOTALL # MULTILINE чтобы ^ работал для каждой строки, DOTALL чтобы . включал \n
            )
            
            parsed_uk_count = 0
            for match in uk_matches:
                code = match.group(1).strip().upper()
                name = match.group(2).strip()
                # Дополнительная очистка формулировки
                name = re.sub(r'\.$', '', name) # Убираем точку в конце
                name = re.sub(r'\s*\n\s*', ' ', name) # Заменяем переносы внутри формулировки на пробел
                name = re.sub(r'\s{2,}', ' ', name).strip() # Схлопываем пробелы
                if name: # Добавляем только если есть непустая формулировка
                    competencies['uk_competencies'].append({'code': code, 'name': name, 'indicators': []})
                    parsed_uk_count += 1
            logger.debug(f"_extract_uk_opk: Parsed {parsed_uk_count} УК competencies using main pattern.")
            if not competencies['uk_competencies'] and uk_block_text.strip(): # Если блок был, но ничего не спарсили
                 logger.warning("_extract_uk_opk: No UKs parsed despite UK block found.")
            elif uk_block_text.strip() and parsed_uk_count > 0 and parsed_uk_count < 8 and "УК-11" not in [c['code'] for c in competencies['uk_competencies']]: # Для ХимТех (11 УК) это нормально
                 # Эвристика: если спарсили мало УК (меньше 8), но не УК-11, это может быть проблемой
                 logger.warning(f"_extract_uk_opk: Parsed only {parsed_uk_count} UKs. Preview: {uk_block_text[:300]}...")
        else:
            logger.warning("_extract_uk_opk: UK competencies block not found in Section III.")

        # --- Парсинг самих ОПК компетенций ---
        opk_block_match = re.search(opk_block_re, section_iii_text, re.IGNORECASE)
        if opk_block_match:
            opk_block_text = opk_block_match.group(1)
            logger.debug(f"_extract_uk_opk: Found OPK block (length: {len(opk_block_text)} chars). Preview: {opk_block_text[:500]}...")
            
            # Аналогичный lookahead для ОПК
            # Убрали ^ в начале ОПК-паттерна
            opk_matches = re.finditer(
                r'(ОПК-\d+)\s*[).:]?\s*(.+?)(?=(?:\n[ \t]*|^)(?:ОПК-\d+\s*[).:]?|Профессиональные\s+компетенци)|\Z)',
                opk_block_text, re.IGNORECASE | re.MULTILINE | re.DOTALL
            )
            
            parsed_opk_count = 0
            for match in opk_matches:
                code = match.group(1).strip().upper()
                name = match.group(2).strip()
                name = re.sub(r'\.$', '', name)
                name = re.sub(r'\s*\n\s*', ' ', name) 
                name = re.sub(r'\s{2,}', ' ', name).strip()
                if name:
                    competencies['opk_competencies'].append({'code': code, 'name': name, 'indicators': []})
                    parsed_opk_count += 1
            logger.debug(f"_extract_uk_opk: Parsed {parsed_opk_count} ОПК competencies using main pattern.")
            if not competencies['opk_competencies'] and opk_block_text.strip():
                 logger.warning("_extract_uk_opk: No OPKs parsed despite OPK block found.")
            elif opk_block_text.strip() and parsed_opk_count > 0 and parsed_opk_count < 5: # Обновленная эвристика
                 logger.warning(f"_extract_uk_opk: Parsed only {parsed_opk_count} OPKs. Preview: {opk_block_text[:300]}...")
        else:
            logger.warning("_extract_uk_opk: OPK competencies block not found in Section III.")

    else:
        # Если раздел III не найден
        logger.warning("_extract_uk_opk: Section III start marker not found ('III. Требования к результатам...' or simplified).")

    return competencies


def _extract_recommended_ps(text: str, filename: str) -> List[str]: # Added filename parameter
    """
    Извлекает список кодов рекомендованных профессиональных стандартов из текста ФГОС.
    """
    ps_codes = []
    # Ищем начало блока ПС (делаем гибче к разделителям и словам между "Перечень" и "профессиональных стандартов")
    ps_section_match = re.search(
        r'(?s)(Перечень(?:\s+и\s+)?(?:рекомендуемых\s+)?профессиональных\s+стандартов'
        r'|Приложение.*?Перечень\s+профессиональных\s+стандартов)', # Added (?:\s+и\s+) for "Перечень и профессиональных стандартов"
        text, re.IGNORECASE
    )
    
    if not ps_section_match:
        logger.warning("_extract_recommended_ps: Section 'Перечень профессиональных стандартов' or related Appendix not found.")
        return ps_codes

    # Текст для поиска кодов ПС начинается с найденного заголовка
    search_text_for_ps_codes = text[ps_section_match.start():]
    
    # Определяем маркеры конца списка ПС (начало следующего раздела IV, V и т.д., или "Сведения об организациях")
    # Добавим маркер "Информация об изменениях:", который часто встречается перед новым разделом или в конце
    end_of_ps_list_match = re.search(
        r'(?s)(\n\s*(?:IV|V|VI|VII|VIII|IX|X)\.\s*Требования|\n\s*Сведения\s+об\s+организациях\s*-\s*разработчиках|\n\s*Информация\s+об\s+изменениях:|\n{3,})', # Added 'Информация об изменениях:'
        search_text_for_ps_codes, re.IGNORECASE | re.MULTILINE
    )

    if end_of_ps_list_match:
        # Если найден конец списка, ограничиваем текст для поиска кодов
        ps_list_text = search_text_for_ps_codes[:end_of_ps_list_match.start()]
        logger.debug(f"_extract_recommended_ps: Found PS list text (length: {len(ps_list_text)} chars) before next major section. Preview: {ps_list_text[:1000]}...")
    else:
        # Если маркер конца не найден, анализируем весь оставшийся текст (или его часть)
        ps_list_text = search_text_for_ps_codes # Можно ограничить[:5000] или по другому критерию
        logger.warning(f"_extract_recommended_ps: Could not find clear end of PS list. Analyzing remaining text (length: {len(ps_list_text)} chars). Preview: {ps_list_text[:1000]}...")

    # Ищем коды ПС (например, 06.001) в извлеченном тексте
    # \b - граница слова, чтобы не находить части других чисел
    code_matches = re.finditer(r'\b(\d{2}\.\d{3})\b', ps_list_text)

    for match in code_matches:
        ps_codes.append(match.group(1))

    ps_codes = sorted(list(set(ps_codes))) # Убираем дубликаты и сортируем
    logger.debug(f"_extract_recommended_ps: Found {len(ps_codes)} recommended PS codes: {ps_codes}")

    # --- DEBUGGING: Write ps_list_text to file if no codes found ---
    if not ps_codes and ps_list_text.strip(): # Только если текст был, но коды не нашлись
        # Убираем недопустимые символы из имени файла
        safe_filename_part = re.sub(r'[\\/*?:"<>|]', "_", os.path.splitext(filename)[0])
        debug_filename = f"debug_ps_list_text_{safe_filename_part}.txt"
        try:
            with open(debug_filename, "w", encoding="utf-8") as f:
                f.write(ps_list_text)
            logger.warning(f"_extract_recommended_ps: No PS codes extracted from section text. Section text written to '{debug_filename}' for debugging.")
        except Exception as e:
            logger.error(f"_extract_recommended_ps: Failed to write debug file '{debug_filename}': {e}")
        # End Debugging

    if not ps_codes and ps_list_text.strip(): logger.warning("_extract_recommended_ps: No PS codes extracted from the identified section text despite text existing. Check regex \b(\d{2}\.\d{3})\b or text content.")
    elif not ps_codes and not ps_list_text.strip(): logger.warning("_extract_recommended_ps: No PS codes extracted from section, because section text is empty.")

    return ps_codes


def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Главная функция парсинга PDF файла ФГОС ВО.
    Извлекает метаданные, УК/ОПК компетенции и рекомендованные ПС.
    """
    logger.info(f"Starting PDF parsing for FGOS file: {filename}")
    parsed_data: Dict[str, Any] = {
        'metadata': {},
        'uk_competencies': [],
        'opk_competencies': [],
        'recommended_ps_codes': [],
        'raw_text': "" # Сохраним сырой текст для возможной отладки
    }
    try:
        # 1. Извлечение текста из PDF
        text_content = extract_text(io.BytesIO(file_bytes))
        parsed_data['raw_text'] = text_content # Сохраняем сырой текст
        cleaned_text = _clean_text(text_content) # Очищаем текст для парсинга

        # 2. Извлечение метаданных
        parsed_data['metadata'] = _extract_fgos_metadata(cleaned_text)

        # Проверяем наличие критических метаданных ПОСЛЕ попытки парсинга метаданных
        critical_fields = ['order_number', 'direction_code', 'education_level']
        missing_critical = [field for field in critical_fields if not parsed_data['metadata'].get(field)]
        
        # Дополнительно проверяем дату, т.к. она может быть None после _parse_date_from_text
        if not parsed_data['metadata'].get('order_date'):
             logger.warning(f"parse_fgos_pdf: 'order_date' could not be extracted or parsed correctly for {filename}.")
             # Если дата критична для идентификации, можно добавить 'order_date' в missing_critical
             # или выбрасывать ошибку здесь, если дата абсолютно необходима.
             # Для CLI это может быть не так критично, как для API сохранения.

        if missing_critical:
             logger.error(f"parse_fgos_pdf: Missing one or more CRITICAL metadata fields for {filename}. Aborting parsing.")
             # Выбрасываем ValueError, чтобы CLI команда могла его поймать и сообщить пользователю
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}'. Отсутствуют: {', '.join(missing_critical)}.")

        # Если критические метаданные найдены, продолжаем парсить остальное
        logger.debug(f"parse_fgos_pdf: Calling _extract_uk_opk with cleaned_text (first 500 chars):\n{cleaned_text[:500]}...")
        
        # 3. Извлечение УК и ОПК
        comp_data = _extract_uk_opk(cleaned_text)
        parsed_data['uk_competencies'] = comp_data.get('uk_competencies', [])
        parsed_data['opk_competencies'] = comp_data.get('opk_competencies', [])
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.warning(f"parse_fgos_pdf: No UK or OPK competencies found for {filename}.")
        else:
             logger.info(f"parse_fgos_pdf: Found {len(parsed_data['uk_competencies'])} UK and {len(parsed_data['opk_competencies'])} OPK competencies.") # Added found count

        # 4. Извлечение рекомендованных ПС
        # Pass filename to _extract_recommended_ps for debugging
        parsed_data['recommended_ps_codes'] = _extract_recommended_ps(cleaned_text, filename) # Added filename here

        logger.info(f"PDF parsing for FGOS {filename} finished. Metadata Extracted: {bool(parsed_data['metadata'])}, UK Found: {len(parsed_data['uk_competencies'])}, OPK Found: {len(parsed_data['opk_competencies'])}, Recommended PS Found: {len(parsed_data['recommended_ps_codes'])}")
        
        # Добавляем финальную проверку, что хоть ЧТО-ТО было найдено, кроме метаданных
        # (т.к. метаданные могли быть неполными, но критические поля прошли)
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies'] and not parsed_data['recommended_ps_codes']:
             # Если только метаданные, но не компетенции/ПС, это может быть сигналом к проверке
             logger.warning(f"parse_fgos_pdf: No competencies or recommended PS found for {filename} despite critical metadata being present.")

        return parsed_data

    except FileNotFoundError: # Это не должно происходить, т.к. filepath проверяется в CLI
        logger.error(f"parse_fgos_pdf: File not found: {filename}")
        raise
    except ImportError as e: # Если pdfminer.six не установлен
        logger.error(f"parse_fgos_pdf: Missing dependency for reading PDF files: {e}. Please install 'pdfminer.six'.")
        # Перебрасываем ошибку, чтобы CLI мог ее обработать
        raise ImportError(f"Отсутствует зависимость для чтения PDF файлов: {e}. Пожалуйста, установите 'pdfminer.six'.")
    except ValueError as e: # Ошибки, которые мы сами генерируем (например, отсутствие метаданных)
        logger.error(f"parse_fgos_pdf: Parser ValueError for {filename}: {e}")
        raise ValueError(f"Ошибка парсинга содержимого файла '{filename}': {e}")
    except Exception as e: # Любые другие неожиданные ошибки
        logger.error(f"parse_fgos_pdf: Unexpected error during PDF parsing for {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")

# --- Функции для извлечения данных из HTML/Markdown Профстандартов (оставляем без изменений) ---
# ... (html_to_markdown_enhanced, extract_ps_metadata_simple, extract_ps_structure_detailed, parse_prof_standard_orchestrator) ...
# Код для ПС остается как в `competencies_matrix/parsers.py` из предыдущего вывода
# ВАЖНО: Убедитесь, что эти функции также используют `logger`, а не `print` для отладочных сообщений.
# parse_prof_standard_orchestrator - это ваша функция, которая читает файл и вызывает парсер
# в зависимости от расширения, затем вызывает extract_ps_metadata_simple и extract_ps_structure_detailed

# --- Блок if __name__ == '__main__': для автономного тестирования (можно доработать) ---
if __name__ == '__main__':
    # ... (ваш тестовый код для fgos_parser.py) ...
    pass
```

**`competencies_matrix/logic.py` (добавление `parse_fgos_file` и доработка `save_fgos_data`):**
```python
# competencies_matrix/logic.py
# ... (существующие импорты)
from .fgos_parser import parse_fgos_pdf # Импортируем сам парсер PDF
# ...

def parse_fgos_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Оркестрирует парсинг файла ФГОС ВО PDF.
    Эта функция вызывается из CLI команды и API эндпоинта.
    """
    try:
        # Здесь можно добавить предварительные проверки, если нужно,
        # но основная логика парсинга - в fgos_parser.parse_fgos_pdf
        parsed_data = parse_fgos_pdf(file_bytes, filename)
        
        # Проверка, что парсер вернул хоть какие-то метаданные (особенно критичные)
        if not parsed_data or not parsed_data.get('metadata'):
             logger.warning(f"parse_fgos_file: Parsing failed or returned insufficient metadata for {filename}")
             if not parsed_data:
                  raise ValueError("Парсер вернул пустые данные.")
             if not parsed_data.get('metadata'):
                  raise ValueError("Не удалось извлечь метаданные из файла ФГОС.")
             # Если мы дошли сюда, значит, parsed_data['metadata'] есть, но может быть неполным
             # parse_fgos_pdf сам должен был выбросить ValueError, если критичные метаданные отсутствуют.
             
        return parsed_data
    except ValueError as e: # Ловим ошибки валидации из парсера
        logger.error(f"parse_fgos_file: Parser ValueError for {filename}: {e}")
        raise e # Перебрасываем дальше
    except Exception as e:
        logger.error(f"parse_fgos_file: Unexpected error parsing {filename}: {e}", exc_info=True)
        # Оборачиваем в общее исключение, если нужно, или перебрасываем как есть
        raise Exception(f"Неожиданная ошибка при парсинге файла ФГОС '{filename}': {e}")


def save_fgos_data(parsed_data: Dict[str, Any], filename: str, session: Session, force_update: bool = False) -> Optional[FgosVo]:
    """
    Сохраняет структурированные данные ФГОС из парсера в БД.
    Управляет транзакцией (через вложенные savepoints).
    """
    logger.info(f"save_fgos_data: Attempting to save data for FGOS from '{filename}'. force_update: {force_update}")
    if not parsed_data or not parsed_data.get('metadata'):
        logger.warning("save_fgos_data: No parsed data or metadata provided for saving.")
        return None

    metadata = parsed_data.get('metadata', {})
    # Извлекаем поля для поиска/создания FgosVo
    fgos_number = metadata.get('order_number')
    fgos_date_obj = metadata.get('order_date') # Ожидаем здесь уже объект datetime.date
    fgos_direction_code = metadata.get('direction_code')
    fgos_education_level = metadata.get('education_level')
    
    # Доп. поля для FgosVo
    fgos_generation = metadata.get('generation') # Может быть 'unknown'
    fgos_direction_name = metadata.get('direction_name')

    # Проверка наличия ключевых полей для идентификации FgosVo
    if not all([fgos_number, fgos_date_obj, fgos_direction_code, fgos_education_level]):
        logger.error("save_fgos_data: Missing core metadata from parsed data for saving (number, date, direction_code, education_level).")
        return None
    
    # Убедимся, что fgos_date_obj это datetime.date
    if not isinstance(fgos_date_obj, datetime.date):
        logger.error(f"save_fgos_data: order_date is not a datetime.date object. Type: {type(fgos_date_obj)}. Value: {fgos_date_obj}")
        # Попытка конвертации, если это строка (на всякий случай, хотя парсер должен возвращать date)
        if isinstance(fgos_date_obj, str):
            try:
                fgos_date_obj = datetime.datetime.strptime(fgos_date_obj, '%Y-%m-%d').date() # Пример, если парсер вернул YYYY-MM-DD
            except ValueError:
                 logger.error("save_fgos_data: Failed to convert order_date string to date object.")
                 return None
        else:
            return None # Неизвестный тип даты

    try:
        # Используем вложенную транзакцию (savepoint)
        # Это позволит откатить только эту операцию, если что-то пойдет не так,
        # не затрагивая внешнюю транзакцию (если она есть, например, в CLI команде)
        with session.begin_nested():
            # Ищем существующий ФГОС
            existing_fgos = session.query(FgosVo).filter_by(
                direction_code=fgos_direction_code,
                education_level=fgos_education_level,
                number=fgos_number,
                date=fgos_date_obj
            ).first()

            fgos_vo = None # Переменная для хранения объекта FgosVo (нового или существующего)

            if existing_fgos:
                if force_update:
                    logger.info(f"save_fgos_data: Existing FGOS found (ID: {existing_fgos.id}). Force update requested. Deleting old competencies and PS links...")
                    # Удаляем связанные УК/ОПК и рекомендованные ПС
                    # SQLAlchemy должен обработать каскадное удаление индикаторов, если настроено в модели Competency
                    session.query(Competency).filter_by(fgos_vo_id=existing_fgos.id).delete()
                    session.query(FgosRecommendedPs).filter_by(fgos_vo_id=existing_fgos.id).delete()
                    # session.flush() # Применяем удаления перед обновлением

                    # Обновляем сам ФГОС
                    fgos_vo = existing_fgos
                    fgos_vo.direction_name = fgos_direction_name if fgos_direction_name else 'Не указано'
                    fgos_vo.generation = fgos_generation if fgos_generation else 'unknown'
                    fgos_vo.file_path = filename # Обновляем путь к файлу
                    session.add(fgos_vo) # Добавляем в сессию для фиксации изменений
                    session.flush() # Применяем обновление основной записи
                    logger.info(f"save_fgos_data: Existing FGOS (ID: {fgos_vo.id}) updated.")

                else:
                    # ФГОС существует, force_update не указан - ничего не делаем, возвращаем существующий
                    logger.warning(f"save_fgos_data: FGOS with same key data already exists (ID: {existing_fgos.id}). Skipping save.")
                    return existing_fgos # Возвращаем найденный без изменений
            else:
                # Создаем новый ФГОС
                fgos_vo = FgosVo(
                    number=fgos_number,
                    date=fgos_date_obj,
                    direction_code=fgos_direction_code,
                    direction_name=fgos_direction_name if fgos_direction_name else 'Не указано',
                    education_level=fgos_education_level,
                    generation=fgos_generation if fgos_generation else 'unknown',
                    file_path=filename
                )
                session.add(fgos_vo)
                session.flush() # Получаем ID нового ФГОС
                logger.info(f"save_fgos_data: New FgosVo created with ID {fgos_vo.id} for {fgos_vo.direction_code}.")

            # --- Сохранение УК и ОПК ---
            # Получаем ID типов компетенций УК и ОПК
            comp_types_q = session.query(CompetencyType).filter(CompetencyType.code.in_(['УК', 'ОПК'])).all()
            comp_types_map = {ct.code: ct for ct in comp_types_q}

            if not comp_types_map.get('УК') or not comp_types_map.get('ОПК'):
                 logger.error("save_fgos_data: CompetencyType (УК и/или ОПК) not found in the database. Cannot save competencies.")
                 raise ValueError("Типы компетенций УК/ОПК не найдены в базе данных.") # Это прервет транзакцию

            saved_competencies_count = 0
            all_parsed_competencies = parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', [])

            for parsed_comp in all_parsed_competencies:
                comp_code = parsed_comp.get('code')
                comp_name = parsed_comp.get('name')
                if not comp_code or not comp_name:
                    logger.warning(f"save_fgos_data: Skipping competency due to missing code/name: {parsed_comp}")
                    continue

                comp_prefix = comp_code.split('-')[0].upper() # УК или ОПК
                comp_type = comp_types_map.get(comp_prefix)

                if not comp_type:
                    logger.warning(f"save_fgos_data: Skipping competency {comp_code}: Competency type {comp_prefix} not found.")
                    continue
                
                # Проверяем, существует ли уже такая компетенция для ДАННОГО ФГОС (на случай, если force_update не удалил все)
                # Эта проверка может быть избыточной, если мы всегда удаляем при force_update, но безопасна
                existing_comp_for_fgos = session.query(Competency).filter_by(
                     code=comp_code, competency_type_id=comp_type.id, fgos_vo_id=fgos_vo.id
                ).first()

                if existing_comp_for_fgos:
                     logger.warning(f"save_fgos_data: Competency {comp_code} already exists for FGOS {fgos_vo.id}. Skipping creation/update.")
                     # Можно добавить логику обновления имени, если нужно, но обычно УК/ОПК не меняются в рамках одного ФГОС
                     continue

                competency = Competency(
                    competency_type_id=comp_type.id,
                    fgos_vo_id=fgos_vo.id, # Связываем с текущим ФГОС
                    code=comp_code,
                    name=comp_name
                )
                session.add(competency)
                session.flush() # Получаем ID компетенции (для индикаторов, если бы они были)
                saved_competencies_count += 1
                logger.debug(f"save_fgos_data: Created Competency {competency.code} (ID: {competency.id}) for FGOS {fgos_vo.id}.")
            
            logger.info(f"save_fgos_data: Saved {saved_competencies_count} competencies for FGOS {fgos_vo.id}.")

            # --- Сохранение рекомендованных ПС ---
            recommended_ps_codes = parsed_data.get('recommended_ps_codes', [])
            logger.info(f"save_fgos_data: Found {len(recommended_ps_codes)} potential recommended PS codes.")

            if recommended_ps_codes:
                 # Находим существующие ПС в БД по кодам
                 existing_prof_standards = session.query(ProfStandard).filter(ProfStandard.code.in_(recommended_ps_codes)).all()
                 ps_by_code = {ps.code: ps for ps in existing_prof_standards}

                 linked_ps_count = 0
                 for ps_code in recommended_ps_codes:
                    prof_standard = ps_by_code.get(ps_code)
                    if prof_standard:
                        # Проверяем, есть ли уже такая связь
                        existing_link = session.query(FgosRecommendedPs).filter_by(
                            fgos_vo_id=fgos_vo.id, prof_standard_id=prof_standard.id
                        ).first()

                        if not existing_link:
                             link = FgosRecommendedPs(
                                 fgos_vo_id=fgos_vo.id,
                                 prof_standard_id=prof_standard.id,
                                 is_mandatory=False # По умолчанию, если не указано иное
                             )
                             session.add(link)
                             linked_ps_count += 1
                             logger.debug(f"save_fgos_data: Created link FGOS {fgos_vo.id} <-> PS {prof_standard.code}.")
                        else:
                             logger.debug(f"save_fgos_data: Link between FGOS {fgos_vo.id} and PS {prof_standard.code} already exists.")
                    else:
                        # Если ПС с таким кодом нет в БД - создаем заглушку или пропускаем
                        # Для MVP - пропускаем и логируем
                        logger.warning(f"save_fgos_data: Recommended PS with code {ps_code} not found in DB. Skipping link creation.")
                 logger.info(f"save_fgos_data: Queued {linked_ps_count} new recommended PS links.")
            
            # Коммит вложенной транзакции
            # session.commit() # Не нужно, with session.begin_nested() сделает это
        
        # Коммит основной транзакции (если мы управляем ею здесь)
        # В CLI команде коммит будет снаружи
        # Для API - тоже снаружи, после успешного вызова этой функции
        session.commit() # <--- ВАЖНО: Добавили коммит здесь, т.к. CLI команда его не делает
        logger.info(f"save_fgos_data: Changes for FGOS ID {fgos_vo.id} committed successfully.")
        return fgos_vo # Возвращаем сохраненный/обновленный объект FgosVo

    except IntegrityError as e: # Обработка ошибок уникальности
        session.rollback() # Откатываем всю транзакцию (основную, если она была начата снаружи, или savepoint)
        logger.error(f"save_fgos_data: Integrity error during save for FGOS from '{filename}': {e}", exc_info=True)
        return None
    except SQLAlchemyError as e: # Обработка других ошибок БД
        session.rollback()
        logger.error(f"save_fgos_data: Database error during save for FGOS from '{filename}': {e}", exc_info=True)
        return None
    except Exception as e: # Обработка всех остальных ошибок
        session.rollback()
        logger.error(f"save_fgos_data: Unexpected error during save for FGOS from '{filename}': {e}", exc_info=True)
        return None


def delete_fgos(fgos_id: int, session: Session) -> bool:
    """
    Удаляет ФГОС и все связанные с ним сущности (Компетенции, Рекомендованные ПС).
    Управляет своей транзакцией.
    """
    logger.info(f"delete_fgos: Attempting to delete FGOS with id: {fgos_id}")
    try:
        # Используем вложенную транзакцию (savepoint)
        with session.begin_nested():
            fgos_to_delete = session.query(FgosVo).get(fgos_id)
            if not fgos_to_delete:
                logger.warning(f"delete_fgos: FGOS with id {fgos_id} not found for deletion.")
                return False # Возвращаем False, если объект не найден

            # SQLAlchemy должен автоматически удалить связанные записи Competency и FgosRecommendedPs
            # благодаря `backref='fgos'` и `cascade="all, delete-orphan"` (если он есть)
            # или через явное удаление, если каскады не настроены на все связи.
            # Проверим, настроены ли каскады в моделях.
            # Если FgosVo.competencies и FgosVo.recommended_ps_assoc имеют cascade="all, delete-orphan",
            # то явное удаление не нужно.
            # Для безопасности, можно явно удалить связанные записи ПЕРЕД удалением основного объекта:
            # session.query(Competency).filter_by(fgos_vo_id=fgos_id).delete(synchronize_session='fetch')
            # session.query(FgosRecommendedPs).filter_by(fgos_vo_id=fgos_id).delete(synchronize_session='fetch')
            # session.flush() # Применяем удаления зависимостей

            session.delete(fgos_to_delete)
            # session.flush() # Применяем удаление основного объекта
        
        session.commit() # Коммитим основную транзакцию (если она была начата снаружи) или savepoint
        logger.info(f"delete_fgos: FGOS with id {fgos_id} and related entities deleted successfully.")
        return True

    except SQLAlchemyError as e:
        session.rollback() # Откатываем транзакцию
        logger.error(f"delete_fgos: Database error deleting FGOS {fgos_id}: {e}", exc_info=True)
        raise # Перебрасываем ошибку, чтобы CLI/API мог ее обработать
    except Exception as e:
        session.rollback()
        logger.error(f"delete_fgos: Unexpected error deleting FGOS {fgos_id}: {e}", exc_info=True)
        raise

# ... (остальная часть файла logic.py)
```

**3. Регистрация CLI команды в `app.py`:**

```python
# app.py
# ...
from cli_commands.fgos_import import import_fgos_command # Добавить этот импорт
# ...

def create_app(config_class=Config):
    # ...
    app.cli.add_command(import_aup_command)
    app.cli.add_command(seed_command)
    app.cli.add_command(unseed_command)
    app.cli.add_command(import_fgos_command) # <--- Зарегистрировать новую команду
    app.cli.add_command(parse_ps_command)
    # ...
    return app
```

После этого, вы сможете запустить `flask import-fgos path/to/your/fgos.pdf` для тестирования.

**Следующие шаги (после парсера ФГОС):**

1.  **Доработка парсера профстандартов (`profstandard-lean.py` или новый `competencies_matrix/ps_parser.py`):**
    *   Фокус на извлечении кода, названия ПС, и всего текста в Markdown (для MVP).
    *   CLI команда `flask parse-ps <filepath> [--force] [--dry-run]` для загрузки и сохранения `ProfStandard.parsed_content`.
2.  **Frontend – страница "Конструктор Компетенций":**
    *   Создание нового Vue компонента и маршрута.
    *   Реализация UI для выбора ОП (или ФГОС).
    *   Отображение УК/ОПК из выбранного ФГОС.
    *   Отображение рекомендованных ПС для ФГОС и/или списка всех загруженных ПС.
    *   UI для просмотра Markdown-содержимого ПС.
    *   Формы для ручного создания ПК и ИПК.
    *   API вызовы в бэкенд для сохранения ПК/ИПК.

Давайте начнем с CLI команды для ФГОС. Какие у вас есть мысли или вопросы по предложенной структуре и логике? Готовы ли вы предоставить пример PDF ФГОС 3++ для тестирования парсера?