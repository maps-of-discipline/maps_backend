# filepath: competencies_matrix/fgos_parser.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
from pdfminer.high_level import extract_text
import xml.etree.ElementTree as ET
import logging
import pandas as pd
from bs4 import BeautifulSoup
from markdownify import markdownify


logger = logging.getLogger(__name__)

def _parse_date_string(date_str: Optional[str]) -> Optional[datetime.date]:
    """Attempts to parse date strings from common formats (YYYY-MM-DD, DD.MM.YYYY, DD MonthName YYYY)."""
    if not date_str: return None

    date_str = date_str.strip()

    try: return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError: pass 

    try: return datetime.datetime.strptime(date_str, '%d.%m.%Y').date()
    except ValueError: pass 

    month_names = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
        'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    match = re.match(r'(\d{1,2})\s+([а-яА-Я]+)(?:\s+года)?\s+(\d{4})\s*г?\.?', date_str, re.IGNORECASE)
    if match:
        day_str, month_name_str, year_str = match.groups()[:3] 
        month = month_names.get(month_name_str.lower())
        if month:
            try: return datetime.date(int(year_str), month, int(day_str))
            except ValueError: logger.warning(f"Invalid date components for '{date_str}': {year_str}-{month}-{day_str}"); return None
        else: logger.warning(f"Unknown month name '{month_name_str}' for '{date_str}'."); return None

    logger.warning(f"Could not parse date string: '{date_str}' using any known format.")
    return None

def _clean_text_fgos(text: str) -> str:
    """Cleans FGOS text by normalizing newlines, merging hyphenated words, and collapsing spaces."""
    text = text.replace('\r\n', '\n').replace('\r', '\n') 
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text) 
    text = re.sub(r'-\n', '', text) 
    text = re.sub(r'[ \t]+', ' ', text) 
    text = re.sub(r'\n[ \t]*\n', '\n\n', text) 
    return text.strip()


def _extract_fgos_metadata(text: str) -> Dict[str, Any]:
    """Extracts metadata (order number/date, direction code/name, education level, generation) from FGOS PDF text."""
    metadata = {}
    search_area = text[:4000] 

    order_match = re.search(
        r'от\s+(.+?)\s*г\.?\s*[N№#]\s*(\d+[а-яА-Я0-9-]*)', 
        search_area, re.IGNORECASE | re.DOTALL
    )
    if order_match:
        date_str_raw = order_match.group(1).strip()
        metadata['order_date'] = _parse_date_string(date_str_raw)
        metadata['order_number'] = order_match.group(2).strip()
    else:
        logger.warning("Order number and date not found using primary pattern. Trying alternative.")
        alt_order_number_match = re.search(r'(?:приказом|утвержден)\s.*?от\s+.+?\s*[№N#]\s*(\d+[а-яА-Я0-9-]*)', search_area, re.IGNORECASE | re.DOTALL)
        if alt_order_number_match: metadata['order_number'] = alt_order_number_match.group(1).strip()
        else: logger.error("CRITICAL - Order number could not be found by any pattern.")

    direction_match = re.search(
        r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
        r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s+'
        r'([^\n(]+?(?:\([^)]+\))?[^\n(]*?)(?=\s*(?:\(с изменениями|\n\s*I\.\s+Общие положения|\n\s*С изменениями|Зарегистрировано в Минюсте|$))',
        search_area, re.IGNORECASE
    )
    if direction_match:
        metadata['direction_code'] = direction_match.group(1).strip()
        name_raw = direction_match.group(2).strip()
        metadata['direction_name'] = re.sub(r'[\s"-]+$', '', name_raw).strip().replace('"', '')
    else:
        logger.warning("Primary direction pattern not found. Trying simple fallback...")
        direction_match_simple = re.search(
            r'(?:по\s+направлению\s+подготовки|по\s+специальности)\s+'
            r'\(?(\d{2}\.\d{2}\.\d{2})\)?\s*"?([^\n"]+?)"?\s*$', 
            search_area, re.IGNORECASE | re.MULTILINE
        )
        if direction_match_simple:
            metadata['direction_code'] = direction_match_simple.group(1).strip()
            name_raw = direction_match_simple.group(2).strip()
            metadata['direction_name'] = re.sub(r'[\s"-]+$', '', name_raw).strip().replace('"', '')
        else: logger.error("CRITICAL - Direction code and name not found by any pattern.")

    level_match = re.search(r'(?:высшего образования\s*-\s*|уровень\s+)(бакалавриата|магистратуры|специалитета)', search_area, re.IGNORECASE)
    if level_match: metadata['education_level'] = level_match.group(1).lower().strip()
    else: logger.error("CRITICAL - Education level not found.")

    generation_match_main = re.search(r'ФГОС\s+ВО(?:\s*\(?(3\+\+?)\)?)?', search_area, re.IGNORECASE)
    if generation_match_main and generation_match_main.group(1):
        gen_text = generation_match_main.group(1).lower().strip()
        metadata['generation'] = re.sub(r'[().,]+$', '', gen_text).strip()
    else:
        generation_match_fallback = re.search(r'ФГОС\s+(3\+\+?)\b', search_area, re.IGNORECASE)
        if generation_match_fallback: metadata['generation'] = generation_match_fallback.group(1).lower().strip()
        else: logger.warning("FGOS generation explicitly not found. Setting to 'unknown'."); metadata['generation'] = 'unknown' 

    critical_fields = ['order_number', 'direction_code', 'education_level']
    missing_critical = [field for field in critical_fields if not metadata.get(field)]
    if not metadata.get('order_date'): logger.warning("'order_date' could not be extracted successfully.")
    if missing_critical: logger.error(f"Missing CRITICAL metadata fields: {', '.join(missing_critical)}")
    return metadata

