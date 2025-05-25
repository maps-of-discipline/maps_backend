# filepath: competencies_matrix/fgos_parser.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
from pdfminer.high_level import extract_text
import xml.etree.ElementTree as ET
import logging
# import pandas as pd 
from bs4 import BeautifulSoup
from markdownify import markdownify

from .parsing_utils import parse_date_string


logger = logging.getLogger(__name__)

def _clean_text_fgos(text: str) -> str:
    """
    Базовая очистка текста ФГОС от лишних пробелов, переносов и мусорных символов.
    Удаляет дефисы, разделяющие слова на разных строках, и схлопывает множественные пробелы/переносы.
    """
    # Удаление неразрывных пробелов и прочих "белых" символов, кроме обычного пробела и переноса строки
    text = re.sub(r'[^\S\n\r\t ]+', ' ', text)
    # Удаление дефисов в конце строки, за которыми следует перенос строки и продолжение слова
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    # Удаление дефисов в конце строки без продолжения слова (если это артефакт парсинга)
    text = re.sub(r'-\s*\n', '', text)
    # Замена любых переносных символов на единый перенос строки
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Схлопывание множественных пробелов
    text = re.sub(r'[ \t]+', ' ', text)
    # Схлопывание множественных переносов строки
    text = re.sub(r'\n[ \t]*\n', '\n\n', text)
    # Удаление пробелов в начале/конце строк
    text = re.sub(r'^[ \t]+|[ \t]+$', '', text, flags=re.MULTILINE)
    return text.strip()


