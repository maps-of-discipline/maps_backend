# competencies_matrix/parsers.py
"""
Модуль для парсинга Профессиональных Стандартов и ФГОС ВО в структурированные данные.
"""
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
from pdfminer.high_level import extract_text
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from markdownify import markdownify
import chardet
import pandas as pd
import logging
import traceback

logger = logging.getLogger(__name__)

# --- Функции для извлечения данных из PDF ФГОС ---

def _clean_text(text: str) -> str:
    """Базовая очистка текста от лишних пробелов и переносов."""
    text = text.replace('\r\n', '\n').replace('\r', '\n') # Нормализуем переносы строк
    text = re.sub(r'\n\s*\n', '\n', text) # Удаляем пустые строки
    text = re.sub(r'\s{2,}', ' ', text) # Заменяем множественные пробелы на один
    text = text.strip()
    return text

def _extract_fgos_metadata(text: str) -> Dict[str, Any]:
    """
    Извлекает метаданные (номер/дата приказа, код/название направления, уровень, поколение) из текста ФГОС PDF.
    Использует регулярные выражения для поиска ключевых фраз в начале документа.
    """
    metadata = {}
    search_area = text[:3000]

    # Номер и дата приказа
    order_match = re.search(r'от\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:г\.)?\s*[N№#]?\s*(\d+[а-яА-Я0-9-]*)', search_area, re.IGNORECASE)
    if order_match:
        date_str = order_match.group(1)
        number_str = order_match.group(2)
        try:
            # Нормализуем дату
            day, month, year = map(int, date_str.split('.'))
            metadata['order_date'] = datetime.date(year, month, day)
            metadata['order_number'] = number_str.strip()
            logger.debug(f"_extract_fgos_metadata: Found order: №{metadata['order_number']} от {metadata['order_date']}")
        except ValueError as e:
            logger.warning(f"_extract_fgos_metadata: Could not parse date '{date_str}' or number '{number_str}'. Error: {e}")
    else:
        logger.warning("_extract_fgos_metadata: Order number and date not found.")

    # Код и название направления подготовки
    direction_match = re.search(
        r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
        r'(\d{2}\.\d{2}\.\d{2})\s+' 
        r'([^\n(]+(?:\([^)]+\))?[^\n(]*)', 
        search_area, re.IGNORECASE
    )
    if direction_match:
        metadata['direction_code'] = direction_match.group(1).strip()
        name_raw = direction_match.group(2).strip()
        metadata['direction_name'] = re.sub(r'\s*-\s*$', '', name_raw).strip() # Убираем тире в конце
        logger.debug(f"_extract_fgos_metadata: Found direction: Code '{metadata['direction_code']}', Name '{metadata['direction_name']}'")
    else:
        logger.warning("_extract_fgos_metadata: Direction code and name not found.")

    # Уровень образования
    level_match = re.search(r'уровень\s+(бакалавриата|магистратуры|специалитета)', search_area, re.IGNORECASE)
    if level_match:
        metadata['education_level'] = level_match.group(1).lower().strip()
        logger.debug(f"_extract_fgos_metadata: Found education level: '{metadata['education_level']}'")
    else:
        logger.warning("_extract_fgos_metadata: Education level not found.")

    # Поколение ФГОС
    generation_match = re.search(r'ФГОС\s+ВО\s+(3\+\+|3\+)', search_area, re.IGNORECASE)
    if generation_match:
        metadata['generation'] = generation_match.group(1).lower().strip()
        logger.debug(f"_extract_fgos_metadata: Found generation: '{metadata['generation']}'")
    else:
        logger.warning("_extract_fgos_metadata: FGOS generation not found.")

    if not all([metadata.get('order_number'), metadata.get('order_date'), metadata.get('direction_code'), metadata.get('education_level')]):
         logger.warning("_extract_fgos_metadata: Missing one or more critical metadata fields after parsing.")
    logger.debug(f"   - Final extracted metadata: {metadata}")
    return metadata

