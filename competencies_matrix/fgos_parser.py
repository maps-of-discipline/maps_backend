# filepath: competencies_matrix/fgos_parser.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
from pdfminer.high_level import extract_text
import xml.etree.ElementTree as ET
import logging

from .parsing_utils import parse_date_string
from .nlp import parse_fgos_with_gemini 

logger = logging.getLogger(__name__)

def _clean_text_fgos(text: str) -> str:
    # ... (код функции остаётся без изменений) ...
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
    # ... (код функции остаётся без изменений) ...
    """Извлекает метаданные из текста ФГОС PDF."""
    metadata = {}
    search_area = text[:6000] 
    logger.debug(f"--- METADATA SEARCH AREA (first 500 chars) ---\n{search_area[:500]}\n--------------------------------------")

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

    direction_match = re.search(
        r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
        r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s*' 
        r'["«]?([^\n("»]+?)["»]?\s*' 
        r'(?=\s*(?:'
        r'\(с\s+изменениями\s+и\s+дополнениями\)' 
        r'|\n\s*I\.\s+Общие положения'
        r'|\n\s*С\s+изменениями\s+и\s+дополнениями\s+от:' 
        r'|Зарегистрировано\s+в\s+Минюсте'
        r'|$' 
        r'|\(уровень\s+бакалавриата\)' 
        r'|\(далее\s+-\s+стандарт\)' 
        r'))', 
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

def _add_buffered_comp_to_list(competencies_dict, comp_data):
    # ... (код функции остаётся без изменений) ...
    """Helper to clean and add a competence from buffer to the main list."""
    code, name_raw, category = comp_data
    name_cleaned = re.sub(r'\s*\n\s*', ' ', name_raw).strip() 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip() 
    name_cleaned = re.sub(r'\.$', '', name_cleaned).strip() 

    if not name_cleaned:
        logger.warning(f"Skipping buffered competence {code} due to empty name after cleanup.")
        return

    comp_obj = {'code': code, 'name': name_cleaned, 'indicators': [], 'category_name': category}
    if code.startswith('УК-'):
        competencies_dict['uk_competencies'].append(comp_obj)
    elif code.startswith('ОПК-'):
        competencies_dict['opk_competencies'].append(comp_obj)
    logger.debug(f"Added {code}: '{name_cleaned[:50]}...' (Category: '{category}') to final list.")


def _extract_uk_opk(text: str) -> Dict[str, List[Dict[str, Any]]]:
    # ... (код функции остаётся без изменений) ...
    """
    Извлекает УК и ОПК компетенции (код, название, категория) из текста раздела III ФГОС.
    Улучшена обработка многострочных наименований и категорий, а также ОПК.
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

    category_pattern = re.compile(
        r'^(?!УК-|ОПК-)([А-ЯЁ][а-яё\s-]+?(?:я|а|и|ы|ь|е)(?::|\s+подготовка|\s+мышление|\s+деятельности|\s+взаимодействие|\s+позиция|\s+компетентность))',
        re.IGNORECASE | re.MULTILINE
    )
    comp_pattern = re.compile(
        r'^(?P<code>[УО]К-\d+)\s*[).:]?\s*(?P<name>.+)$',
        re.IGNORECASE | re.MULTILINE
    )

    lines = section_iii_text.splitlines()
    current_category = "Без категории"
    comp_buffer: Optional[List[str]] = None

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        comp_match = comp_pattern.match(stripped_line)
        if comp_match:
            code = comp_match.group('code').strip().upper()
            name_part = comp_match.group('name').strip()

            if comp_buffer and comp_buffer[0] == code:
                comp_buffer[1] = f"{comp_buffer[1]} {name_part}"
                logger.debug(f"Appended to buffered {code}: '{comp_buffer[1][:50]}...' (continuation)")
            else:
                if comp_buffer:
                    _add_buffered_comp_to_list(competencies, comp_buffer)
                comp_buffer = [code, name_part, current_category]
                logger.debug(f"Started buffer for {code}: '{name_part[:50]}...' (Category: '{current_category}')")
            continue

        category_match = category_pattern.match(stripped_line)
        if category_match:
            if comp_buffer:
                _add_buffered_comp_to_list(competencies, comp_buffer)
                comp_buffer = None
            current_category = category_match.group(1).strip()
            logger.debug(f"Detected new category: '{current_category}'")
            continue
        
        if comp_buffer:
            comp_buffer[1] = f"{comp_buffer[1]} {stripped_line}"
            logger.debug(f"Continuing name for buffered {comp_buffer[0]}: '{comp_buffer[1][:50]}...'")
            
    if comp_buffer:
        _add_buffered_comp_to_list(competencies, comp_buffer)

    logger.info(f"Parsed {len(competencies['uk_competencies'])} УК competencies and {len(competencies['opk_competencies'])} ОПК competencies.")
    return competencies


def _extract_recommended_ps_fgos(text: str) -> List[Dict[str, Any]]:
    # ... (код функции остаётся без изменений) ...
    """
    Извлекает коды и названия рекомендованных ПС из текста ФГОС.
    Улучшена обработка табличного формата на примере PDF.
    """
    ps_list = []
    ps_section_start_match = re.search(
        r'(?s)(?:Приложение(?:\s*[N№]\s*\d+)?\s*к\s*федеральному\s+государственному\s+образовательному\s+стандарту\s+высшего\s+образования)?\s*\n?'
        r'(?:Перечень\s+профессиональных\s+стандартов,\s+соответствующих\s+профессиональной\s+деятельности\s+выпускников|Перечень(?:\s+и\s+)?(?:рекомендуемых\s+)?профессиональных\s+стандартов)',
        text, re.IGNORECASE
    )
    
    if not ps_section_start_match:
        logger.warning("Section 'Перечень профессиональных стандартов' or related Appendix not found.")
        return ps_list

    search_text_for_ps = text[ps_section_start_match.start():]
    
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

    ps_pattern = re.compile(
        r'(?:\d+\s*\.\s*)?'
        r'(?P<code>\d{2}\s*\.\s*\d{3})\s*' 
        r'Профессиональный\s+стандарт\s*' 
        r'"(?P<name>[^"]+?)"(?:,\s*утвержденный\s+приказом.*?(?:\d+\s+г\.)?,\s*регистрационный\s*[N№#]\s*\d+[а-яА-Я0-9-]*)?', 
        re.IGNORECASE | re.DOTALL 
    )

    for match in ps_pattern.finditer(ps_list_raw_text):
        code = match.group('code').replace(' ', '').strip()
        name_raw = match.group('name').strip()
        name_cleaned = re.sub(r'\s*\n\s*', ' ', name_raw).strip()
        name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip() 

        if code and name_cleaned:
            ps_list.append({'code': code, 'name': name_cleaned})

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
    Теперь использует NLP-модуль для извлечения структурированных данных.
    """
    logger.info(f"Starting PDF parsing for FGOS file: {filename} using NLP module.")
    
    try:
        text_content = extract_text(io.BytesIO(file_bytes))
        parsed_data_from_nlp = parse_fgos_with_gemini(text_content)
        
        if not all(k in parsed_data_from_nlp for k in ['metadata', 'uk_competencies', 'opk_competencies', 'recommended_ps']):
            raise ValueError("NLP parser did not return all required top-level keys.")
        
        parsed_data_from_nlp['raw_text'] = text_content

        critical_fields = ['order_number', 'direction_code', 'education_level']
        # ИСПРАВЛЕНО: Заменено 'critical_data_from_nlp' на 'parsed_data_from_nlp'
        missing_critical = [field for field in critical_fields if not parsed_data_from_nlp['metadata'].get(field)]
        
        if missing_critical:
             logger.error(f"Missing one or more CRITICAL metadata fields after NLP parsing for {filename}. Missing: {', '.join(missing_critical)}.")
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}' через NLP-парсер. Отсутствуют: {', '.join(missing_critical)}.")
        
        logger.info(f"PDF parsing for FGOS {filename} finished via NLP. Metadata Extracted: {bool(parsed_data_from_nlp['metadata'])}, UK Found: {len(parsed_data_from_nlp['uk_competencies'])}, OPK Found: {len(parsed_data_from_nlp['opk_competencies'])}, Recommended PS Found: {len(parsed_data_from_nlp['recommended_ps'])}")
        
        return parsed_data_from_nlp

    except FileNotFoundError:
        logger.error(f"File not found: {filename}")
        raise
    except ImportError as e:
        logger.error(f"Missing dependency (pdfminer.six or google-genai): {e}.")
        raise ImportError(f"Отсутствует зависимость: {e}. Пожалуйста, установите необходимые пакеты.")
    except ValueError as e:
        logger.error(f"Data validation error after NLP parsing for {filename}: {e}")
        raise ValueError(f"Ошибка валидации данных после NLP-парсинга для файла '{filename}': {e}")
    except RuntimeError as e: # Catch RuntimeError from nlp_parser for API issues
        logger.error(f"NLP parsing failed for {filename}: {e}", exc_info=True)
        raise Exception(f"Не удалось спарсить ФГОС с помощью NLP-модуля: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during PDF parsing for {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")

