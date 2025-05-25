# filepath: competencies_matrix/parsers.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
from pdfminer.high_level import extract_text
import xml.etree.ElementTree as ET
import logging
import pandas as pd # Для обработки HTML профстандартов
# Импорт для работы с HTML (если потребуется снова)
from bs4 import BeautifulSoup
from markdownify import markdownify


logger = logging.getLogger(__name__)

# --- Shared Parsing Helpers ---

def _parse_date_string(date_str: Optional[str]) -> Optional[datetime.date]:
    """
    Attempts to parse date strings from common formats (YYYY-MM-DD, DD.MM.YYYY, DD MonthName YYYY).
    Handles variations in format and returns a datetime.date object or None if parsing fails.
    """
    if not date_str:
        logger.debug("_parse_date_string: Input date string is empty.")
        return None

    date_str = date_str.strip()

    # Try YYYY-MM-DD format (common in XML)
    try:
        parsed_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        logger.debug(f"_parse_date_string: Successfully parsed '{date_str}' as YYYY-MM-DD.")
        return parsed_date
    except ValueError:
        logger.debug(f"_parse_date_string: '{date_str}' did not match YYYY-MM-DD format. Trying other formats.")
        pass 

    # Try DD.MM.YYYY format
    try:
        parsed_date = datetime.datetime.strptime(date_str, '%d.%m.%Y').date()
        logger.debug(f"_parse_date_string: Successfully parsed '{date_str}' as DD.MM.YYYY.")
        return parsed_date
    except ValueError:
        logger.debug(f"_parse_date_string: '{date_str}' did not match DD.MM.YYYY format.")
        pass 

    # Try DD MonthName YYYY format (e.g., '7 августа 2020', '19 сентября 2017 г.')
    month_names = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
        'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    # Pattern: Day(1-2 digits) + spaces + MonthName + optional 'года' + spaces + Year(4 digits) + optional ' г.'
    match = re.match(r'(\d{1,2})\s+([а-яА-Я]+)(?:\s+года)?\s+(\d{4})\s*г?\.?', date_str, re.IGNORECASE)
    if match:
        day_str, month_name_str, year_str = match.groups()[:3] 
        month = month_names.get(month_name_str.lower())
        if month:
            try:
                parsed_date = datetime.date(int(year_str), month, int(day_str))
                logger.debug(f"_parse_date_string: Successfully parsed '{date_str}' as DD MonthName YYYY.")
                return parsed_date
            except ValueError:
                logger.warning(f"_parse_date_string: Invalid date components for format 'DD MonthName YYYY': {year_str}-{month}-{day_str}")
                return None
        else:
            logger.warning(f"_parse_date_string: Unknown month name '{month_name_str}' for format 'DD MonthName YYYY'.")
            return None

    logger.warning(f"_parse_date_string: Could not parse date string: '{date_str}' using any known format.")
    return None

# --- FGOS PDF Parsing ---

def _clean_text_fgos(text: str) -> str:
    """Базовая очистка текста ФГОС от лишних пробелов и переносов."""
    # Нормализуем переносы строк
    text = text.replace('\r\n', '\n').replace('\r', '\n') 
    # Объединяем слова, разделенные дефисом и переносом строки
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text) 
    # Удаляем висячие дефисы в конце строк
    text = re.sub(r'-\n', '', text) 
    # Заменяем множественные пробелы/табуляции на один пробел
    text = re.sub(r'[ \t]+', ' ', text) 
    # Схлопываем пустые строки до одной пустой строки (\n\n)
    text = re.sub(r'\n[ \t]*\n', '\n\n', text) 
    text = text.strip() 
    return text


