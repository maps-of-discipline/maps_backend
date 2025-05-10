# competencies_matrix/fgos_parser.py

import io
import re
import datetime
from typing import Dict, List, Any, Optional
from pdfminer.high_level import extract_text # Убедитесь, что установлена библиотека pdfminer.six
import logging
import traceback
import pandas as pd # Для парсинга таблиц в HTML
from bs4 import BeautifulSoup, Comment, NavigableString, Tag # Для парсинга HTML
from markdownify import markdownify # Для конвертации HTML в Markdown
import chardet # Для определения кодировки HTML

logger = logging.getLogger(__name__)

# --- Функции для извлечения данных из PDF ФГОС ---
# Эти функции должны вызываться из parse_fgos_pdf

def _extract_fgos_metadata(text: str) -> Dict[str, Any]:
    """
    Извлекает метаданные (номер/дата приказа, код/название направления, уровень, поколение) из текста ФГОС PDF.
    Использует регулярные выражения.
    """
    metadata = {}
    # TODO: Реализовать извлечение метаданных из текста PDF с помощью регулярных выражений.
    # Пример извлечения: номер и дата приказа, код и название направления, уровень образования, поколение.
    # Убедиться в устойчивости к разным форматам дат и формулировок.
    # Примеры REGEX:
    # order_match = re.search(r'от\s+(\d{2}\.\d{2}\.\d{4})\s+№\s*(\d+)', text)
    # direction_match = re.search(r'по\s+направлению\s+подготовки\s+(\d{2}\.\d{2}\.\d{2})\s+(.*?)уровень', text)
    # level_match = re.search(r'уровень\s+(бакалавриата|магистратуры|специалитета)', text)
    # generation_match = re.search(r'ФГОС\s+ВО\s+(3\+\+|3\+)', text[:1000]) # Искать в начале

    logger.debug("_extract_fgos_metadata: Metadata extraction logic TBD.")
    # Заглушка с тестовыми данными для 09.03.01
    metadata = {
        'order_number': '929',
        'order_date': datetime.date(2017, 9, 19),
        'direction_code': '09.03.01',
        'direction_name': 'Информатика и вычислительная техника',
        'education_level': 'бакалавриат',
        'generation': '3++',
        'order_date_raw': '19.09.2017' # Исходная строка даты, если нужно
    }

    return metadata