def parse_prof_standard_xml(xml_content: bytes) -> Dict[str, Any]:
    # ... (код функции остаётся без изменений) ...
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
    # ... (код функции остаётся без изменений) ...
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
        
    elif lower_filename.endswith(('.html', '.htm')):
        logger.warning(f"HTML parsing for PS ('{filename}') is deprecated and not fully supported in MVP. Skipping.")
        return {"success": False, "error": "Парсинг HTML профстандартов устарел и не поддерживается в MVP. Используйте XML.", "filename": filename, "error_type": "deprecated_format"}
    
    elif lower_filename.endswith('.docx'):
        logger.warning(f"DOCX parsing for PS ('{filename}') is not implemented. Skipping.")
        return {"success": False, "error": "Парсинг DOCX файлов еще не реализован.", "filename": filename, "error_type": "not_implemented"}
        
    elif lower_filename.endswith('.pdf'):
         logger.warning(f"PDF parsing for PS structure ('{filename}') is not implemented. Skipping.")
         return {"success": False, "error": "Парсинг PDF файлов (структура ПС) еще не реализован.", "filename": filename, "error_type": "not_implemented"}
         
    else:
        logger.warning(f"Unsupported file format for PS: {filename}. Supported: XML (.xml).")
        return {"success": False, "error": "Неподдерживаемый формат файла для ПС. Поддерживается только XML.", "filename": filename, "error_type": "unsupported_format"}