def _extract_fgos_metadata(text: str) -> Dict[str, Any]:
    """Извлекает метаданные из текста ФГОС PDF."""
    metadata = {}
    search_area = text[:4000] 
    logger.debug(f"--- METADATA SEARCH AREA (first 500 chars) ---\n{search_area[:500]}\n--------------------------------------")

    # Паттерн для номера приказа и даты
    order_match = re.search(
        r'от\s+(.+?)\s*г\.?\s*[N№#]\s*(\d+[а-яА-Я0-9-]*)', 
        search_area, re.IGNORECASE | re.DOTALL
    )
    if order_match:
        date_str_raw = order_match.group(1).strip()
        number_str = order_match.group(2).strip()
        logger.debug(f"Attempting to parse date_str_raw: '{date_str_raw}'")
        metadata['order_date'] = _parse_date_string(date_str_raw)
        metadata['order_number'] = number_str
        if metadata.get('order_date'):
             logger.info(f"_extract_fgos_metadata: Found order: №{metadata['order_number']} от {metadata['order_date']}")
        else:
             logger.warning(f"_extract_fgos_metadata: Found order number '{metadata['order_number']}', но дата '{date_str_raw}' не смогла быть распознана.")
    else:
        logger.warning("_extract_fgos_metadata: Order number and date not found using pattern 'от DATE г. № NUMBER'. Trying alternative.")
        alt_order_number_match = re.search(r'(?:приказом|утвержден)\s.*?от\s+.+?\s*[№N#]\s*(\d+[а-яА-Я0-9-]*)', search_area, re.IGNORECASE | re.DOTALL)
        if alt_order_number_match:
            metadata['order_number'] = alt_order_number_match.group(1).strip()
            logger.warning(f"_extract_fgos_metadata: Found order number '{metadata['order_number']}' using ALTERNATIVE pattern (date not found or parsed separately).")
        else:
            logger.error("_extract_fgos_metadata: CRITICAL - Order number could not be found by any pattern.")

    # Паттерн для кода и названия направления
    direction_match = re.search(
        r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
        r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s+'
        r'([^\n(]+?(?:\([^)]+\))?[^\n(]*?)(?=\s*(?:\(с изменениями|\n\s*I\.\s+Общие положения|\n\s*С изменениями|Зарегистрировано в Минюсте|$))',
        search_area, re.IGNORECASE
    )
    if direction_match:
        logger.debug(f"Direction_match primary found: group(1)='{direction_match.group(1)}', group(2)='{direction_match.group(2)}'")
        metadata['direction_code'] = direction_match.group(1).strip()
        name_raw = direction_match.group(2).strip()
        metadata['direction_name'] = re.sub(r'[\s"-]+$', '', name_raw).strip().replace('"', '')
        logger.info(f"_extract_fgos_metadata: Found direction: Code '{metadata['direction_code']}', Name '{metadata['direction_name']}'")
    else:
        logger.warning("_extract_fgos_metadata: Primary direction pattern not found. Trying simple fallback...")
        direction_match_simple = re.search(
            r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
            r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s*"?([^\n"]+?)"?\s*$', 
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

    # Паттерн для уровня образования
    level_match = re.search(r'(?:высшего образования\s*-\s*|уровень\s+)(бакалавриата|магистратуры|специалитета)', search_area, re.IGNORECASE)
    if level_match:
        logger.debug(f"Level_match found: group(1)='{level_match.group(1)}'")
        metadata['education_level'] = level_match.group(1).lower().strip()
        logger.info(f"_extract_fgos_metadata: Found education level: '{metadata['education_level']}'")
    else:
        logger.error("_extract_fgos_metadata: CRITICAL - Education level not found.")

    # Паттерн для поколения ФГОС (3+, 3++)
    generation_match_main = re.search(r'ФГОС\s+ВО(?:\s*\(?(3\+\+?)\)?)?', search_area, re.IGNORECASE)
    if generation_match_main and generation_match_main.group(1):
        gen_text = generation_match_main.group(1).lower().strip()
        metadata['generation'] = re.sub(r'[().,]+$', '', gen_text).strip()
        logger.info(f"_extract_fgos_metadata: Found generation (main pattern): '{metadata['generation']}'")
    else:
        logger.debug(f"FGOS generation_match_main not found or group(1) is None. Trying fallback.")
        generation_match_fallback = re.search(r'ФГОС\s+(3\+\+?)\b', search_area, re.IGNORECASE)
        if generation_match_fallback:
            metadata['generation'] = generation_match_fallback.group(1).lower().strip()
            logger.info(f"_extract_fgos_metadata: Found generation (fallback): '{metadata['generation']}'")
        else:
            logger.warning("_extract_fgos_metadata: FGOS generation explicitly not found. Setting to 'unknown'.")
            metadata['generation'] = 'unknown' 

    # Проверка на наличие критически важных полей
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

    section_iii_start_match = re.search(
        r'III\.\s*Требования\s+к\s+результатам\s+освоения\s+программы',
        text, re.IGNORECASE | re.MULTILINE
    )
    if not section_iii_start_match:
        logger.warning("_extract_uk_opk: Section III start marker not found ('III. Требования к результатам...').")
        return competencies

    text_after_section_iii = text[section_iii_start_match.end():]

    section_iv_start_match = re.search(
        r'\n[ \t]*IV\.\s*Требования\s+к\s+условиям\s+реализации\s+программы',
        text_after_section_iii, re.IGNORECASE | re.MULTILINE
    )

    section_iii_text = text_after_section_iii[:section_iv_start_match.start()] if section_iv_start_match else text_after_section_iii
    
    if not section_iii_text.strip():
        logger.warning("_extract_uk_opk: Section III text is empty after markers search.")
        return competencies

    logger.debug(f"_extract_uk_opk: Successfully isolated Section III text (length: {len(section_iii_text)} chars). Preview: {section_iii_text[:500]}...")

    # Define common patterns that mark the end of a competence description
    # or the start of unwanted footer/info text.
    # This pattern will be used to 'trim' the extracted name.
    end_of_comp_patterns = [
        r'\n\s*Информация об изменениях:.*', # General info block
        r'\n\s*\d{1,2}\.\d{1,2}\.\d{4}\s+Система\s+ГАРАНТ\s+\d{1,2}/\d{1,2}', # Page footer (e.g., "16.06.2021 Система ГАРАНТ 5/13")
        r'\n\s*УК-\d+', # Start of next UK
        r'\n\s*ОПК-\d+', # Start of next OPK
        r'\n\s*Профессиональные\s+компетенци(?:и|я)', # Start of PK block
        r'\n\s*Общепрофессиональные\s+компетенци(?:и|я)', # Start of OPK block
        r'\n\s*Таблица\s+\d+', # Start of a table
        r'\n{2,}', # Two or more consecutive newlines (might indicate paragraph/block end)
        r'\s*$', # End of string if nothing else
    ]
    # Compile a single regex to find any of these patterns from the end of a string
    # We want to remove everything from the first match of these patterns
    end_of_comp_regex = re.compile(
        '|'.join(f'(?:{p})' for p in end_of_comp_patterns), 
        re.IGNORECASE | re.MULTILINE | re.DOTALL 
    )

    # Regex for individual competencies: Capture code and then the name which can span multiple lines (non-greedy)
    # The lookahead is simplified to just find the *next* competence code or major section start
    # Note: the .+? ensures non-greedy match of the name.
    uk_comp_re = r'^(УК-\d+)\s*[).:]?\s*(.+?)(?=\n[ \t]*(?:УК-\d+|ОПК-\d+|Общепрофессиональные\s+компетенци|Профессиональные\s+компетенци)|\Z)'
    opk_comp_re = r'^(ОПК-\d+)\s*[).:]?\s*(.+?)(?=\n[ \t]*(?:ОПК-\d+|Профессиональные\s+компетенци|\Z))'

    # --- Parse UK competencies ---
    uk_block_match = re.search(r'(?s)Универсальные\s+компетенци(?:и|я).*?:\s*(.*?)(?=\n[ \t]*(?:Общепрофессиональные|Профессиональные)\s+компетенци(?:и|я)|\n[ \t]*IV\.\s*Требования|\Z)', section_iii_text, re.IGNORECASE)
    if uk_block_match:
        uk_block_text = uk_block_match.group(1)
        uk_matches = re.finditer(uk_comp_re, uk_block_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in uk_matches:
            code = match.group(1).strip().upper()
            name_raw = match.group(2).strip()
            
            # Remove any trailing garbage/footers
            name_cleaned = end_of_comp_regex.split(name_raw, 1)[0].strip() # Split at first match, take first part
            name_cleaned = re.sub(r'\.$', '', name_cleaned) # Remove trailing dot
            name_cleaned = re.sub(r'\s*\n\s*', ' ', name_cleaned) # Collapse newlines
            name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip() # Collapse multiple spaces
            
            if name_cleaned:
                competencies['uk_competencies'].append({'code': code, 'name': name_cleaned, 'indicators': []})
        logger.debug(f"Parsed {len(competencies['uk_competencies'])} УК competencies.")
        if not competencies['uk_competencies'] and uk_block_text.strip():
             logger.warning("_extract_uk_opk: No UKs parsed despite UK block found and not empty.")
    else:
        logger.warning("_extract_uk_opk: UK competencies block not found in Section III.")

    # --- Parse OPK competencies ---
    opk_block_match = re.search(r'(?s)Общепрофессиональные\s+компетенци(?:и|я).*?:\s*(.*?)(?=\n[ \t]*Профессиональные\s+компетенци(?:и|я)|\n[ \t]*IV\.\s*Требования|\Z)', section_iii_text, re.IGNORECASE)
    if opk_block_match:
        opk_block_text = opk_block_match.group(1)
        opk_matches = re.finditer(opk_comp_re, opk_block_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in opk_matches:
            code = match.group(1).strip().upper()
            name_raw = match.group(2).strip()
            
            # Remove any trailing garbage/footers
            name_cleaned = end_of_comp_regex.split(name_raw, 1)[0].strip() # Split at first match, take first part
            name_cleaned = re.sub(r'\.$', '', name_cleaned) # Remove trailing dot
            name_cleaned = re.sub(r'\s*\n\s*', ' ', name_cleaned) # Collapse newlines
            name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip() # Collapse multiple spaces
            
            if name_cleaned:
                competencies['opk_competencies'].append({'code': code, 'name': name_cleaned, 'indicators': []})
        logger.debug(f"Parsed {len(competencies['opk_competencies'])} ОПК competencies.")
        if not competencies['opk_competencies'] and opk_block_text.strip():
             logger.warning("_extract_uk_opk: No OPKs parsed despite OPK block found and not empty.")
    else:
        logger.warning("_extract_uk_opk: OPK competencies block not found in Section III.")

    return competencies


def _extract_recommended_ps_fgos(text: str) -> List[str]:
    """Извлекает коды рекомендованных ПС из текста ФГОС."""
    ps_codes = []
    # Flexible search for the start of the PS list section
    ps_section_match = re.search(
        r'(?s)(Перечень(?:\s+и\s+)?(?:рекомендуемых\s+)?профессиональных\s+стандартов'
        r'|Приложение\s*(?:[N№]\s*\d+)?\s*к\s*ФГОС\s*ВО.*?Перечень\s+профессиональных\s+стандартов)', 
        text, re.IGNORECASE
    )
    
    if not ps_section_match:
        logger.warning("_extract_recommended_ps_fgos: Section 'Перечень профессиональных стандартов' or related Appendix not found.")
        return ps_codes

    search_text_for_ps_codes = text[ps_section_match.start():]
    
    # Define end markers (next major section, information blocks, multiple newlines)
    end_of_ps_list_match = re.search(
        r'(?s)(\n\s*(?:IV|V|VI|VII|VIII|IX|X)\.\s*Требования|\n\s*Сведения\s+об\s+организациях\s*-\s*разработчиках|\n\s*Информация\s+об\s+изменениях:|\n{3,})', 
        search_text_for_ps_codes, re.IGNORECASE | re.MULTILINE
    )

    if end_of_ps_list_match:
        ps_list_text = search_text_for_ps_codes[:end_of_ps_list_match.start()]
        logger.debug(f"_extract_recommended_ps_fgos: Found PS list text (length: {len(ps_list_text)} chars) before next major section. Preview: {ps_list_text[:1000]}...")
    else:
        ps_list_text = search_text_for_ps_codes 
        logger.warning(f"_extract_recommended_ps_fgos: Could not find clear end of PS list. Analyzing remaining text (length: {len(ps_list_text)} chars). Preview: {ps_list_text[:1000]}...")

    # Find PS codes (e.g., 06.001) in the extracted text
    # Make regex more robust to spaces around the dot.
    # Also, ensure it doesn't pick up other numbers that look like codes (e.g., page numbers or dates)
    # The (?:[N№#]?\s*п/?п?\s*\d+\.\s+)? is to optionally capture leading list markers like "1. ", "N п/п 1."
    code_matches = re.finditer(r'(?:[N№#]?\s*п/?п?\s*\d+\.\s+)?\b(\d{2}\s*\.\s*\d{3})\b', ps_list_text, re.IGNORECASE)

    for match in code_matches:
        # Clean the extracted code (remove spaces around dot)
        clean_code = match.group(1).replace(' ', '').strip()
        ps_codes.append(clean_code)

    ps_codes = sorted(list(set(ps_codes)))
    logger.debug(f"_extract_recommended_ps_fgos: Found {len(ps_codes)} recommended PS codes: {ps_codes}")

    if not ps_codes and ps_list_text.strip(): logger.warning("_extract_recommended_ps_fgos: No PS codes extracted from the identified section text despite text existing. Check regex or text content.")
    elif not ps_codes and not ps_list_text.strip(): logger.warning("_extract_recommended_ps_fgos: No PS codes extracted from section, because section text is empty.")

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
        cleaned_text = _clean_text_fgos(text_content) 

        parsed_data['metadata'] = _extract_fgos_metadata(cleaned_text)

        critical_fields = ['order_number', 'direction_code', 'education_level']
        missing_critical = [field for field in critical_fields if not parsed_data['metadata'].get(field)]
        
        if missing_critical:
             logger.error(f"parse_fgos_pdf: Missing one or more CRITICAL metadata fields for {filename}. Aborting parsing.")
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}'. Отсутствуют: {', '.join(missing_critical)}.")

        logger.debug(f"parse_fgos_pdf: Calling _extract_uk_opk with cleaned_text (first 500 chars):\n{cleaned_text[:500]}...")
        
        comp_data = _extract_uk_opk(cleaned_text)
        parsed_data['uk_competencies'] = comp_data.get('uk_competencies', [])
        parsed_data['opk_competencies'] = comp_data.get('opk_competencies', [])
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.warning(f"parse_fgos_pdf: No UK or OPK competencies found for {filename}.")
        else:
             logger.info(f"parse_fgos_pdf: Found {len(parsed_data['uk_competencies'])} UK and {len(parsed_data['opk_competencies'])} OPK competencies.")

        parsed_data['recommended_ps_codes'] = _extract_recommended_ps_fgos(cleaned_text) 

        logger.info(f"PDF parsing for FGOS {filename} finished. Metadata Extracted: {bool(parsed_data['metadata'])}, UK Found: {len(parsed_data['uk_competencies'])}, OPK Found: {len(parsed_data['opk_competencies'])}, Recommended PS Found: {len(parsed_data['recommended_ps_codes'])}")
        
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


# --- ProfStandard XML Parsing Function ---

def parse_prof_standard_xml(xml_content: bytes) -> Dict[str, Any]:
    """
    Парсит XML-файл Профессионального Стандарта.
    Возвращает словарь с извлеченными данными (включая структуру) или ошибку.
    """
    parsed_data_root: Dict[str, Any] = {
        'code': None,
        'name': None,
        'order_number': None,
        'order_date': None,
        'registration_number': None, 
        'registration_date': None,   
        'activity_area_name': None,
        'activity_purpose': None,
        'generalized_labor_functions': []
    }

    try:
        root = ET.parse(io.BytesIO(xml_content)).getroot()
        logger.debug("XML parsed successfully with ElementTree.")
        
        ps_element = root.find('.//ProfessionalStandart') 
        if ps_element is None:
            logger.error("Тег <ProfessionalStandart> не найден в XML.")
            return {"success": False, "error": "Тег <ProfessionalStandart> не найден.", "parsed_data": None}

        parsed_data_root['name'] = ps_element.findtext('NameProfessionalStandart')
        parsed_data_root['registration_number'] = ps_element.findtext('RegistrationNumber')
        
        first_section = ps_element.find('FirstSection')
        if first_section is not None:
            parsed_data_root['code'] = first_section.findtext('CodeKindProfessionalActivity')
            parsed_data_root['activity_area_name'] = first_section.findtext('KindProfessionalActivity')
            parsed_data_root['activity_purpose'] = first_section.findtext('PurposeKindProfessionalActivity')
        else:
            logger.warning("Тег <FirstSection> не найден, код ПС и области деятельности могут отсутствовать.")

        parsed_data_root['order_number'] = ps_element.findtext('OrderNumber')
        parsed_data_root['order_date'] = _parse_date_string(ps_element.findtext('DateOfApproval'))
        
        if not parsed_data_root['code'] or not parsed_data_root['name']:
            logger.error("Не удалось извлечь обязательные поля: код или название ПС из метаданных.")
            return {"success": False, "error": "Не удалось извлечь код или название ПС из метаданных.", "parsed_data": parsed_data_root}

        otf_elements_container = ps_element.find('.//ThirdSection/WorkFunctions/GeneralizedWorkFunctions')
        if otf_elements_container is not None:
            for otf_elem in otf_elements_container.findall('GeneralizedWorkFunction'):
                otf_data = {
                    'code': otf_elem.findtext('CodeOTF'),
                    'name': otf_elem.findtext('NameOTF'),
                    'qualification_level': otf_elem.findtext('LevelOfQualification'),
                    'labor_functions': []
                }
                
                tf_elements_container = otf_elem.find('ParticularWorkFunctions')
                if tf_elements_container is not None:
                    for tf_elem in tf_elements_container.findall('ParticularWorkFunction'):
                        tf_data = {
                            'code': tf_elem.findtext('CodeTF'),
                            'name': tf_elem.findtext('NameTF'),
                            'qualification_level': tf_elem.findtext('SubQualification'), 
                            'labor_actions': [],
                            'required_skills': [],
                            'required_knowledge': []
                        }
                        
                        la_container = tf_elem.find('LaborActions')
                        if la_container is not None:
                            for i, la_elem in enumerate(la_container.findall('LaborAction')):
                                la_description = la_elem.text.strip() if la_elem.text else ""
                                if la_description: 
                                     tf_data['labor_actions'].append({'description': la_description, 'order': i})
                        
                        rs_container = tf_elem.find('RequiredSkills')
                        if rs_container is not None:
                            for i, rs_elem in enumerate(rs_container.findall('RequiredSkill')):
                                rs_description = rs_elem.text.strip() if rs_elem.text else ""
                                if rs_description: 
                                     tf_data['required_skills'].append({'description': rs_description, 'order': i})
                                
                        rk_container = tf_elem.find('NecessaryKnowledges') 
                        if rk_container is not None:
                            for i, rk_elem in enumerate(rk_container.findall('NecessaryKnowledge')):
                                rk_description = rk_elem.text.strip() if rk_elem.text else ""
                                if rk_description: 
                                     tf_data['required_knowledge'].append({'description': rk_description, 'order': i})
                                
                        otf_data['labor_functions'].append(tf_data)
                parsed_data_root['generalized_labor_functions'].append(otf_data)
        
        logger.info(f"Успешно спарсен ПС из XML: {parsed_data_root.get('code')} - {parsed_data_root.get('name')}")
        result = {
             "success": True,
             "parsed_data": parsed_data_root, # Return the root dict containing metadata and structure
             "error": None,
        }
        logger.debug(f"parse_prof_standard_xml: Returning data keys: {list(result['parsed_data'].keys())}")
        return result

    except ET.ParseError as e:
        logger.error(f"Ошибка парсинга XML: {e}", exc_info=True)
        return {"success": False, "error": f"Ошибка парсинга XML: {e}", "parsed_data": None}
    except Exception as e:
        logger.error(f"Неожиданная ошибка при парсинге XML ПС: {e}", exc_info=True)
        return {"success": False, "error": f"Неожиданная ошибка: {e}", "parsed_data": None}

# --- Orchestrator for ProfStandard Parsing ---

def parse_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Оркестрирует парсинг файла Профессионального Стандарта (HTML/XML/DOCX/PDF).
    В MVP фокусируемся на XML.
    Возвращает словарь с извлеченными данными или ошибку.
    """
    logger.info(f"parse_prof_standard: Starting PS parsing orchestration for file: {filename}")
    lower_filename = filename.lower()

    if lower_filename.endswith('.xml'):
        logger.info(f"   Detected XML format for '{filename}'. Calling XML parser...")
        return parse_prof_standard_xml(file_bytes) 
        
    elif lower_filename.endswith(('.html', '.htm')):
        logger.warning(f"   HTML parsing for PS ('{filename}') is deprecated and not fully supported in MVP. Skipping.")
        return {"success": False, "error": "Парсинг HTML профстандартов устарел и не поддерживается в MVP. Используйте XML.", "filename": filename, "error_type": "deprecated_format"}
    
    elif lower_filename.endswith('.docx'):
        logger.warning(f"   DOCX parsing for PS ('{filename}') is not implemented. Skipping.")
        return {"success": False, "error": "Парсинг DOCX файлов еще не реализован.", "filename": filename, "error_type": "not_implemented"}
        
    elif lower_filename.endswith('.pdf'):
         logger.warning(f"   PDF parsing for PS structure ('{filename}') is not implemented. Skipping.")
         return {"success": False, "error": "Парсинг PDF файлов (структура ПС) еще не реализован.", "filename": filename, "error_type": "not_implemented"}
         
    else:
        logger.warning(f"   Unsupported file format for PS: {filename}. Supported: XML (.xml).")
        return {"success": False, "error": "Неподдерживаемый формат файла для ПС. Поддерживается только XML.", "filename": filename, "error_type": "unsupported_format"}