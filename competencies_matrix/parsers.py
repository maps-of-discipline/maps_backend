# filepath: competencies_matrix/parsers.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional, Tuple
# from pdfminer.high_level import extract_text # Удаляем, т.к. ФГОС парсится через nlp.py
import xml.etree.ElementTree as ET
import logging
from bs4 import BeautifulSoup # Оставляем, если планируется парсинг HTML ПС в будущем
from markdownify import markdownify # Оставляем, если планируется конвертация HTML в Markdown

from .parsing_utils import parse_date_string


logger = logging.getLogger(__name__)

# --- Удален весь код _clean_text_fgos ---
# --- Удален весь код _extract_fgos_metadata ---
# --- Удален весь код _add_buffered_comp_to_list ---
# --- Удален весь код _extract_uk_opk ---
# --- Удален весь код _extract_recommended_ps_fgos ---
# --- Удален весь код parse_fgos_pdf ---

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