def _extract_fgos_metadata(text: str) -> Dict[str, Any]:
    """Извлекает метаданные из текста ФГОС PDF."""
    metadata = {}
    # Расширим область поиска метаданных, т.к. они могут быть не только в самом начале
    search_area = text[:6000] # Увеличим область поиска на 6000 символов
    logger.debug(f"--- METADATA SEARCH AREA (first 500 chars) ---\n{search_area[:500]}\n--------------------------------------")

    # Уточним паттерн для номера и даты приказа
    order_match = re.search(
        r'(?:Приказ Министерства науки и высшего образования РФ от|утвержден приказом Министерства науки и высшего образования Российской Федерации)'
        r'\s*(?:от\s+)?(\d{1,2}\s+[а-яА-Я]+\s+\d{4}\s*г?\.?)\s*[N№#]\s*(\d+[а-яА-Я0-9-]*)',
        search_area, re.IGNORECASE | re.DOTALL
    )
    if order_match:
        date_str_raw = order_match.group(1).strip()
        metadata['order_date'] = parse_date_string(date_str_raw)
        metadata['order_number'] = order_match.group(2).strip()
        if metadata.get('order_date'):
             logger.info(f"_extract_fgos_metadata: Found order: №{metadata['order_number']} от {metadata['order_date']}")
        else:
             logger.warning(f"_extract_fgos_metadata: Found order number '{metadata['order_number']}', но дата '{date_str_raw}' не смогла быть распознана.")
    else:
        logger.warning("_extract_fgos_metadata: Order number and date not found using primary pattern. Trying alternative.")
        alt_order_number_match = re.search(r'(?:приказом|утвержден)\s.*?от\s+.+?\s*[№N#]\s*(\d+[а-яА-Я0-9-]*)', search_area, re.IGNORECASE | re.DOTALL)
        if alt_order_number_match:
            metadata['order_number'] = alt_order_number_match.group(1).strip()
            logger.warning(f"_extract_fgos_metadata: Found order number '{metadata['order_number']}' using ALTERNATIVE pattern (date not found or parsed separately).")
        else:
            logger.error("_extract_fgos_metadata: CRITICAL - Order number could not be found by any pattern.")

    # Уточним паттерн для кода и названия направления
    # ИСПРАВЛЕНО: Экранированы литеральные скобки в lookahead части
    direction_match = re.search(
        r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
        r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s*' # Code (e.g. 18.03.01)
        r'["«]?([^\n("»]+?)["»]?\s*' # Name (e.g. Химическая технология)
        # Lookahead for end markers: Escaping literal parentheses and handling exact phrases
        r'(?=\s*(?:'
        r'\(с\s+изменениями\s+и\s+дополнениями\)' # Match "(с изменениями и дополнениями)" literally
        r'|\n\s*I\.\s+Общие положения'
        r'|\n\s*С\s+изменениями\s+и\s+дополнениями\s+от:' # Exact phrase from provided PDF
        r'|Зарегистрировано\s+в\s+Минюсте'
        r'|$' # End of string
        r'|\(уровень\s+бакалавриата\)' # Literal "(уровень бакалавриата)"
        r'|\(далее\s+-\s+стандарт\)' # Literal "(далее - стандарт)"
        r'))', # End of non-capturing group and lookahead
        search_area, re.IGNORECASE | re.DOTALL
    )
    if direction_match:
        logger.debug(f"Direction_match primary found: group(1)='{direction_match.group(1)}', group(2)='{direction_match.group(2)}'")
        metadata['direction_code'] = direction_match.group(1).strip()
        name_raw = direction_match.group(2).strip()
        metadata['direction_name'] = re.sub(r'[\s"-]+$', '', name_raw).strip().replace('"', '')
        logger.info(f"_extract_fgos_metadata: Found direction: Code '{metadata['direction_code']}', Name '{metadata['direction_name']}'")
    else:
        logger.warning("_extract_fgos_metadata: Primary direction pattern not found. Trying simple fallback...")
        # Fallback for direction that might be split or less formally presented
        direction_match_simple = re.search(
            r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
            r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s*"?([^\n"]+?)"?\s*$',
            search_area, re.IGNORECASE | re.MULTILINE
        )
        if direction_match_simple:
            metadata['direction_code'] = direction_match_simple.group(1).strip()
            name_raw = direction_match_simple.group(2).strip()
            metadata['direction_name'] = re.sub(r'[\s"-]+$', '', name_raw).strip().replace('"', '')
            logger.info(f"_extract_fgos_metadata: Found direction (simple fallback): Code '{metadata['direction_code']}', Name '{metadata['direction_name']}'")
        else:
            logger.error("_extract_fgos_metadata: CRITICAL - Direction code and name not found by any pattern.")

    level_match = re.search(r'(?:высшего образования\s*-\s*|уровень\s+)(бакалавриата|магистратуры|специалитета)', search_area, re.IGNORECASE)
    if level_match:
        logger.debug(f"Level_match found: group(1)='{level_match.group(1)}'")
        metadata['education_level'] = level_match.group(1).lower().strip()
        logger.info(f"Found education level: '{metadata['education_level']}'")
    else:
        logger.error("_extract_fgos_metadata: CRITICAL - Education level not found.")

    generation_match_main = re.search(r'ФГОС\s+ВО(?:\s*\(?(3\+\+?)\)?)?', search_area, re.IGNORECASE)
    if generation_match_main and generation_match_main.group(1):
        gen_text = generation_match_main.group(1).lower().strip()
        metadata['generation'] = re.sub(r'[().,]+$', '', gen_text).strip()
        logger.info(f"Found generation (main pattern): '{metadata['generation']}'")
    else:
        logger.debug(f"FGOS generation_match_main not found or group(1) is None. Trying fallback.")
        generation_match_fallback = re.search(r'ФГОС\s+(3\+\+?)\b', search_area, re.IGNORECASE)
        if generation_match_fallback:
            metadata['generation'] = generation_match_fallback.group(1).lower().strip()
            logger.info(f"Found generation (fallback): '{metadata['generation']}'")
        else:
            logger.warning("FGOS generation explicitly not found. Setting to 'unknown'.")
            metadata['generation'] = 'unknown' 

    critical_fields = ['order_number', 'direction_code', 'education_level']
    missing_critical = [field for field in critical_fields if not metadata.get(field)]
    if not metadata.get('order_date'):
         logger.warning("'order_date' could not be extracted successfully.")

    if missing_critical:
         logger.error(f"Отсутствуют следующие КРИТИЧЕСКИЕ метаданные: {', '.join(missing_critical)}")
    else:
         logger.info("Все КРИТИЧЕСКИЕ метаданные извлечены.")

    logger.debug(f"Final extracted metadata before return: {metadata}")
    return metadata