def _extract_uk_opk(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extracts UK and OPK competencies (code, name, category) from Section III of FGOS text.
    Prioritizes parsing from table-like structures.
    """
    competencies = {'uk_competencies': [], 'opk_competencies': []}

    section_iii_start_match = re.search(
        r'III\.\s*Требования\s+к\s+результатам\s+освоения\s+программы',
        text, re.IGNORECASE | re.MULTILINE
    )
    if not section_iii_start_match:
        logger.warning("Section III start marker not found ('III. Требования к результатам...').")
        return competencies

    text_after_section_iii = text[section_iii_start_match.end():]

    section_iv_start_match = re.search(
        r'\n[ \t]*IV\.\s*Требования\s+к\s+условиям\s+реализации\s+программы',
        text_after_section_iii, re.IGNORECASE | re.MULTILINE
    )

    section_iii_text = text_after_section_iii[:section_iv_start_match.start()] if section_iv_start_match else text_after_section_iii
    
    if not section_iii_text.strip():
        logger.warning("Section III text is empty after markers search.")
        return competencies

    end_of_comp_patterns = [
        r'\n\s*Информация об изменениях:.*', 
        r'\n\s*\d{1,2}\.\d{1,2}\.\d{4}\s+Система\s+ГАРАНТ\s+\d{1,2}/\d{1,2}', 
        r'\n{3,}', 
        r'\s*$' 
    ]
    end_of_comp_regex = re.compile(
        '|'.join(f'(?:{p})' for p in end_of_comp_patterns), 
        re.IGNORECASE | re.MULTILINE | re.DOTALL 
    )

    table_header_match = re.search(
        r'(?s)(Наименование\s+категории(?:.*?)\s+компетенций)\s*(?:\||[\t\s]+)' 
        r'(Код\s+и\s+наименование\s+(?:универсальной|общепрофессиональной)\s+компетенции\s+выпускника)', 
        section_iii_text, re.IGNORECASE
    )

    if table_header_match:
        table_start_pos = table_header_match.start()
        competency_table_text = section_iii_text[table_start_pos:]
        
        current_category = ""
        for line in competency_table_text.splitlines():
            line = line.strip()
            if not line: continue

            category_heading_match = re.match(r'^(?![УО]К-\d+)([А-Я][а-я\s-]+(?:я|а|и|ы))(?::|\s+подготовка|\s+мышление|\s+деятельности)?$', line)
            if category_heading_match:
                current_category = category_heading_match.group(1).strip()
                continue

            comp_match = re.match(r'^([УО]К-\d+)\s*[).:]?\s*(.+)$', line, re.IGNORECASE)
            if comp_match:
                code = comp_match.group(1).strip().upper()
                name_raw = comp_match.group(2).strip()
                
                name_cleaned = re.sub(r'\.$', '', name_raw) 
                name_cleaned = re.sub(r'\s*\n\s*', ' ', name_cleaned) 
                name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip() 
                
                if name_cleaned:
                    comp_data = {'code': code, 'name': name_cleaned, 'indicators': [], 'category_name': current_category if current_category else None}
                    if code.startswith('УК-'): competencies['uk_competencies'].append(comp_data)
                    elif code.startswith('ОПК-'): competencies['opk_competencies'].append(comp_data)
                continue
        
        if not competencies['uk_competencies'] and not competencies['opk_competencies'] and competency_table_text.strip():
             logger.warning("No UK/OPK parsed despite table-like structure found.")

    else:
        logger.warning("Table-like header for competencies not found. Trying fallback non-table parsing (less reliable).")
        uk_block_re = r'(?s)Универсальные\s+компетенци(?:и|я).*?:\s*(.*?)(?=\n[ \t]*(?:Общепрофессиональные|Профессиональные)\s+компетенци(?:и|я)|\n[ \t]*IV\.\s*Требования|\Z)'
        opk_block_re = r'(?s)Общепрофессиональные\s+компетенци(?:и|я).*?:\s*(.*?)(?=\n[ \t]*Профессиональные\s+компетенци(?:и|я)|\n[ \t]*IV\.\s*Требования|\Z)'

        uk_block_match = re.search(uk_block_re, section_iii_text, re.IGNORECASE)
        if uk_block_match:
            uk_block_text = uk_block_match.group(1)
            uk_matches = re.finditer(
                r'^(УК-\d+)\s*[).:]?\s*(.+?)(?=(?:\n[ \t]*|^)(?:УК-\d+\s*[).:]?|Общепрофессиональные\s+компетенци|Профессиональные\s+компетенци)|\Z)',
                uk_block_text, re.IGNORECASE | re.MULTILINE | re.DOTALL
            )
            for match in uk_matches:
                code = match.group(1).strip().upper()
                name_raw = match.group(2).strip()
                name_cleaned = re.sub(r'\.$', '', name_raw) 
                name_cleaned = re.sub(r'\s*\n\s*', ' ', name_cleaned) 
                name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip() 
                if name_cleaned: 
                    competencies['uk_competencies'].append({'code': code, 'name': name_cleaned, 'indicators': [], 'category_name': None})
        else: logger.warning("UK competencies block not found (fallback).")

        opk_block_match = re.search(opk_block_re, section_iii_text, re.IGNORECASE)
        if opk_block_match:
            opk_block_text = opk_block_match.group(1)
            opk_matches = re.finditer(
                r'^(ОПК-\d+)\s*[).:]?\s*(.+?)(?=(?:\n[ \t]*|^)(?:ОПК-\d+\s*[).:]?|Профессиональные\s+компетенци|\Z)',
                opk_block_text, re.IGNORECASE | re.MULTILINE | re.DOTALL
            )
            for match in opk_matches:
                code = match.group(1).strip().upper()
                name_raw = match.group(2).strip()
                name_cleaned = re.sub(r'\.$', '', name_raw)
                name_cleaned = re.sub(r'\s*\n\s*', ' ', name_cleaned) 
                name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()
                if name_cleaned:
                    competencies['opk_competencies'].append({'code': code, 'name': name_cleaned, 'indicators': [], 'category_name': None})
        else: logger.warning("OPK competencies block not found (fallback).")

    return competencies

def _extract_recommended_ps_fgos(text: str) -> List[str]:
    """Extracts recommended professional standard codes from FGOS text."""
    ps_codes = []
    ps_section_match = re.search(
        r'(?s)(Перечень(?:\s+и\s+)?(?:рекомендуемых\s+)?профессиональных\s+стандартов'
        r'|Приложение\s*(?:[N№]\s*\d+)?\s*к\s*ФГОС\s*ВО.*?Перечень\s+профессиональных\s+стандартов)', 
        text, re.IGNORECASE
    )
    
    if not ps_section_match:
        logger.warning("Section 'Перечень профессиональных стандартов' or related Appendix not found.")
        return ps_codes

    search_text_for_ps_codes = text[ps_section_match.start():]
    
    end_of_ps_list_match = re.search(
        r'(?s)(\n\s*(?:IV|V|VI|VII|VIII|IX|X)\.\s*Требования|\n\s*Сведения\s+об\s+организациях\s*-\s*разработчиках|\n\s*Информация\s+об\s+изменениях:|\n{3,})', 
        search_text_for_ps_codes, re.IGNORECASE | re.MULTILINE
    )

    if end_of_ps_list_match: ps_list_text = search_text_for_ps_codes[:end_of_ps_list_match.start()]
    else: ps_list_text = search_text_for_ps_codes; logger.warning("Could not find clear end of PS list. Analyzing remaining text.")

    code_matches = re.finditer(r'(?:[N№#]?\s*п/?п?\s*\d+\.\s+)?\b(\d{2}\s*\.\s*\d{3})\b', ps_list_text, re.IGNORECASE | re.MULTILINE)

    for match in code_matches:
        clean_code = match.group(1).replace(' ', '').strip()
        ps_codes.append(clean_code)

    ps_codes = sorted(list(set(ps_codes)))
    if not ps_codes and ps_list_text.strip(): logger.warning("No PS codes extracted from the identified section text despite text existing. Check regex or text content.")
    elif not ps_codes and not ps_list_text.strip(): logger.warning("No PS codes extracted from section, because section text is empty.")

    return ps_codes


def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Main function for parsing FGOS VO PDF files."""
    parsed_data: Dict[str, Any] = {
        'metadata': {}, 'uk_competencies': [], 'opk_competencies': [],
        'recommended_ps_codes': [], 'raw_text': "" 
    }
    try:
        text_content = extract_text(io.BytesIO(file_bytes))
        parsed_data['raw_text'] = text_content
        cleaned_text = _clean_text_fgos(text_content) 

        parsed_data['metadata'] = _extract_fgos_metadata(cleaned_text)

        critical_fields = ['order_number', 'direction_code', 'education_level']
        missing_critical = [field for field in critical_fields if not parsed_data['metadata'].get(field)]
        
        if missing_critical:
             logger.error(f"Missing CRITICAL metadata fields for {filename}. Aborting parsing.")
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}'. Отсутствуют: {', '.join(missing_critical)}.")

        comp_data = _extract_uk_opk(cleaned_text)
        parsed_data['uk_competencies'] = comp_data.get('uk_competencies', [])
        parsed_data['opk_competencies'] = comp_data.get('opk_competencies', [])
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.warning(f"No UK or OPK competencies found for {filename}.")

        parsed_data['recommended_ps_codes'] = _extract_recommended_ps_fgos(cleaned_text) 

        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies'] and not parsed_data['recommended_ps_codes']:
             logger.warning(f"No competencies or recommended PS found for {filename} despite critical metadata being present.")

        return parsed_data

    except FileNotFoundError:
        logger.error(f"File not found: {filename}"); raise
    except ImportError as e:
        logger.error(f"Missing dependency for reading PDF files: {e}. Please install 'pdfminer.six'."); raise ImportError(f"Отсутствует зависимость для чтения PDF файлов: {e}. Пожалуйста, установите 'pdfminer.six'.")
    except ValueError as e:
        logger.error(f"Parser ValueError for {filename}: {e}"); raise ValueError(f"Ошибка парсинга содержимого файла '{filename}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error during PDF parsing for {filename}: {e}", exc_info=True); raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")