def _extract_uk_opk(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Извлекает УК и ОПК компетенции (код, название) из текста раздела III ФГОС.
    """
    competencies = {'uk_competencies': [], 'opk_competencies': []}
    
    section_iii_start_match = re.search(r'^[ \t]*III\.[ \t\n]+Требования\s+к\s+результатам\s+освоения\s+программы', text, re.IGNORECASE | re.MULTILINE)
    if not section_iii_start_match:
        logger.warning("_extract_uk_opk: Section III start marker not found.")
        return competencies

    text_after_section_iii = text[section_iii_start_match.end():]
    section_iv_start_match = re.search(r'^[ \t]*IV\.[ \t\n]+Требования\s+к\s+условиям\s+реализации\s+программы', text_after_section_iii, re.IGNORECASE | re.MULTILINE)
    
    section_iii_text = text_after_section_iii[:section_iv_start_match.start()] if section_iv_start_match else text_after_section_iii
    if not section_iii_text.strip():
         logger.warning("_extract_uk_opk: Section III text is empty after markers search.")
         return competencies
    logger.debug(f"_extract_uk_opk: Successfully isolated Section III text (length: {len(section_iii_text)} chars).")

    # (?s) для DOTALL
    uk_block_match = re.search(r'(?s)Универсальные\s+компетенции\s* выпускника\s+обладают\s+следующими\s+универсальными\s+компетенциями:\s*(.*?)(?=\n[ \t]*(?:Общепрофессиональные|Профессиональные)\s+компетенции|\n[ \t]*IV\.)', section_iii_text, re.IGNORECASE)
    if not uk_block_match: # Пытаемся найти без "выпускника обладают..."
        uk_block_match = re.search(r'(?s)Универсальные\s+компетенции[^\n]*?\n\s*(.*?)(?=\n[ \t]*(?:Общепрофессиональные|Профессиональные)\s+компетенции|\n[ \t]*IV\.)', section_iii_text, re.IGNORECASE)

    if uk_block_match:
        uk_block_text = uk_block_match.group(1)
        logger.debug(f"_extract_uk_opk: Found UK block (length: {len(uk_block_text)} chars).")
        uk_matches = re.finditer(r'(УК-\d+)\s*[.:]?\s*((?:[^\n]+\n?)+?)(?=\n\s*УК-\d+|\Z)', _clean_text(uk_block_text), re.IGNORECASE | re.MULTILINE)
        for match in uk_matches:
            code = match.group(1).strip().upper()
            name = _clean_text(match.group(2).strip())
            if name.endswith('.'): name = name[:-1] # Убираем точку в конце
            competencies['uk_competencies'].append({'code': code, 'name': name, 'indicators': []})
        logger.debug(f"_extract_uk_opk: Parsed {len(competencies['uk_competencies'])} УК competencies.")
        if not competencies['uk_competencies']: logger.warning("_extract_uk_opk: No UKs parsed despite UK block found. Check regex for УК-N.")
    else:
        logger.warning("_extract_uk_opk: UK competencies block not found in Section III.")

    opk_block_match = re.search(r'(?s)Общепрофессиональные\s+компетенции\s* выпускника\s+обладают\s+следующими\s+общепрофессиональными\s+компетенциями:\s*(.*?)(?=\n[ \t]*Профессиональные\s+компетенции|\n[ \t]*IV\.)', section_iii_text, re.IGNORECASE)
    if not opk_block_match: # Пытаемся найти без "выпускника обладают..."
        opk_block_match = re.search(r'(?s)Общепрофессиональные\s+компетенции[^\n]*?\n\s*(.*?)(?=\n[ \t]*Профессиональные\s+компетенции|\n[ \t]*IV\.)', section_iii_text, re.IGNORECASE)

    if opk_block_match:
        opk_block_text = opk_block_match.group(1)
        logger.debug(f"_extract_uk_opk: Found OPK block (length: {len(opk_block_text)} chars).")
        opk_matches = re.finditer(r'(ОПК-\d+)\s*[.:]?\s*((?:[^\n]+\n?)+?)(?=\n\s*ОПК-\d+|\Z)', _clean_text(opk_block_text), re.IGNORECASE | re.MULTILINE)
        for match in opk_matches:
            code = match.group(1).strip().upper()
            name = _clean_text(match.group(2).strip())
            if name.endswith('.'): name = name[:-1] # Убираем точку в конце
            competencies['opk_competencies'].append({'code': code, 'name': name, 'indicators': []})
        logger.debug(f"_extract_uk_opk: Parsed {len(competencies['opk_competencies'])} ОПК competencies.")
        if not competencies['opk_competencies']: logger.warning("_extract_uk_opk: No OPKs parsed despite OPK block found. Check regex for ОПК-N.")
    else:
        logger.warning("_extract_uk_opk: OPK competencies block not found in Section III.")

    return competencies

def _extract_recommended_ps(text: str) -> List[str]:
    """
    Извлекает список кодов рекомендованных профессиональных стандартов из текста ФГОС.
    """
    ps_codes = []
    ps_section_match = re.search(
        r'(?s)(Перечень\s+профессиональных\s+стандартов,\s+соответствующих\s+профессиональной\s+деятельности\s+выпускников'
        r'|Приложение\s+к\s+федеральному\s+государственному\s+образовательному\s+стандарту.*?Перечень\s+профессиональных\s+стандартов)'
        r'.*?(\n\s*\n|$)',
        text, re.IGNORECASE
    )
    
    if not ps_section_match:
        logger.warning("_extract_recommended_ps: Section 'Перечень профессиональных стандартов' or related Appendix not found.")
        return ps_codes
    
    search_text_for_ps_codes = text[ps_section_match.start():]
    end_of_ps_list_match = re.search(r'(?s)(\n\s*(?:IV|V|VI|VII|VIII|IX|X)\.\s+|\n\s*Сведения\s+об\s+организациях\s*-\s*разработчиках)', search_text_for_ps_codes, re.IGNORECASE | re.MULTILINE)
    
    if end_of_ps_list_match:
        ps_list_text = search_text_for_ps_codes[:end_of_ps_list_match.start()]
        logger.debug(f"_extract_recommended_ps: Found PS list text (length: {len(ps_list_text)} chars) before next major section.")
    else:
        ps_list_text = search_text_for_ps_codes[:5000] # Ограничиваем поиск
        logger.warning("_extract_recommended_ps: Could not find clear end of PS list. Analyzing a limited text block.")

    code_matches = re.finditer(r'\b(\d{2}\.\d{3})\b', ps_list_text)
    for match in code_matches:
        ps_codes.append(match.group(1))

    ps_codes = sorted(list(set(ps_codes)))
    logger.debug(f"_extract_recommended_ps: Found {len(ps_codes)} recommended PS codes: {ps_codes}")
    if not ps_codes: logger.warning("_extract_recommended_ps: No PS codes extracted from the identified section.")
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
        if not all([parsed_data['metadata'].get('order_number'), parsed_data['metadata'].get('order_date'),
                    parsed_data['metadata'].get('direction_code'), parsed_data['metadata'].get('education_level')]):
             logger.error(f"parse_fgos_pdf: Missing one or more CRITICAL metadata fields for {filename}. Aborting parsing.")
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}'.")

        comp_data = _extract_uk_opk(cleaned_text)
        parsed_data['uk_competencies'] = comp_data.get('uk_competencies', [])
        parsed_data['opk_competencies'] = comp_data.get('opk_competencies', [])
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.warning(f"parse_fgos_pdf: No UK or OPK competencies found for {filename}.")

        parsed_data['recommended_ps_codes'] = _extract_recommended_ps(cleaned_text)

        logger.info(f"PDF parsing for FGOS {filename} finished. Metadata Extracted: {bool(parsed_data['metadata'])}, UK Found: {len(parsed_data['uk_competencies'])}, OPK Found: {len(parsed_data['opk_competencies'])}, Recommended PS Found: {len(parsed_data['recommended_ps_codes'])}")
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
            logger.error(f"html_to_markdown_enhanced: Error processing table with Pandas: {e}. Table content: {str(table_tag)[:200]}")

    markdown_text = markdownify(str(soup), heading_style="ATX", bullets='-').strip()
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
    return markdown_text

def extract_ps_metadata_simple(markdown_text: str) -> Dict[str, Any]:
    """
    Простое извлечение метаданных ПС (код, название, номер/дата приказа и т.д.) из начала Markdown текста.
    """
    metadata = {}
    search_area = markdown_text[:3000] 
    code_name_match = re.search(
         r'(?:ПРОФЕССИОНАЛЬНЫЙ СТАНДАРТ(?:\s*[\:\s]*"(.*?)"|\s*[\:\s]*(.*?)))?\s*Код\s+(\d+\.\d+)',
         search_area, re.IGNORECASE | re.DOTALL
    )
    if code_name_match:
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
    order_match = re.search(
        r'утвержден\s+приказом.*?от\s+'
        r'(\d{1,2})\s+(\S+)\s+(\d{4})\s+г\.\s+[№N]\s*(\d+[а-яА-Я-]?)',
        search_area, re.IGNORECASE | re.DOTALL
    )
    if order_match:
        day = int(order_match.group(1))
        month_name = order_match.group(2).lower()
        year = int(order_match.group(3))
        order_number = order_match.group(4).strip()
        month_names = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}
        month = month_names.get(month_name)
        if month:
            try:
                metadata['order_date'] = datetime.date(year, month, day)
                metadata['order_number'] = order_number
                logger.debug(f"extract_ps_metadata_simple: Found order date/number: №{metadata['order_number']} от {metadata['order_date']}")
            except ValueError: logger.warning(f"extract_ps_metadata_simple: Could not parse date components for PS order date: {year}-{month}-{day}")
        else: logger.warning(f"extract_ps_metadata_simple: Could not parse month name '{month_name}' for PS order date.")
    registration_match = re.search(
        r'зарегистрирован\s+Министерством\s+юстиции.*?(\d{1,2})\s+(\S+)\s+(\d{4})\s+г\.\s+регистрационный\s+[№N]\s*(\d+)',
        search_area, re.IGNORECASE | re.DOTALL
    )
    if registration_match:
        day = int(registration_match.group(1))
        month_name = registration_match.group(2).lower()
        year = int(registration_match.group(3))
        reg_number = registration_match.group(4).strip()
        month_names = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}
        month = month_names.get(month_name)
        if month:
            try:
                metadata['registration_date'] = datetime.date(year, month, day)
                metadata['registration_number'] = reg_number
                logger.debug(f"extract_ps_metadata_simple: Found registration date/number: №{metadata['registration_number']} от {metadata['registration_date']}")
            except ValueError: logger.warning(f"extract_ps_metadata_simple: Could not parse date components for PS registration date: {year}-{month}-{day}")
        else: logger.warning(f"extract_ps_metadata_simple: Could not parse month name '{month_name}' for PS registration date.")
    if not metadata.get('code') or not metadata.get('name'):
         logger.warning("extract_ps_metadata_simple: Missing core metadata (code or name) after parsing.")
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
            logger.debug(f"  Found OTF: {code}"); continue
        tf_header_match = re.match(tf_header_re, line)
        if tf_header_match and current_otf: # Новая ТФ
             current_list_type = None
             code = tf_header_match.group(1)
             name = f"ТФ {code}"; qualification_level = None # Placeholder
             current_tf = {'code': code, 'name': name, 'qualification_level': qualification_level, 'labor_actions': [], 'required_skills': [], 'required_knowledge': []}
             current_otf['labor_functions'].append(current_tf)
             logger.debug(f"    Found TF: {code} under OTF {current_otf['code']}"); continue
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

def parse_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Адаптер для вызова parse_prof_standard, чтобы соответствовать старому API, если использовался."""
    return parse_prof_standard(file_bytes, filename)

# --- Блок if __name__ == '__main__': для автономного тестирования ---
if __name__ == '__main__':
    import sys
    import os
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    if len(sys.argv) < 2:
        print("Usage: python parsers.py <filepath> [<format>]"); sys.exit(1)
    test_file_path = sys.argv[1]
    file_format_arg = sys.argv[2].lower() if len(sys.argv) > 2 else None
    file_extension = os.path.splitext(test_file_path)[1][1:].lower()
    file_format = file_format_arg or file_extension
    if not os.path.exists(test_file_path): print(f"Error: File not found at '{test_file_path}'"); sys.exit(1)
    with open(test_file_path, 'rb') as f: file_content = f.read()
    try:
        if file_format == 'pdf' and "fgos" in test_file_path.lower(): # Примерное определение, что это ФГОС
            parsed_data = parse_fgos_pdf(file_content, os.path.basename(test_file_path))
            print("\n--- Результат парсинга ФГОС ---")
            print("Метаданные:", parsed_data.get('metadata'))
            print("\nУК Компетенции:", len(parsed_data.get('uk_competencies', [])))
            for comp in parsed_data.get('uk_competencies', []): print(f"  - {comp.get('code')}: {comp.get('name', '')[:80]}...")
            print("\nОПК Компетенции:", len(parsed_data.get('opk_competencies', [])))
            for comp in parsed_data.get('opk_competencies', []): print(f"  - {comp.get('code')}: {comp.get('name', '')[:80]}...")
            print("\nРекомендованные ПС:", parsed_data.get('recommended_ps_codes'))
            # print("\nСырой текст (превью):", parsed_data.get('raw_text', '')[:1000] + ("..." if len(parsed_data.get('raw_text', '')) > 1000 else ""))
        elif file_format in ['html', 'htm'] or (file_format == 'pdf' and "ps" in test_file_path.lower()): # Примерное определение, что это ПС
            # Для ПС PDF парсинг не реализован в parse_prof_standard, но if __name__ может его вызвать
            if file_format == 'pdf':
                 print("Предупреждение: Парсинг PDF для Профстандартов (структура) не реализован в parse_prof_standard. Тест может быть неполным.")
            parsed_result = parse_prof_standard(file_content, os.path.basename(test_file_path))
            print("\n--- Результат парсинга Профстандарта ---")
            if parsed_result.get('success'):
                 print("Статус: Успех")
                 parsed_content = parsed_result.get('parsed_data', {})
                 metadata = {k:v for k,v in parsed_content.items() if k != 'parsed_content_markdown'}
                 markdown_text = parsed_content.get('parsed_content_markdown', '')
                 print("Метаданные:", metadata)
                 # print("\nMarkdown содержимое (превью):", markdown_text[:1000] + ("..." if len(markdown_text) > 1000 else ""))
                 if markdown_text:
                     structure = extract_ps_structure_detailed(markdown_text)
                     print("\nСтруктура (из Markdown):")
                     print(f"  ОТФ найдено: {len(structure.get('generalized_labor_functions',[]))}")
                     for otf in structure.get('generalized_labor_functions',[]):
                         print(f"    - ОТФ {otf.get('code')}: {otf.get('name')}, ТФ: {len(otf.get('labor_functions',[]))}")

            else:
                 print("Статус: Ошибка"); print("Ошибка:", parsed_result.get('error')); print("Тип ошибки:", parsed_result.get('error_type')); print("Тип файла:", parsed_result.get('file_type'))
        else: print(f"Неизвестный или не указан тип файла для теста (добавьте 'fgos' или 'ps' в имя файла или укажите формат): {file_format}, {test_file_path}")
    except FileNotFoundError: print(f"Error: File not found at '{test_file_path}'")
    except NotImplementedError as e: print(f"Error: {e}")
    except ValueError as e: print(f"Error: {e}")
    except Exception as e: print(f"An unexpected error occurred: {e}"); traceback.print_exc()

