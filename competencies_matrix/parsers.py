# competencies_matrix/parsers.py
"""
Module for parsing Professional Standards into structured data.
"""
import re
import pandas as pd
import io
from bs4 import BeautifulSoup, Comment, NavigableString, Tag # Добавляем импорты Tag, NavigableString
from markdownify import markdownify # Добавляем импорт markdownify
import chardet
import tempfile
import os
import logging # Добавляем логирование
from typing import Dict, List, Any, Optional, Tuple # Добавляем типизацию


# Настройка логирования
logger = logging.getLogger(__name__)


# --- Вспомогательные функции для парсинга ---

def detect_encoding(file_bytes: bytes) -> str:
    """
    Detect the encoding of a file.
    """
    # Try common encodings
    encodings = ['utf-8', 'cp1251', 'iso-8859-1', 'utf-16'] # Добавим common Russian encodings

    for enc in encodings:
        try:
            file_bytes.decode(enc)
            logger.debug(f"Detected encoding: {enc}")
            return enc
        except UnicodeDecodeError:
            continue

    # Fallback
    logger.warning("Could not confidently detect encoding. Falling back to 'latin-1'.")
    return 'latin-1'


def html_to_markdown_parser_enhanced(html_content: str) -> str:
    """
    Convert HTML content to enhanced Markdown with proper structure for PS.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception as e:
        logger.error(f"Error parsing HTML with BeautifulSoup: {e}")
        # В случае ошибки парсинга HTML, возвращаем просто текст или пустую строку
        try:
             return BeautifulSoup(html_content, 'html.parser').get_text() # Пробуем более простой парсер
        except Exception:
             return ""


    # Удаление глобального мусора (шапки, подвалы, реклама, скрипты, стили)
    elements_to_remove_globally = [
        'header', 'footer', 'script', 'style', 'noscript', 'form', 'nav', 'aside', '.ad-block', '[class*="footer"]', '[id*="header"]', '[id*="menu"]', '[id*="ad"]'
    ]
    for selector in elements_to_remove_globally:
        for element in soup.select(selector):
            element.decompose()

    # Удаление HTML-комментариев
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Поиск основного контейнера контента (часто div с id 'cont_txt', 'main', 'content', или просто div с классом 'article')
    # Это эвристика, может потребоваться настройка для разных источников
    content_containers = soup.select('div#cont_txt, div#main, div#content, article, div.article, div.content, div.post')
    if not content_containers:
         content_containers = soup.select('body') # Запасной вариант - весь body

    main_content_area = None
    if content_containers:
        # Выбираем самый большой контейнер как основной (эвристика)
        main_content_area = max(content_containers, key=lambda tag: len(tag.get_text(strip=True)))
        logger.debug(f"Selected main content area: {main_content_area.name} (id: {main_content_area.get('id')}, class: {main_content_area.get('class')}) with text length {len(main_content_area.get_text(strip=True))}")
    else:
         logger.warning("Could not identify main content area. Processing entire soup body.")
         main_content_area = soup.body # Если не нашли, берем весь body

    # Удаление пустых тегов (p, div) после чистки
    for tag in main_content_area.find_all(['p', 'div']):
         if not tag.get_text(strip=True) and not tag.find(['img', 'br', 'table', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
             tag.decompose()


    markdown_parts = []

    # Обработка элементов внутри основного контейнера
    for element in main_content_area.contents: # Используем .contents, чтобы получить текст и прямых потомков
         if isinstance(element, NavigableString):
             text = str(element).strip() # Преобразуем в строку для strip
             if text:
                 markdown_parts.append(text)
         elif isinstance(element, Tag):
             if element.name == 'table':
                 # Обработка таблицы через Pandas
                 try:
                     # Используем lxml напрямую для лучшей обработки HTML таблиц
                     # header=0 означает, что первая строка - заголовок
                     dfs = pd.read_html(str(element), flavor='lxml', header=0, encoding=encoding, keep_default_na=False)
                     if dfs:
                         for df in dfs:
                             # Убираем пустые строки/столбцы, которые мог создать Pandas из-за rowspan/colspan
                             df.dropna(axis=0, how='all', inplace=True)
                             df.dropna(axis=1, how='all', inplace=True)
                             if not df.empty: # Только если DataFrame не пустой после дропа
                                 # Конвертируем DataFrame в Markdown
                                 md_table = df.to_markdown(index=False, tablefmt='pipe')
                                 markdown_parts.append("\n" + md_table + "\n") # Добавляем переносы для таблиц
                             # else: logger.debug("Skipping empty DataFrame after dropna.")
                         # else: logger.debug("Pandas did not extract any DataFrame from the table.")
                     # else: logger.debug("pd.read_html returned empty list.") # Вряд ли произойдет
                 except Exception as e:
                     logger.warning(f"Error processing table with Pandas ({element.get('id', element.get('class', element.name))}). Skipping table. Error: {e}")
                     # Можно добавить markdownify как fallback, но он скорее всего тоже не справится
             elif element.name == 'br':
                  # Игнорируем <br> - Markdownify должен их обрабатывать
                  pass
             else:
                # Обработка остальных тегов через Markdownify
                # Чистим атрибуты перед передачей в markdownify
                clean_html_tag(element) # Чистка атрибутов in-place
                # Преобразуем элемент и его содержимое в Markdown
                md_part = markdownify(str(element), heading_style="ATX", bullets='-').strip()
                if md_part:
                    markdown_parts.append(md_part)

    # Собираем итоговый Markdown
    final_markdown = "\n\n".join(filter(None, markdown_parts))
    # Удаляем множественные пустые строки, оставляя максимум одну между блоками
    final_markdown = re.sub(r'(\n\s*)+\n', '\n\n', final_markdown).strip()


    return final_markdown


def extract_ps_metadata_simple(markdown_text: str) -> Dict[str, Any]:
    """
    Простое извлечение метаданных (код, название, номер приказа, дата) из начала Markdown текста ПС.
    """
    metadata = {}
    # Ищем код и название в первых строках
    code_match = re.search(r'Профессиональный\s+стандарт(?:\s+"(.*?)"|:\s*(.*?))\s+Код\s+(\d+\.\d+)', markdown_text, re.IGNORECASE | re.DOTALL)
    if code_match:
        metadata['name'] = code_match.group(1) or code_match.group(2) # Название
        metadata['code'] = code_match.group(3) # Код
    else:
        # Запасной вариант поиска кода
        code_match_fallback = re.search(r'Код\s+(\d+\.\d+)', markdown_text, re.IGNORECASE)
        if code_match_fallback:
            metadata['code'] = code_match_fallback.group(1)
        # Запасной вариант поиска названия (первый H1 или H2?)
        name_match_fallback = re.search(r'^#+\s*(.*?)\n', markdown_text, re.MULTILINE)
        if name_match_fallback:
             metadata['name'] = metadata.get('name') or name_match_fallback.group(1).strip()


    # Ищем номер и дату приказа утверждения
    order_match = re.search(
        r'утвержден\s+приказом\s+Министерства\s+труда\s+и\s+социальной\s+защиты\s+Российской\s+Федерации\s+от\s+'
        r'(\d{1,2})\s+(\S+)\s+(\d{4})\s+г\.\s+[№N]\s*(\d+)',
        markdown_text, re.IGNORECASE
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
            except ValueError:
                logger.warning(f"Invalid date components for PS order date: {year}-{month}-{day}")
        else:
            logger.warning(f"Could not parse month name '{month_name}' for PS order date.")

    # Ищем номер и дату регистрации в Минюсте
    registration_match = re.search(
        r'зарегистрирован\s+Министерством\s+юстиции\s+Российской\s+Федерации\s+(\d{1,2})\s+(\S+)\s+(\d{4})\s+г\.\s+регистрационный\s+[№N]\s*(\d+)',
        markdown_text, re.IGNORECASE
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
            except ValueError:
                logger.warning(f"Invalid date components for PS registration date: {year}-{month}-{day}")
        else:
            logger.warning(f"Could not parse month name '{month_name}' for PS registration date.")


    return metadata


# --- Основная функция парсинга для загруженных файлов ---

def parse_uploaded_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Парсит загруженный файл Профессионального Стандарта (HTML/DOCX/PDF).
    Возвращает структурированные данные (пока только метаданные и markdown).

    Args:
        file_bytes: Содержимое файла в байтах.
        filename: Имя файла.

    Returns:
        Dict[str, Any]: Словарь с результатами парсинга {'success': bool, 'error': str, 'parsed_data': {...}}.
                        'parsed_data' содержит 'code', 'name', 'parsed_content' (markdown) и др.
    """
    logger.info(f"parse_uploaded_prof_standard: Starting parsing for file: {filename}")
    markdown_text = ""
    extracted_metadata = {}

    try:
        # Определяем тип файла по расширению
        lower_filename = filename.lower()
        if lower_filename.endswith(('.html', '.htm')):
            encoding = detect_encoding(file_bytes)
            html_content = file_bytes.decode(encoding, errors='ignore')
            markdown_text = html_to_markdown_parser_enhanced(html_content)
            extracted_metadata = extract_ps_metadata_simple(markdown_text) # Извлекаем метаданные из Markdown
        elif lower_filename.endswith('.docx'):
            # TODO: Реализовать парсинг DOCX
            logger.warning(f"DOCX parsing is not yet implemented for {filename}. Skipping.")
            return {"success": False, "error": "Парсинг DOCX файлов еще не реализован.", "filename": filename, "error_type": "not_implemented"}
        elif lower_filename.endswith('.pdf'):
             # TODO: Реализовать парсинг PDF
             logger.warning(f"PDF parsing is not yet implemented for {filename}. Skipping.")
             return {"success": False, "error": "Парсинг PDF файлов еще не реализован.", "filename": filename, "error_type": "not_implemented"}
        else:
            # Неизвестный формат
            logger.warning(f"Unsupported file format for {filename}. Supported: HTML (.html, .htm).")
            return {"success": False, "error": "Неподдерживаемый формат файла. Поддерживаются только HTML.", "filename": filename, "error_type": "unsupported_format"}

        # Проверяем, извлекли ли код и название из метаданных
        ps_code = extracted_metadata.get('code')
        ps_name = extracted_metadata.get('name')

        if not ps_code or not ps_name:
            # Если метаданные не извлечены из текста, можно попытаться из имени файла
            code_match_filename = re.search(r'ps[_-]?(\d+\.\d+)', lower_filename)
            if code_match_filename:
                 ps_code = code_match_filename.group(1)
                 # Если названия нет, используем плейсхолдер
                 ps_name = ps_name or f"Профессиональный стандарт {ps_code}"
                 logger.warning(f"Extracted PS code '{ps_code}' from filename.")
            else:
                # Если даже из имени файла не получилось, это критическая ошибка
                logger.error(f"Could not extract PS code and name from file '{filename}' or content.")
                return {"success": False, "error": "Не удалось извлечь код и название профессионального стандарта.", "filename": filename, "error_type": "parsing_error"}

        # Формируем результат парсинга (только базовые данные и markdown)
        parsed_data: Dict[str, Any] = {
            'code': ps_code,
            'name': ps_name,
            'parsed_content': markdown_text, # Сохраняем весь Markdown
            # Добавляем другие извлеченные метаданные
            'order_number': extracted_metadata.get('order_number'),
            'order_date': extracted_metadata.get('order_date'), # Date object or None
            'registration_number': extracted_metadata.get('registration_number'),
            'registration_date': extracted_metadata.get('registration_date'), # Date object or None
        }
        logger.info(f"parse_uploaded_prof_standard: Successfully parsed basic data for '{filename}' (Code: {ps_code}).")
        return {"success": True, "parsed_data": parsed_data, "filename": filename}

    except Exception as e:
        logger.error(f"parse_uploaded_prof_standard: Unexpected error parsing {filename}: {e}", exc_info=True)
        return {"success": False, "error": f"Неожиданная ошибка при парсинге файла: {e}", "filename": filename, "error_type": "unexpected_error"}


# TODO: Реализовать extract_ps_structure_detailed (будет парсить Markdown в структуру ОТФ, ТФ, ТД, НУ, НЗ)
def extract_ps_structure_detailed(markdown_text: str) -> Dict[str, Any]:
    """
    Извлекает детальную структуру ПС (ОТФ, ТФ, ТД, НУ, НЗ) из Markdown текста.
    Это сложная задача, требующая анализа структуры разделов, списков и таблиц.
    Заглушка для будущей реализации.
    """
    logger.warning("extract_ps_structure_detailed: Detailed PS structure extraction is not yet implemented.")
    # Возвращаем пустую структуру для ОТФ/ТФ и т.д.
    return {
        'generalized_labor_functions': []
        # Здесь будут списки словарей для каждой сущности
        # 'labor_functions': [...],
        # 'labor_actions': [...],
        # 'required_skills': [...],
        # 'required_knowledge': [...]
    }