def _extract_uk_opk(text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Извлекает УК и ОПК компетенции (код, название) из текста раздела III ФГОС.
    НЕ ПАРСИТ ИНДИКАТОРЫ.
    """
    competencies = {'uk_competencies': [], 'opk_competencies': []}
    # TODO: Реализовать поиск раздела III.
    # TODO: Внутри раздела III найти блоки УК и ОПК.
    # TODO: Для каждой компетенции (УК-N, ОПК-N) извлечь код и формулировку.
    # Индикаторы из PDF не парсятся.

    logger.debug("_extract_uk_opk: UK/OPK extraction logic TBD.")
    # Заглушка с тестовыми данными
    competencies['uk_competencies'] = [
        {'code': 'УК-1', 'name': 'Способен осуществлять поиск, критический анализ и синтез информации...', 'indicators': []}, # Индикаторы будут добавлены позже (из другого источника)
        {'code': 'УК-5', 'name': 'Способен воспринимать межкультурное разнообразие общества...', 'indicators': []},
    ]
     # Заглушка с тестовыми данными
    competencies['opk_competencies'] = [
        {'code': 'ОПК-7', 'name': 'Способен участвовать в настройке и наладке программно-аппаратных комплексов...', 'indicators': []},
    ]

    return competencies

def _extract_recommended_ps(text: str) -> List[str]:
    """
    Извлекает список кодов рекомендованных профессиональных стандартов из текста ФГОС.
    Ищет раздел "Перечень профессиональных стандартов..."
    """
    ps_codes = []
    # TODO: Реализовать поиск раздела с перечнем ПС (обычно приложение или в конце документа).
    # TODO: В этом разделе найти коды ПС в формате ЧЧ.ЧЧЧ (например, 06.001).

    logger.debug("_extract_recommended_ps: Recommended PS extraction logic TBD.")
    # Заглушка с тестовыми данными для 09.03.01
    ps_codes = ['06.001', '06.004', '06.011', '06.015', '06.016']

    return ps_codes

def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Главная функция парсинга PDF файла ФГОС ВО.
    Извлекает метаданные, УК/ОПК (без индикаторов), рекомендованные ПС.
    """
    logger.info(f"Starting PDF parsing for file: {filename}")
    text = ""
    parsed_data: Dict[str, Any] = {
        'metadata': {},
        'uk_competencies': [],
        'opk_competencies': [],
        'recommended_ps_codes': [],
        'raw_text': "" # Можно сохранить сырой текст для отладки
    }

    try:
        # --- 1. Извлечение текста ---
        # Убедитесь, что библиотека pdfminer.six установлена
        text = extract_text(io.BytesIO(file_bytes))
        parsed_data['raw_text'] = text
        logger.debug(f"Extracted text from PDF ({len(text)} characters).")

        # TODO: Добавить базовую предобработку текста (удаление переносов, лишних пробелов)

        # --- 2. Извлечение метаданных ---
        parsed_data['metadata'] = _extract_fgos_metadata(text)
        if not parsed_data['metadata']:
             logger.error("Failed to extract core FGOS metadata.")
             # Решаем, что делать при ошибке метаданных - выбросить исключение или вернуть частичные данные
             # Для MVP, наверное, лучше выбросить, т.к. без метаданных запись ФГОС неполноценна
             raise ValueError("Не удалось извлечь основные метаданные ФГОС (номер, код направления, дата, уровень).")


        # --- 3. Извлечение компетенций (УК, ОПК) ---
        comp_data = _extract_uk_opk(text)
        parsed_data['uk_competencies'] = comp_data.get('uk_competencies', [])
        parsed_data['opk_competencies'] = comp_data.get('opk_competencies', [])
        # Если ни УК, ни ОПК не найдены, возможно, файл не соответствует формату ФГОС
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.warning("No UK or OPK competencies found in the document.")
             # Решаем, что делать - выбросить ошибку или продолжить с предупреждением
             # Для MVP, если метаданные есть, можно продолжить, но пометить как "проблемный" файл
             # raise ValueError("Не удалось извлечь ни УК, ни ОПК компетенции из раздела III.")


        # --- 4. Извлечение рекомендованных ПС ---
        parsed_data['recommended_ps_codes'] = _extract_recommended_ps(text)
        # Отсутствие рекомендованных ПС - не ошибка, просто их нет в стандарте

        logger.info(f"PDF parsing for {filename} finished. Found UK:{len(parsed_data['uk_competencies'])}, OPK:{len(parsed_data['opk_competencies'])}, PS:{len(parsed_data['recommended_ps_codes'])}")

        return parsed_data

    except FileNotFoundError:
        logger.error(f"PDF file not found: {filename}")
        raise # Перебрасываем исключение
    except Exception as e:
        logger.error(f"Unexpected error during PDF parsing for {filename}: {e}", exc_info=True)
        raise # Перебрасываем исключение

# --- Функции для извлечения данных из HTML/Markdown ПС ---
# Эти функции должны вызываться из parse_uploaded_prof_standard
# (profstandard-lean.py уже содержит базовый html_to_markdown_parser_enhanced)

def _extract_ps_metadata(markdown_text: str) -> Dict[str, Any]:
    """
    Извлекает метаданные ПС (код, название, номер/дата приказа и т.д.) из Markdown текста.
    """
    metadata = {}
    # TODO: Реализовать парсинг метаданных из Markdown текста.
    # Используйте регулярные выражения для поиска "ПРОФЕССИОНАЛЬНЫЙ СТАНДАРТ "...", Код ЧЧ.ЧЧЧ",
    # "Утвержден приказом...", "Зарегистрирован Минюстом..." и т.д.
    # Конвертация дат из русского формата (день месяц_прописью год) в date object.

    logger.debug("_extract_ps_metadata: Metadata extraction logic TBD.")
     # Заглушка
    metadata = {
        'code': '06.001',
        'name': 'Программист',
        'order_number': '424н',
        'order_date': datetime.date(2022, 7, 20),
        'registration_number': None, # Может отсутствовать
        'registration_date': None # Может отсутствовать
    }

    return metadata

def _extract_ps_structure_detailed(markdown_text: str) -> Dict[str, Any]:
    """
    Извлекает детальную структуру ПС (ОТФ, ТФ, ТД, НУ, НЗ) из Markdown текста.
    Это сложная задача, требующая анализа заголовков разделов, списков, таблиц.
    Для MVP достаточно структуры ОТФ -> ТФ.
    """
    structure = {'generalized_labor_functions': []}
    # TODO: Реализовать парсинг структуры из Markdown текста.
    # Искать заголовки разделов "II. Описание трудовых функций...", "III. Характеристика обобщенных трудовых функций".
    # Искать блоки ОТФ (Например: "3.1. Обобщенная трудовая функция" -> Наименование, Код, Уровень).
    # Внутри ОТФ искать блоки ТФ (Например: "3.1.1. Трудовая функция" -> Наименование, Код, Уровень (подуровень)).
    # Внутри ТФ искать списки: Трудовые действия, Необходимые умения, Необходимые знания.

    logger.debug("_extract_ps_structure_detailed: Detailed structure extraction logic TBD.")
    # Заглушка
    structure['generalized_labor_functions'] = [
        {'code': 'A', 'name': 'Разработка и отладка программного кода', 'qualification_level': '3', 'labor_functions': [
            {'code': 'A/01.3', 'name': 'Формализация и алгоритмизация...', 'qualification_level': '3', 'labor_actions': [{'description': 'Составление формализованных описаний...'}], 'required_skills': [], 'required_knowledge': []},
            {'code': 'A/02.3', 'name': 'Написание программного кода...', 'qualification_level': '3', 'labor_actions': [{'description': 'Создание программного кода...'}], 'required_skills': [], 'required_knowledge': []},
        ]},
         {'code': 'C', 'name': 'Интеграция программных модулей...', 'qualification_level': '5', 'labor_functions': [
            {'code': 'C/01.5', 'name': 'Разработка процедур интеграции...', 'qualification_level': '5', 'labor_actions': [], 'required_skills': [], 'required_knowledge': []},
        ]},
         {'code': 'D', 'name': 'Разработка требований и проектирование...', 'qualification_level': '6', 'labor_functions': [
            {'code': 'D/01.6', 'name': 'Анализ возможностей реализации...', 'qualification_level': '6', 'labor_actions': [], 'required_skills': [], 'required_knowledge': []},
        ]},
    ]

    return structure

def parse_prof_standard(file_bytes: bytes, filename: str, file_format: str) -> Dict[str, Any]:
    """
    Главная функция парсинга файла Профессионального Стандарта.
    Определяет формат и вызывает соответствующий парсер, извлекает метаданные и структуру.
    """
    logger.info(f"Starting PS parsing for file: {filename}, format: {file_format}")
    markdown_text = ""
    extracted_metadata = {}
    extracted_structure = {}

    try:
        if file_format == 'html':
            # Используйте логику из profstandard-lean.py
            encoding = chardet.detect(file_bytes)['encoding'] or 'utf-8' # Улучшенное определение кодировки
            html_content = file_bytes.decode(encoding, errors='ignore')
            # Используйте парсер из profstandard-lean.py, который возвращает Markdown
            # (предполагается, что он адаптирован или вызван из parse_uploaded_prof_standard)
            # For MVP, let's assume parse_uploaded_prof_standard handles HTML and returns Markdown
            # markdown_text = html_to_markdown_parser_enhanced(html_content) # <-- Это логика из profstandard-lean.py
            
            # Для текущей реализации, просто вызовем парсер из parse_uploaded_prof_standard
            parse_result = parse_uploaded_prof_standard(file_bytes, filename)
            if not parse_result['success']:
                 raise ValueError(f"HTML parsing failed: {parse_result.get('error', 'Unknown error')}")
            
            markdown_text = parse_result['parsed_data']['parsed_content']
            extracted_metadata = parse_result['parsed_data'] # parse_uploaded_prof_standard уже извлекает метаданные
            extracted_structure = _extract_ps_structure_detailed(markdown_text) # Извлекаем структуру из Markdown

        elif file_format == 'docx':
            # TODO: Реализовать парсинг DOCX
            logger.warning(f"DOCX parsing is not yet implemented for {filename}. Skipping.")
            raise NotImplementedError("Парсинг DOCX файлов еще не реализован.")
        elif file_format == 'pdf':
             # TODO: Реализовать парсинг PDF
             logger.warning(f"PDF parsing is not yet implemented for {filename}. Skipping.")
             raise NotImplementedError("Парсинг PDF файлов еще не реализован.")
        else:
            logger.error(f"Unsupported file format for {filename}: {file_format}")
            raise ValueError(f"Неподдерживаемый формат файла: {file_format}")

        # Проверка наличия минимальных данных
        if not extracted_metadata.get('code') or not extracted_metadata.get('name'):
             logger.error("Could not extract PS code and name.")
             raise ValueError("Не удалось извлечь код и название профессионального стандарта.")

        parsed_data: Dict[str, Any] = {
            'metadata': extracted_metadata,
            'structure': extracted_structure, # Включает ОТФ, ТФ, ТД, НУ, НЗ
            'parsed_content_markdown': markdown_text # Весь текст в Markdown
        }

        logger.info(f"PS parsing for {filename} finished. Code: {parsed_data['metadata']['code']}, Name: {parsed_data['metadata']['name']}")
        return parsed_data

    except FileNotFoundError:
        logger.error(f"PS file not found: {filename}")
        raise
    except NotImplementedError:
        raise # Пробрасываем, если формат не реализован
    except ValueError as e:
        logger.error(f"PS Parsing ValueError for {filename}: {e}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during PS parsing for {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла ПС '{filename}': {e}")

# --- Блок if __name__ == '__main__': для автономного тестирования ---
# Этот блок позволяет запустить парсер из командной строки для тестирования.
# Он не является частью логики приложения, а только для разработки.

if __name__ == '__main__':
    import sys
    import os
    
    # Настроим логирование для автономного запуска
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    if len(sys.argv) < 2:
        print("Usage: python fgos_parser.py <filepath> [<format>]")
        print("Example: python fgos_parser.py path/to/fgos.pdf pdf")
        print("Example: python fgos_parser.py path/to/ps.html html")
        sys.exit(1)

    test_file_path = sys.argv[1]
    file_format = sys.argv[2].lower() if len(sys.argv) > 2 else os.path.splitext(test_file_path)[1][1:].lower()

    if not os.path.exists(test_file_path):
        print(f"Error: File not found at '{test_file_path}'")
        sys.exit(1)

    with open(test_file_path, 'rb') as f:
        file_content = f.read()

    try:
        if file_format == 'pdf':
            # Парсинг ФГОС PDF
            parsed_data = parse_fgos_pdf(file_content, os.path.basename(test_file_path))
            print("\n--- Результат парсинга ФГОС ---")
            print("Метаданные:", parsed_data.get('metadata'))
            print("\nУК Компетенции:", len(parsed_data.get('uk_competencies', [])))
            for comp in parsed_data.get('uk_competencies', []):
                 print(f"  - {comp['code']}: {comp['name'][:80]}...")
            print("\nОПК Компетенции:", len(parsed_data.get('opk_competencies', [])))
            for comp in parsed_data.get('opk_competencies', []):
                 print(f"  - {comp['code']}: {comp['name'][:80]}...")
            print("\nРекомендованные ПС:", parsed_data.get('recommended_ps_codes'))
            print("\nСырой текст (превью):", parsed_data.get('raw_text', '')[:1000], "...")

        else:
            # Парсинг ПС (HTML, DOCX, PDF)
            parsed_data = parse_prof_standard(file_content, os.path.basename(test_file_path), file_format)
            print("\n--- Результат парсинга Профстандарта ---")
            if parsed_data.get('success'):
                 print("Статус: Успех")
                 parsed_content = parsed_data.get('parsed_data', {})
                 metadata = parsed_content.get('metadata', {})
                 structure = parsed_content.get('structure', {})
                 print("Метаданные:", metadata)
                 print("\nСтруктура:")
                 for otf in structure.get('generalized_labor_functions', []):
                     print(f"  ОТФ {otf.get('code')}: {otf.get('name', '')[:50]}... ({otf.get('qualification_level')})")
                     for tf in otf.get('labor_functions', []):
                          print(f"    ТФ {tf.get('code')}: {tf.get('name', '')[:50]}... ({tf.get('qualification_level')})")
                          print(f"      ТД: {len(tf.get('labor_actions', []))}, Умения: {len(tf.get('required_skills', []))}, Знания: {len(tf.get('required_knowledge', []))}")
                 print("\nMarkdown содержимое (превью):", parsed_content.get('parsed_content_markdown', '')[:1000], "...")
            else:
                 print("Статус: Ошибка")
                 print("Ошибка:", parsed_data.get('error'))
                 print("Тип ошибки:", parsed_data.get('error_type'))


    except FileNotFoundError:
        print(f"Error: File not found at '{test_file_path}'")
    except NotImplementedError as e:
         print(f"Error: {e}")
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()