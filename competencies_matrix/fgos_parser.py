# competencies_matrix/fgos_parser.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
from pdfminer.high_level import extract_text
# BS4, markdownify, chardet, pandas, traceback are used in PS parsing, keep them
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from markdownify import markdownify
import chardet
import pandas as pd
import logging
import traceback
import os


# Настройка логирования для этого модуля
logger = logging.getLogger(__name__) # Используем стандартный подход Flask

# --- FGOS PDF Parsing ---

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
    metadata = {}
    search_area = text[:4000] # Увеличим еще немного на всякий случай
    logger.debug(f"--- METADATA SEARCH AREA (first 500 chars) ---\n{search_area[:500]}\n--------------------------------------")

    # --- Order number and date ---
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
        metadata['order_date'] = _parse_date_from_text(date_str_raw)
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


    # --- Direction code and name ---
    direction_match = re.search(
        r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
        r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s+'
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

    # --- Education level ---
    level_match = re.search(r'(?:высшего образования\s*-\s*|уровень\s+)(бакалавриата|магистратуры|специалитета)', search_area, re.IGNORECASE)
    if level_match:
        logger.debug(f"Level_match found: group(1)='{level_match.group(1)}'")
        # Используем group(1), так как у нас одна захватывающая группа для уровня
        metadata['education_level'] = level_match.group(1).lower().strip()
        logger.info(f"_extract_fgos_metadata: Found education level: '{metadata['education_level']}'")
    else:
        logger.error("_extract_fgos_metadata: CRITICAL - Education level not found.")

    # --- FGOS generation ---
    # Попробуем найти "ФГОС ВО" и если после него есть (3++) или (3+) или просто 3++
    generation_match_main = re.search(r'ФГОС\s+ВО(?:\s*\(?(3\+\+?)\)?)?', search_area, re.IGNORECASE)
    if generation_match_main and generation_match_main.group(1):
        gen_text = generation_match_main.group(1).lower().strip()
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
    """Extracts UK and OPK competencies (code, name) from Section III of FGOS PDF."""
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
            uk_matches = re.finditer(
                r'^(УК-\d+)\s*[).:]?\s*(.+?)(?=(?:\n[ \t]*|^)(?:УК-\d+\s*[).:]?|Общепрофессиональные\s+компетенци|Профессиональные\s+компетенци)|\Z)',
                uk_block_text, re.IGNORECASE | re.MULTILINE | re.DOTALL
            )
            
            parsed_uk_count = 0
            for match in uk_matches:
                code = match.group(1).strip().upper()
                name = match.group(2).strip()
                name = re.sub(r'\.$', '', name) 
                name = re.sub(r'\s*\n\s*', ' ', name) 
                name = re.sub(r'\s{2,}', ' ', name).strip() 
                if name: 
                    competencies['uk_competencies'].append({'code': code, 'name': name, 'indicators': []})
                    parsed_uk_count += 1
            logger.debug(f"_extract_uk_opk: Parsed {parsed_uk_count} УК competencies using main pattern.")
            if not competencies['uk_competencies'] and uk_block_text.strip():
                 logger.warning("_extract_uk_opk: No UKs parsed despite UK block found.")
            elif uk_block_text.strip() and parsed_uk_count > 0 and parsed_uk_count < 8 and "УК-11" not in [c['code'] for c in competencies['uk_competencies']]: # Для ХимТех (11 УК) это нормально
                 logger.warning(f"_extract_uk_opk: Parsed only {parsed_uk_count} UKs. Preview: {uk_block_text[:300]}...")
        else:
            logger.warning("_extract_uk_opk: UK competencies block not found in Section III.")

        # --- Парсинг самих ОПК компетенций ---
        opk_block_match = re.search(opk_block_re, section_iii_text, re.IGNORECASE)
        if opk_block_match:
            opk_block_text = opk_block_match.group(1)
            logger.debug(f"_extract_uk_opk: Found OPK block (length: {len(opk_block_text)} chars). Preview: {opk_block_text[:500]}...")
            
            # Аналогичный lookahead для ОПК
            opk_matches = re.finditer(
                r'^(ОПК-\d+)\s*[).:]?\s*(.+?)(?=(?:\n[ \t]*|^)(?:ОПК-\d+\s*[).:]?|Профессиональные\s+компетенци)|\Z)',
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

    search_text_for_ps_codes = text[ps_section_match.start():]
    
    # Define end markers (Section IV, V, etc., or "Сведения об организациях", or just next major section)
    # Добавим маркер "Информация об изменениях:", который часто встречается перед новым разделом или в конце
    end_of_ps_list_match = re.search(
        r'(?s)(\n\s*(?:IV|V|VI|VII|VIII|IX|X)\.\s*Требования|\n\s*Сведения\s+об\s+организациях\s*-\s*разработчиках|\n\s*Информация\s+об\s+изменениях:|\n{3,})', # Added 'Информация об изменениях:'
        search_text_for_ps_codes, re.IGNORECASE | re.MULTILINE
    )

    if end_of_ps_list_match:
        ps_list_text = search_text_for_ps_codes[:end_of_ps_list_match.start()]
        logger.debug(f"_extract_recommended_ps: Found PS list text (length: {len(ps_list_text)} chars) before next major section. Preview: {ps_list_text[:1000]}...")
    else:
        ps_list_text = search_text_for_ps_codes # Если конец не найден, анализируем весь оставшийся текст
        logger.warning(f"_extract_recommended_ps: Could not find clear end of PS list. Analyzing remaining text (length: {len(ps_list_text)} chars). Preview: {ps_list_text[:1000]}...")

    # Find PS codes (e.g., 06.001) in the extracted text
    code_matches = re.finditer(r'\b(\d{2}\.\d{3})\b', ps_list_text)

    for match in code_matches:
        ps_codes.append(match.group(1))

    ps_codes = sorted(list(set(ps_codes)))
    logger.debug(f"_extract_recommended_ps: Found {len(ps_codes)} recommended PS codes: {ps_codes}")

    # --- DEBUGGING: Write ps_list_text to file if no codes found ---
    if not ps_codes and ps_list_text.strip():
        debug_filename = f"debug_ps_list_text_{os.path.splitext(filename)[0]}.txt"
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
    """
    logger.info(f"Starting PDF parsing for FGOS file: {filename}")
    parsed_data: Dict[str, Any] = {
        'metadata': {},
        'uk_competencies': [],
        'opk_competencies': [],
        'recommended_ps_codes': [],
        'raw_text': ""
    }
    try:
        text_content = extract_text(io.BytesIO(file_bytes))
        parsed_data['raw_text'] = text_content
        cleaned_text = _clean_text(text_content) # Очищаем текст для парсинга

        parsed_data['metadata'] = _extract_fgos_metadata(cleaned_text)

        # Проверяем наличие критических метаданных ПОСЛЕ попытки парсинга метаданных
        critical_fields = ['order_number', 'direction_code', 'education_level']
        missing_critical = [field for field in critical_fields if not parsed_data['metadata'].get(field)]
        
        if missing_critical:
             logger.error(f"parse_fgos_pdf: Missing one or more CRITICAL metadata fields for {filename}. Aborting parsing.")
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}'. Отсутствуют: {', '.join(missing_critical)}.")

        # Если критические метаданные найдены, продолжаем парсить остальное
        logger.debug(f"parse_fgos_pdf: Calling _extract_uk_opk with cleaned_text (first 500 chars):\n{cleaned_text[:500]}...")
        
        comp_data = _extract_uk_opk(cleaned_text)
        parsed_data['uk_competencies'] = comp_data.get('uk_competencies', [])
        parsed_data['opk_competencies'] = comp_data.get('opk_competencies', [])
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.warning(f"parse_fgos_pdf: No UK or OPK competencies found for {filename}.")
        else:
             logger.info(f"parse_fgos_pdf: Found {len(parsed_data['uk_competencies'])} UK and {len(parsed_data['opk_competencies'])} OPK competencies.") # Added found count

        # Pass filename to _extract_recommended_ps for debugging
        parsed_data['recommended_ps_codes'] = _extract_recommended_ps(cleaned_text, filename) # Added filename here

        logger.info(f"PDF parsing for FGOS {filename} finished. Metadata Extracted: {bool(parsed_data['metadata'])}, UK Found: {len(parsed_data['uk_competencies'])}, OPK Found: {len(parsed_data['opk_competencies'])}, Recommended PS Found: {len(parsed_data['recommended_ps_codes'])}")
        
        # Добавляем финальную проверку, что хоть ЧТО-ТО было найдено
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies'] and not parsed_data['recommended_ps_codes']:
             logger.warning(f"parse_fgos_pdf: No competencies or recommended PS found for {filename} despite critical metadata being present.")

        return parsed_data

    except FileNotFoundError:
        logger.error(f"parse_fgos_pdf: File not found: {filename}")
        raise
    except ImportError as e:
        logger.error(f"parse_fgos_pdf: Missing dependency for reading PDF files: {e}. Please install 'pdfminer.six'.")
        raise ImportError(f"Отсутствует зависимость для чтения PDF файлов: {e}. Пожалуйста, установите 'pdfminer.six'.")
    except ValueError as e:
        logger.error(f"parse_fgos_pdf: Parser ValueError for {filename}: {e}")
        raise ValueError(f"Ошибка парсинга содержимого файла '{filename}': {e}")
    except Exception as e:
        logger.error(f"parse_fgos_pdf: Unexpected error during PDF parsing for {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")

# --- Функции для извлечения данных из HTML/Markdown Профстандартов ---

def html_to_markdown_enhanced(html_content: str) -> str:
    """Улучшенный конвертер HTML в Markdown с обработкой таблиц."""
    soup = BeautifulSoup(html_content, 'lxml')
    for script_or_style in soup(["script", "style"]):
        script_or_style.decompose()
    
    for table_tag in soup.find_all('table'):
        try:
            dfs = pd.read_html(str(table_tag), flavor='lxml', header=0, keep_default_na=False)
            if dfs:
                md_table_parts = []
                for df in dfs:
                    df.dropna(axis=0, how='all', inplace=True)
                    df.dropna(axis=1, how='all', inplace=True)
                    if not df.empty:
                         md_table_parts.append(df.to_markdown(index=False, tablefmt='pipe'))
                if md_table_parts:
                     table_tag.replace_with(BeautifulSoup("\n\n" + "\n\n".join(md_table_parts) + "\n\n", 'html.parser'))
            else:
                 logger.warning("html_to_markdown_enhanced: Pandas could not extract DataFrame from a table.")
        except Exception as e:
            logger.error(f"html_to_markdown_enhanced: Error processing table with Pandas: {e}. Table content: {str(table_tag)[:200]}", exc_info=True)

    markdown_text = markdownify(str(soup), heading_style="ATX", bullets='-').strip()
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
    return markdown_text

def extract_ps_metadata_simple(markdown_text: str) -> Dict[str, Any]:
    """
    Простое извлечение метаданных ПС (код, название, номер/дата приказа и т.д.) из начала Markdown текста.
    """
    metadata = {}
    search_area = markdown_text[:3000]
    # Pattern for code and name (more robust) - handles names with quotes or without
    code_name_match = re.search(
         r'(?:ПРОФЕССИОНАЛЬНЫЙ\s+СТАНДАРТ(?:\s*[\:\s]*"(.*?)")?(?:\s*[\:\s]*(.*?))?)\s*Код\s+(\d+\.\d+)',
         search_area, re.IGNORECASE | re.DOTALL
    )
    if code_name_match:
        # group(1) is name in quotes, group(2) is name without quotes, group(3) is code
        metadata['name'] = code_name_match.group(1) or code_name_match.group(2)
        metadata['code'] = code_name_match.group(3)
        if metadata.get('name'): metadata['name'] = metadata['name'].strip()
        logger.debug(f"extract_ps_metadata_simple: Found code '{metadata.get('code')}' and name '{metadata.get('name')}'")
    else:
         logger.warning("extract_ps_metadata_simple: Could not find PS code and name marker.")
         code_match_fallback = re.search(r'Код\s+(\d+\.\d+)', search_area, re.IGNORECASE)
         if code_match_fallback:
              metadata['code'] = code_match_fallback.group(1).strip()
              logger.warning(f"extract_ps_metadata_simple: Found code '{metadata.get('code')}' using fallback.")

    # Order date and number (Pattern: "утвержден приказом ... от DATE № NUMBER")
    order_match = re.search(
        r'утвержден\s+приказом.*?от\s+' # Start from "утвержден приказом ... от"
        r'(.+?)\s*г?\.?\s*[№N#]\s*(\d+[а-яА-Я-]*)', # Capture date string (.+? non-greedy), optional 'г.', optional '#№N', capture number
        search_area, re.IGNORECASE | re.DOTALL
    )
    if order_match:
        date_str_raw = order_match.group(1).strip()
        number_str = order_match.group(2).strip()
        metadata['order_date'] = _parse_date_from_text(date_str_raw)
        metadata['order_number'] = number_str
        if metadata.get('order_date'):
             logger.debug(f"extract_ps_metadata_simple: Found order date/number: №{metadata['order_number']} от {metadata['order_date']}")
        else:
             logger.warning(f"extract_ps_metadata_simple: Found order number '{metadata['order_number']}', but date '{date_str_raw}' could not be parsed.")

    # Registration date and number (Pattern: "зарегистрирован ... DATE г. регистрационный № NUMBER")
    registration_match = re.search(
        r'зарегистрирован\s+Министерством\s+юстиции.*?(\d{1,2}\.\d{1,2}\.\d{4})\s*г?\.?\s*регистрационный\s*[№N#]\s*(\d+)',
        search_area, re.IGNORECASE | re.DOTALL
    )
    if registration_match:
        date_str_raw = registration_match.group(1).strip()
        reg_number = registration_match.group(2).strip()
        metadata['registration_date'] = _parse_date_from_text(date_str_raw)
        metadata['registration_number'] = reg_number
        if metadata.get('registration_date'):
             logger.debug(f"extract_ps_metadata_simple: Found registration date/number: №{metadata['registration_number']} от {metadata['registration_date']}")
        else:
             logger.warning(f"extract_ps_metadata_simple: Found registration number '{metadata['registration_number']}', but date '{date_str_raw}' could not be parsed.")


    if not metadata.get('code'):
         logger.warning("extract_ps_metadata_simple: Missing core metadata (code) after parsing.")
         logger.debug(f"   - Parsed metadata: {metadata}")
    return metadata

def extract_ps_structure_detailed(markdown_text: str) -> Dict[str, Any]:
    """
    Извлекает детальную структуру ПС (ОТФ, ТФ, ТД, НУ, НЗ) из Markdown текста.
    """
    structure = {'generalized_labor_functions': []}
    otf_section_header_re = r'^[IVX]+\.\s+(?:Описание\s+трудовых\s+функций|Характеристика\s+обобщенных\s+трудовых\s+функций).*?(\n|$)'
    otf_header_re = r'^(\d+\.\d+)\.\s+Обобщенная\s+трудовая\s+функция'
    tf_header_re = r'^(\d+\.\d+\.\d+)\.\s+Трудовая\s+функция'
    list_header_re = r'^(Трудовые действия|Необходимые умения|Необходимые знания)'
    list_item_re = r'^-\s+(.*?)(\n|$)'
    current_otf = None; current_tf = None; current_list_type = None
    lines = markdown_text.splitlines()
    logger.debug("extract_ps_structure_detailed: Starting structure extraction from Markdown.")
    for line in lines:
        line = line.strip()
        if not line: continue
        if re.match(r'^[IVX]+\.\s+', line): # Новый раздел
             current_otf = None; current_tf = None; current_list_type = None
        otf_header_match = re.match(otf_header_re, line)
        if otf_header_match: # Новая ОТФ
            current_tf = None; current_list_type = None
            code = otf_header_match.group(1)
            name = f"ОТФ {code}"; qualification_level = None # Placeholder
            current_otf = {'code': code, 'name': name, 'qualification_level': qualification_level, 'labor_functions': []}
            structure['generalized_labor_functions'].append(current_otf)
            logger.debug(f"  Found ОТФ: {code}"); continue
        tf_header_match = re.match(tf_header_re, line)
        if tf_header_match and current_otf: # Новая ТФ
             current_list_type = None
             code = tf_header_match.group(1)
             name = f"ТФ {code}"; qualification_level = None # Placeholder
             current_tf = {'code': code, 'name': name, 'qualification_level': qualification_level, 'labor_actions': [], 'required_skills': [], 'required_knowledge': []}
             current_otf['labor_functions'].append(current_tf)
             logger.debug(f"    Found ТФ: {code} under OTF {current_otf['code']}"); continue
        list_header_match = re.match(list_header_re, line)
        if list_header_match and current_tf: # Заголовок списка
            list_type_text = list_header_match.group(1)
            if 'Трудовые действия' in list_type_text: current_list_type = 'labor_actions'
            elif 'Необходимые умения' in list_type_text: current_list_type = 'required_skills'
            elif 'Необходимые знания' in list_type_text: current_list_type = 'required_knowledge'
            else: current_list_type = None
            logger.debug(f"      Found list header: {list_type_text} under TF {current_tf['code']}"); continue
        list_item_match = re.match(list_item_re, line)
        if list_item_match and current_tf and current_list_type: # Элемент списка
             description = list_item_match.group(1).strip()
             if current_list_type == 'labor_actions': current_tf['labor_actions'].append({'description': description})
             elif current_list_type == 'required_skills': current_tf['required_skills'].append({'description': description})
             elif current_list_type == 'required_knowledge': current_tf['required_knowledge'].append({'description': description})
             continue
    if not structure['generalized_labor_functions']: logger.warning("extract_ps_structure_detailed: No Generalized Labor Functions (ОТФ) found.")
    logger.debug("extract_ps_structure_detailed: Finished structure extraction.")
    return structure

# --- Оркестратор парсинга файлов ПС ---

def parse_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Оркестрирует парсинг файла Профессионального Стандарта (HTML/DOCX/PDF).
    """
    logger.info(f"parse_prof_standard: Starting PS parsing orchestration for file: {filename}")
    markdown_text = ""; extracted_metadata = {}; error_message = None; error_type = None; file_type = 'unknown'
    try:
        lower_filename = filename.lower()
        if lower_filename.endswith(('.html', '.htm')):
            encoding = chardet.detect(file_bytes)['encoding'] or 'utf-8'
            html_content = file_bytes.decode(encoding, errors='ignore')
            markdown_text = html_to_markdown_enhanced(html_content)
            extracted_metadata = extract_ps_metadata_simple(markdown_text)
            file_type = 'html'
        elif lower_filename.endswith('.docx'):
            logger.warning(f"parse_prof_standard: DOCX parsing is not yet implemented for {filename}. Skipping.")
            error_message = "Парсинг DOCX файлов еще не реализован."; error_type = "not_implemented"; file_type = 'docx'
        elif lower_filename.endswith('.pdf'):
             logger.warning(f"parse_prof_standard: PDF parsing for PS is not yet implemented for {filename}. Skipping.")
             error_message = "Парсинг PDF файлов (структура ПС) еще не реализован."; error_type = "not_implemented"; file_type = 'pdf'
        else:
            logger.warning(f"parse_prof_standard: Unsupported file format for {filename}. Supported: HTML (.html, .htm).")
            error_message = "Неподдерживаемый формат файла. Поддерживаются только HTML."; error_type = "unsupported_format"; file_type = 'unknown'
        
        if error_message: return {"success": False, "error": error_message, "filename": filename, "error_type": error_type, "file_type": file_type}
        
        ps_code = extracted_metadata.get('code'); ps_name = extracted_metadata.get('name')
        if not ps_code or not ps_name:
            code_match_filename = re.search(r'ps[_-]?(\d+\.\d+)', lower_filename)
            if code_match_filename:
                 ps_code = ps_code or code_match_filename.group(1).strip()
                 ps_name = ps_name or f"Профессиональный стандарт с кодом из файла {ps_code}" # Placeholder name
                 logger.warning(f"parse_prof_standard: Extracted PS code '{ps_code}' from filename.")
            if not ps_code:
                logger.error(f"parse_prof_standard: Could not extract PS code from file '{filename}' or content.")
                error_message = "Не удалось извлечь код профессионального стандарта."; error_type = "parsing_error"
                return {"success": False, "error": error_message, "filename": filename, "error_type": error_type, "file_type": file_type}
        
        parsed_data: Dict[str, Any] = {
            'code': ps_code, 'name': ps_name, 'parsed_content_markdown': markdown_text,
            'order_number': extracted_metadata.get('order_number'), 'order_date': extracted_metadata.get('order_date'),
            'registration_number': extracted_metadata.get('registration_number'), 'registration_date': extracted_metadata.get('registration_date'),
            'valid_until': None 
        }
        logger.info(f"parse_prof_standard: Successfully parsed basic data for '{filename}' (Code: {ps_code}).")
        return {"success": True, "parsed_data": parsed_data, "filename": filename, "file_type": file_type}
    except Exception as e:
        logger.error(f"parse_prof_standard: Unexpected error parsing {filename}: {e}", exc_info=True)
        error_message = f"Неожиданная ошибка при парсинге файла '{filename}': {e}"; error_type = "unexpected_error"
        return {"success": False, "error": error_message, "filename": filename, "error_type": error_type, "file_type": file_type}

# def parse_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
#     """Адаптер для вызова parse_prof_standard, чтобы соответствовать старому API, если использовался."""
#     # This adapter function definition was duplicated.
#     # The one defined earlier in the file (that calls parse_prof_standard_orchestrator) is the correct one.
#     # This duplicated definition should be removed or commented out.
#     pass # Commenting out or remove this duplicated function definition

# --- Блок if __name__ == '__main__': для автономного тестирования ---
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    if len(sys.argv) < 2:
        print("Usage: python parsers.py <filepath> [<format>]"); sys.exit(1)
        
    test_file_path = sys.argv[1]
    
    if not os.path.exists(test_file_path):
        print(f"Error: File not found at '{test_file_path}'")
        sys.exit(1)
        
    with open(test_file_path, 'rb') as f:
        file_content = f.read()

    try:
        # Определяем тип файла по расширению или имени
        lower_filename = os.path.basename(test_file_path).lower()
        is_fgos_test = lower_filename.endswith('.pdf') and ("fgos" in lower_filename or "фгос" in lower_filename)
        # PS test should now include PDF as a format to test parse_prof_standard_orchestrator
        is_ps_test = lower_filename.endswith(('.html', '.htm', '.docx', '.pdf')) and ("ps" in lower_filename or "пс" in lower_filename)


        if is_fgos_test:
            print("\n--- Trying to parse as FGOS PDF ---")
            parsed_data = parse_fgos_pdf(file_content, os.path.basename(test_file_path))
            print("\n--- FGOS Parsing Result ---")
            print("Метаданные:", parsed_data.get('metadata'))
            print("\nУК Компетенции:", len(parsed_data.get('uk_competencies', [])))
            for comp in parsed_data.get('uk_competencies', []): print(f"  - {comp.get('code')}: {comp.get('name', '')[:80]}...")
            print("\nОПК Компетенции:", len(parsed_data.get('opk_competencies', [])))
            for comp in parsed_data.get('opk_competencies', []): print(f"  - {comp.get('code')}: {comp.get('name', '')[:80]}...")
            print("\nРекомендованные ПС:", parsed_data.get('recommended_ps_codes'))
            # print("\nСырой текст (превью):", parsed_data.get('raw_text', '')[:1000] + ("..." if len(parsed_data.get('raw_text', '')) > 1000 else ""))

        elif is_ps_test:
            print(f"\n--- Trying to parse as ProfStandard ---")
            # Use the orchestrator for PS parsing
            # parse_prof_standard_orchestrator expects filepath, not file_bytes and filename
            parsed_result = parse_prof_standard_orchestrator(test_file_path) # <--- ИСПРАВЛЕНО
            print("\n--- ProfStandard Parsing Result ---")
            if parsed_result.get('success'):
                 print("Статус: Успех")
                 parsed_content_data = parsed_result.get('parsed_data', {})
                 metadata = {k:v for k,v in parsed_content_data.items() if k not in ['parsed_content_markdown', 'structure']}
                 markdown_text = parsed_content_data.get('parsed_content_markdown', '')
                 structure = parsed_content_data.get('structure', {})
                 print("Метаданные:", metadata)
                 # print("\nMarkdown содержимое (превью):", markdown_text[:1000] + ("..." if len(markdown_text) > 1000 else ""))
                 if structure:
                     print("\nСтруктура (из Markdown):")
                     print(f"  ОТФ найдено: {len(structure.get('generalized_labor_functions',[]))}")
                     for otf in structure.get('generalized_labor_functions',[]):
                         print(f"    - ОТФ {otf.get('code')}: {otf.get('name')}, ТФ: {len(otf.get('labor_functions',[]))}")
                         for tf in otf.get('labor_functions', []):
                              print(f"      - ТФ {tf.get('code')}: {tf.get('name')}, ТД: {len(tf.get('labor_actions',[]))}, Умения: {len(tf.get('required_skills',[]))}, Знания: {len(tf.get('required_knowledge',[]))}")

            else:
                 print("Статус: Ошибка"); print("Ошибка:", parsed_result.get('error')); print("Тип ошибки:", parsed_result.get('error_type')); print("Тип файла:", parsed_result.get('file_type'))

        else: print(f"Неизвестный или не указан тип файла для теста (добавьте 'fgos' или 'ps' в имя файла или укажите формат): {file_format}, {test_file_path}")
    except FileNotFoundError: print(f"Error: File not found at '{test_file_path}'")
    except NotImplementedError as e: print(f"Error: {e}")
    except ValueError as e: print(f"Error: {e}")
    except Exception as e: print(f"An unexpected error occurred: {e}"); traceback.print_exc()

    print("\n--- Testing _parse_date_from_text ---")
    test_date_str1 = "7 августа 2020"
    parsed_date1 = _parse_date_from_text(test_date_str1)
    print(f"Input: '{test_date_str1}', Output: {parsed_date1} (Type: {type(parsed_date1)})")

    test_date_str2 = "07.08.2020"
    parsed_date2 = _parse_date_from_text(test_date_str2)
    print(f"Input: '{test_date_str2}', Output: {parsed_date2} (Type: {type(parsed_date2)})")

    test_date_str3 = "19 сентября 2017 г." # Из другого примера
    parsed_date3 = _parse_date_from_text(test_date_str3)
    print(f"Input: '{test_date_str3}', Output: {parsed_date3} (Type: {type(parsed_date3)})")

    test_date_str4 = "12.12.2016" # Новый тест
    parsed_date4 = _parse_date_from_text(test_date_str4)
    print(f"Input: '{test_date_str4}', Output: {parsed_date4} (Type: {type(parsed_date4)})")

    test_date_str5 = "26 ноября 2020 г." # Новый тест из Химической технологии
    parsed_date5 = _parse_date_from_text(test_date_str5)
    print(f"Input: '{test_date_str5}', Output: {parsed_date5} (Type: {type(parsed_date5)})")
    
    test_date_str6 = "8 февраля 2021 г." # Новый тест из ИВТ
    parsed_date6 = _parse_date_from_text(test_date_str6)
    print(f"Input: '{test_date_str6}', Output: {parsed_date6} (Type: {type(parsed_date6)})")