def parse_prof_standard_xml(xml_content: bytes) -> Dict[str, Any]:
    """Parses an XML file of a Professional Standard, extracting its full structured data."""
    parsed_data_root: Dict[str, Any] = {
        'code': None, 'name': None, 'order_number': None, 'order_date': None,
        'registration_number': None, 'registration_date': None,   
        'activity_area_name': None, 'activity_purpose': None,
        'generalized_labor_functions': []
    }

    try:
        root = ET.parse(io.BytesIO(xml_content)).getroot()
        
        ps_element = root.find('.//ProfessionalStandart') 
        if ps_element is None: raise ValueError("Тег <ProfessionalStandart> не найден в XML.")

        parsed_data_root['name'] = ps_element.findtext('NameProfessionalStandart')
        parsed_data_root['registration_number'] = ps_element.findtext('RegistrationNumber')
        
        first_section = ps_element.find('FirstSection')
        if first_section is not None:
            parsed_data_root['code'] = first_section.findtext('CodeKindProfessionalActivity')
            parsed_data_root['activity_area_name'] = first_section.findtext('KindProfessionalActivity')
            parsed_data_root['activity_purpose'] = first_section.findtext('PurposeKindProfessionalActivity')
        else: logger.warning("Тег <FirstSection> не найден, код ПС и области деятельности могут отсутствовать.")

        parsed_data_root['order_number'] = ps_element.findtext('OrderNumber')
        parsed_data_root['order_date'] = _parse_date_string(ps_element.findtext('DateOfApproval'))
        
        if not parsed_data_root['code'] or not parsed_data_root['name']:
            raise ValueError("Не удалось извлечь обязательные поля: код или название ПС из метаданных.")

        otf_elements_container = ps_element.find('.//ThirdSection/WorkFunctions/GeneralizedWorkFunctions')
        if otf_elements_container is not None:
            for otf_elem in otf_elements_container.findall('GeneralizedWorkFunction'):
                otf_data = {
                    'code': otf_elem.findtext('CodeOTF'), 'name': otf_elem.findtext('NameOTF'),
                    'qualification_level': otf_elem.findtext('LevelOfQualification'), 'labor_functions': []
                }
                
                tf_elements_container = otf_elem.find('ParticularWorkFunctions')
                if tf_elements_container is not None:
                    for tf_elem in tf_elements_container.findall('ParticularWorkFunction'):
                        tf_data = {
                            'code': tf_elem.findtext('CodeTF'), 'name': tf_elem.findtext('NameTF'),
                            'qualification_level': tf_elem.findtext('SubQualification'), 
                            'labor_actions': [], 'required_skills': [], 'required_knowledge': []
                        }
                        
                        la_container = tf_elem.find('LaborActions')
                        if la_container is not None:
                            for i, la_elem in enumerate(la_container.findall('LaborAction')):
                                la_description = la_elem.text.strip() if la_elem.text else ""
                                if la_description: tf_data['labor_actions'].append({'description': la_description, 'order': i})
                        
                        rs_container = tf_elem.find('RequiredSkills')
                        if rs_container is not None:
                            for i, rs_elem in enumerate(rs_container.findall('RequiredSkill')):
                                rs_description = rs_elem.text.strip() if rs_elem.text else ""
                                if rs_description: tf_data['required_skills'].append({'description': rs_description, 'order': i})
                                
                        rk_container = tf_elem.find('NecessaryKnowledges') 
                        if rk_container is not None:
                            for i, rk_elem in enumerate(rk_container.findall('NecessaryKnowledge')):
                                rk_description = rk_elem.text.strip() if rk_elem.text else ""
                                if rk_description: tf_data['required_knowledge'].append({'description': rk_description, 'order': i})
                                
                        otf_data['labor_functions'].append(tf_data)
                parsed_data_root['generalized_labor_functions'].append(otf_data)
        
        return { "success": True, "parsed_data": parsed_data_root, "error": None }

    except ET.ParseError as e:
        logger.error(f"Ошибка парсинга XML: {e}", exc_info=True)
        return {"success": False, "error": f"Ошибка парсинга XML: {e}", "parsed_data": None}
    except ValueError as e:
        logger.error(f"Ошибка данных при парсинге XML ПС: {e}", exc_info=True)
        return {"success": False, "error": f"Ошибка данных: {e}", "parsed_data": None}
    except Exception as e:
        logger.error(f"Неожиданная ошибка при парсинге XML ПС: {e}", exc_info=True)
        return {"success": False, "error": f"Неожиданная ошибка: {e}", "parsed_data": None}

def parse_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Orchestrates parsing of a Professional Standard file (XML)."""
    logger.info(f"Starting PS parsing orchestration for file: {filename}")
    lower_filename = filename.lower()

    if lower_filename.endswith('.xml'):
        return parse_prof_standard_xml(file_bytes) 
    elif lower_filename.endswith(('.html', '.htm')):
        return {"success": False, "error": "Парсинг HTML профстандартов не поддерживается. Используйте XML.", "filename": filename, "error_type": "deprecated_format"}
    elif lower_filename.endswith('.docx'):
        return {"success": False, "error": "Парсинг DOCX файлов еще не реализован.", "filename": filename, "error_type": "not_implemented"}
    elif lower_filename.endswith('.pdf'):
         return {"success": False, "error": "Парсинг PDF файлов (структура ПС) еще не реализован.", "filename": filename, "error_type": "not_implemented"}
    else:
        return {"success": False, "error": "Неподдерживаемый формат файла для ПС. Поддерживается только XML.", "filename": filename, "error_type": "unsupported_format"}