def _extract_uk_opk(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Извлекает УК и ОПК компетенции (код, название, категория) из текста раздела III ФГОС.
    Улучшена обработка многострочных наименований и категорий.
    """
    competencies = {'uk_competencies': [], 'opk_competencies': []}

    section_iii_start_match = re.search(
        r'III\.\s*Требования\s+к\s+результатам\s+освоения\s+программы\s+бакалавриата',
        text, re.IGNORECASE | re.MULTILINE
    )
    if not section_iii_start_match:
        logger.warning("Section III start marker not found ('III. Требования к результатам...').")
        return competencies

    text_after_section_iii = text[section_iii_start_match.end():]

    section_iv_start_match = re.search(
        r'\n[ \t]*IV\.\s*Требования\s+к\s+условиям\s+реализации\s+программы\s+бакалавриата',
        text_after_section_iii, re.IGNORECASE | re.MULTILINE
    )

    section_iii_text = text_after_section_iii[:section_iv_start_match.start()] if section_iv_start_match else text_after_section_iii
    
    if not section_iii_text.strip():
        logger.warning("Section III text is empty after markers search.")
        return competencies

    logger.debug(f"Successfully isolated Section III text (length: {len(section_iii_text)} chars). Preview: {section_iii_text[:500]}...")

    # Объединенный паттерн для захвата категории и следующих за ней компетенций.
    # (?s) позволяет . соответствовать переводам строк
    # [ \t]* - позволяет пробелы и табы
    # (?:...) - не-захватывающие группы
    # \s* - любые пробельные символы (включая переводы строк)
    comp_block_pattern = re.compile(
        r'(?s)(?:Наименование\s+категории(?:.*?)\s+компетенций\s*\n)?' # Optional table header (non-capturing)
        r'(?P<category_name>[А-Я][а-я\s-]+(?:я|а|и|ы)(?::|\s+подготовка|\s+мышление|\s+деятельности)?)?\s*\n?' # Optional category name
        r'((?:[УО]К-\d+\s*[).:]?\s*.*?(?=\n(?:[УО]К-\d+|[А-Я][а-я\s-]+(?:я|а|и|ы)|\Z)))+)', # One or more competencies (capturing group)
        re.IGNORECASE | re.MULTILINE
    )
    
    # Паттерн для извлечения отдельной компетенции (код + название) внутри блока
    single_comp_pattern = re.compile(
        r'^(?P<code>[УО]К-\d+)\s*[).:]?\s*(?P<name>.+)',
        re.IGNORECASE | re.MULTILINE
    )

    current_category = None # Сброс категории для каждой итерации
    
    # Поиск категорий и компетенций в тексте раздела III
    # Обрабатываем текст построчно, чтобы лучше реагировать на изменения категорий
    lines = section_iii_text.splitlines()
    temp_comp_buffer = []

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        # Попытка найти категорию (если строка не начинается с УК/ОПК)
        if not re.match(r'^[УО]К-\d+', stripped_line, re.IGNORECASE):
            category_match = re.match(r'^[А-Я][а-я\s-]+(?:я|а|и|ы)(?::|\s+подготовка|\s+мышление|\s+деятельности)?$', stripped_line)
            if category_match:
                # Если найдена новая категория, обрабатываем накопленные компетенции
                if temp_comp_buffer:
                    for comp_code, comp_name, comp_category in temp_comp_buffer:
                        comp_data = {'code': comp_code, 'name': comp_name, 'indicators': [], 'category_name': comp_category}
                        if comp_code.startswith('УК-'): competencies['uk_competencies'].append(comp_data)
                        elif comp_code.startswith('ОПК-'): competencies['opk_competencies'].append(comp_data)
                        logger.debug(f"Parsed buffered {comp_code}: '{comp_name[:50]}...' (Category: '{comp_category}')")
                    temp_comp_buffer = []
                current_category = category_match.group(0).strip()
                logger.debug(f"Detected new category header: '{current_category}'")
                continue

        # Попытка найти компетенцию
        comp_match = re.match(r'^(?P<code>[УО]К-\d+)\s*[).:]?\s*(?P<name>.+)$', stripped_line, re.IGNORECASE)
        if comp_match:
            code = comp_match.group('code').strip().upper()
            name_raw = comp_match.group('name').strip()
            name_cleaned = re.sub(r'\s*\n\s*', ' ', name_raw).strip() # Схлопываем внутренние переносы
            name_cleaned = re.sub(r'\.$', '', name_cleaned) # Удаляем точку в конце
            
            if name_cleaned:
                # Накапливаем компетенции с текущей категорией
                temp_comp_buffer.append((code, name_cleaned, current_category))
                logger.debug(f"Buffered {code}: '{name_cleaned[:50]}...' (Current Category: '{current_category}')")
            continue

    # Обработка оставшихся компетенций после цикла (если раздел заканчивается компетенциями)
    if temp_comp_buffer:
        for comp_code, comp_name, comp_category in temp_comp_buffer:
            comp_data = {'code': comp_code, 'name': comp_name, 'indicators': [], 'category_name': comp_category}
            if comp_code.startswith('УК-'): competencies['uk_competencies'].append(comp_data)
            elif comp_code.startswith('ОПК-'): competencies['opk_competencies'].append(comp_data)
            logger.debug(f"Parsed remaining {comp_code}: '{comp_name[:50]}...' (Category: '{comp_category}')")

    logger.info(f"Parsed {len(competencies['uk_competencies'])} УК competencies and {len(competencies['opk_competencies'])} OПК competencies from section III.")

    return competencies


def _extract_recommended_ps_fgos(text: str) -> List[Dict[str, Any]]:
    """
    Извлекает коды и названия рекомендованных ПС из текста ФГОС.
    Улучшена обработка табличного формата на примере PDF.
    """
    ps_list = []
    # Ищем начало секции, используя более гибкий паттерн
    ps_section_start_match = re.search(
        r'(?s)(?:Приложение(?:\s*[N№]\s*\d+)?\s*к\s*федеральному\s+государственному\s+образовательному\s+стандарту\s+высшего\s+образования)?\s*\n?'
        r'(?:Перечень\s+профессиональных\s+стандартов,\s+соответствующих\s+профессиональной\s+деятельности\s+выпускников|Перечень(?:\s+и\s+)?(?:рекомендуемых\s+)?профессиональных\s+стандартов)',
        text, re.IGNORECASE
    )
    
    if not ps_section_start_match:
        logger.warning("Section 'Перечень профессиональных стандартов' or related Appendix not found.")
        return ps_list

    search_text_for_ps = text[ps_section_start_match.start():]
    
    # Ищем конец секции, используя более общие паттерны
    end_of_ps_list_match = re.search(
        r'(?s)(\n\s*(?:IV|V|VI|VII|VIII|IX|X)\.\s*Требования|\n\s*Сведения\s+об\s+организациях\s*-\s*разработчиках|\n\s*Информация\s+об\s+изменениях:|\n{3,})', 
        search_text_for_ps, re.IGNORECASE | re.MULTILINE
    )

    if end_of_ps_list_match:
        ps_list_raw_text = search_text_for_ps[:end_of_ps_list_match.start()]
        logger.debug(f"Found PS list text (length: {len(ps_list_raw_text)} chars) before next major section. Preview: {ps_list_raw_text[:1000]}...")
    else:
        ps_list_raw_text = search_text_for_ps 
        logger.warning(f"Could not find clear end of PS list. Analyzing remaining text (length: {len(ps_list_raw_text)} chars). Preview: {ps_list_raw_text[:1000]}...")

    # Паттерн для извлечения кода и названия ПС из строки вида "N. Код.000 Профессиональный стандарт "Название..."
    # Учитывает возможные переносы строк внутри названия и пробелы в коде.
    # Group 1: code (e.g. 26.001)
    # Group 2: name (e.g. Специалист по обеспечению комплексного контроля...)
    ps_pattern = re.compile(
        r'(?:\d+\s*\.\s*)?' # Optional numbering (1., 2., etc.)
        r'(?P<code>\d{2}\s*\.\s*\d{3})\s*' # PS Code (e.g. 26.001)
        r'Профессиональный\s+стандарт\s*' # "Профессиональный стандарт"
        r'"(?P<name>[^"]+?)"(?:,\s*утвержденный\s+приказом.*?(?:\d+\s+г\.)?,\s*регистрационный\s*[N№#]\s*\d+)?', # Name in quotes + optional order/reg details
        re.IGNORECASE | re.DOTALL # re.DOTALL allows '.' to match newlines inside quotes
    )

    for match in ps_pattern.finditer(ps_list_raw_text):
        code = match.group('code').replace(' ', '').strip()
        name_raw = match.group('name').strip()
        # Дополнительная очистка названия: убрать лишние пробелы, переносы
        name_cleaned = re.sub(r'\s*\n\s*', ' ', name_raw).strip()
        name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip() # Схлопывание нескольких пробелов

        if code and name_cleaned:
            ps_list.append({'code': code, 'name': name_cleaned})

    # Удаляем дубликаты и сортируем по коду
    unique_ps_list = []
    seen_codes = set()
    for ps_data in ps_list:
        if ps_data['code'] not in seen_codes:
            unique_ps_list.append(ps_data)
            seen_codes.add(ps_data['code'])
    
    unique_ps_list.sort(key=lambda x: x['code'])
    logger.info(f"Found {len(unique_ps_list)} recommended PS codes and names.")
    logger.debug(f"Recommended PS list: {unique_ps_list}")

    if not unique_ps_list and ps_list_raw_text.strip(): logger.warning("No PS codes extracted from the identified section text despite text existing. Check regex or text content.")
    elif not unique_ps_list and not ps_list_raw_text.strip(): logger.warning("No PS codes extracted from section because section text is empty.")

    return unique_ps_list


def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Главная функция парсинга PDF файла ФГОС ВО.
    """
    logger.info(f"Starting PDF parsing for FGOS file: {filename}")
    parsed_data: Dict[str, Any] = {
        'metadata': {},
        'uk_competencies': [],
        'opk_competencies': [],
        'recommended_ps': [], # Изменили с _codes на _list для словарей
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
             logger.error(f"Missing one or more CRITICAL metadata fields for {filename}. Aborting parsing.")
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}'. Отсутствуют: {', '.join(missing_critical)}.")

        logger.debug(f"Calling _extract_uk_opk with cleaned_text (first 500 chars):\n{cleaned_text[:500]}...")
        
        comp_data = _extract_uk_opk(cleaned_text)
        parsed_data['uk_competencies'] = comp_data.get('uk_competencies', [])
        parsed_data['opk_competencies'] = comp_data.get('opk_competencies', [])
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.warning(f"No UK or OPK competencies found for {filename}.")
        else:
             logger.info(f"Found {len(parsed_data['uk_competencies'])} UK and {len(parsed_data['opk_competencies'])} OPK competencies.")

        parsed_data['recommended_ps'] = _extract_recommended_ps_fgos(cleaned_text) # Изменили название поля
        
        logger.info(f"PDF parsing for FGOS {filename} finished. Metadata Extracted: {bool(parsed_data['metadata'])}, UK Found: {len(parsed_data['uk_competencies'])}, OPK Found: {len(parsed_data['opk_competencies'])}, Recommended PS Found: {len(parsed_data['recommended_ps'])}")
        
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies'] and not parsed_data['recommended_ps']:
             logger.warning(f"No competencies or recommended PS found for {filename} despite critical metadata being present.")

        return parsed_data

    except FileNotFoundError:
        logger.error(f"File not found: {filename}")
        raise
    except ImportError as e:
        logger.error(f"Missing dependency for reading PDF files: {e}. Please install 'pdfminer.six'.")
        raise ImportError(f"Отсутствует зависимость для чтения PDF файлов: {e}. Пожалуйста, установите 'pdfminer.six'.")
    except ValueError as e:
        logger.error(f"Parser ValueError for {filename}: {e}")
        raise ValueError(f"Ошибка парсинга содержимого файла '{filename}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error during PDF parsing for {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")


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
        parsed_data_root['order_date'] = parse_date_string(ps_element.findtext('DateOfApproval'))
        
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
             "parsed_data": parsed_data_root, 
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

def parse_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Оркестрирует парсинг файла Профессионального Стандарта (HTML/XML/DOCX/PDF).
    В MVP фокусируемся на XML.
    Возвращает словарь с извлеченными данными или ошибку.
    """
    logger.info(f"Starting PS parsing orchestration for file: {filename}")
    lower_filename = filename.lower()

    if lower_filename.endswith('.xml'):
        logger.info(f"Detected XML format for '{filename}'. Calling XML parser...")
        return parse_prof_standard_xml(file_bytes) 
        
    # elif lower_filename.endswith(('.html', '.htm')):
    #     logger.warning(f"HTML parsing for PS ('{filename}') is deprecated and not fully supported in MVP. Skipping.")
    #     return {"success": False, "error": "Парсинг HTML профстандартов устарел и не поддерживается в MVP. Используйте XML.", "filename": filename, "error_type": "deprecated_format"}
    
    # elif lower_filename.endswith('.docx'):
    #     logger.warning(f"DOCX parsing for PS ('{filename}') is not implemented. Skipping.")
    #     return {"success": False, "error": "Парсинг DOCX файлов еще не реализован.", "filename": filename, "error_type": "not_implemented"}
        
    elif lower_filename.endswith('.pdf'):
         logger.warning(f"PDF parsing for PS structure ('{filename}') is not implemented. Skipping.")
         return {"success": False, "error": "Парсинг PDF файлов (структура ПС) еще не реализован.", "filename": filename, "error_type": "not_implemented"}
         
    else:
        logger.warning(f"Unsupported file format for PS: {filename}. Supported: XML (.xml).")
        return {"success": False, "error": "Неподдерживаемый формат файла для ПС. Поддерживается только XML.", "filename": filename, "error_type": "unsupported_format"}