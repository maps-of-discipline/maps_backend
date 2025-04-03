# competencies_matrix/parsers.py
"""
Модуль для парсинга профессиональных стандартов.
Содержит функции для извлечения структурированных данных из HTML/Markdown файлов профстандартов.
"""
import re
import os
import chardet
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import tempfile
from typing import Dict, List, Optional, Union, Any, Tuple


def detect_encoding(file_path: str) -> str:
    """
    Определяет кодировку файла.
    
    Args:
        file_path (str): Путь к файлу
        
    Returns:
        str: Определённая кодировка (например, 'utf-8', 'windows-1251')
    """
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result['encoding']


def html_to_markdown_parser_enhanced(
    input_filepath: str,
    output_filepath: Optional[str] = None,
    default_encoding: str = 'utf-8'
) -> Optional[str]:
    """
    Преобразует HTML файл профстандарта в Markdown с улучшенным форматированием.
    
    Args:
        input_filepath (str): Путь к входному HTML файлу
        output_filepath (Optional[str]): Путь для сохранения результата (если None, не сохраняется)
        default_encoding (str): Кодировка по умолчанию, если не удается определить
        
    Returns:
        Optional[str]: Текст в формате Markdown или None в случае ошибки
    """
    try:
        # Определяем кодировку, если не указана явно
        encoding = detect_encoding(input_filepath) or default_encoding
        
        # Читаем HTML файл
        with open(input_filepath, 'r', encoding=encoding, errors='replace') as f:
            html_content = f.read()
        
        # Парсим HTML с помощью BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Предобработка: удаляем ненужные элементы
        for tag in soup.find_all(['script', 'style']):
            tag.decompose()
        
        # Преобразуем в Markdown
        markdown_text = md(str(soup), heading_style="ATX")
        
        # Постобработка: удаляем лишние переносы, улучшаем форматирование
        markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
        
        # Сохраняем результат, если указан выходной файл
        if output_filepath:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_text)
        
        return markdown_text
    
    except Exception as e:
        print(f"Ошибка при парсинге HTML: {str(e)}")
        return None


def extract_ps_structure(markdown_text: str) -> Dict[str, Any]:
    """
    Извлекает структурированные данные из Markdown текста профстандарта.
    
    Args:
        markdown_text (str): Текст профстандарта в формате Markdown
        
    Returns:
        Dict[str, Any]: Словарь с структурированными данными профстандарта
    """
    # Извлекаем метаданные (код, название)
    ps_data = {}
    
    # Поиск кода ПС - обычно это число XX.XXX
    code_match = re.search(r'###\s+(\d{2}\.\d{3})', markdown_text)
    ps_data['code'] = code_match.group(1) if code_match else "UNKNOWN"
    
    # Поиск названия ПС - обычно после "ПРОФЕССИОНАЛЬНЫЙ СТАНДАРТ"
    name_match = re.search(r'ПРОФЕССИОНАЛЬНЫЙ СТАНДАРТ\s*\n*(.*?)\n', markdown_text, re.IGNORECASE)
    ps_data['name'] = name_match.group(1).strip() if name_match else "Название не найдено"
    
    # Извлечение ОТФ/ТФ/действий/знаний/умений - базовая реализация
    # Здесь должен быть более сложный алгоритм для полного разбора структуры ПС
    
    otf_list = []
    # Простой паттерн для поиска ОТФ (нужно будет уточнить)
    otf_pattern = r'## [А-Я]\. (.*?)\n'
    otf_matches = re.finditer(otf_pattern, markdown_text)
    
    for match in otf_matches:
        otf_name = match.group(1).strip()
        otf_data = {
            'code': match.group(0)[3].strip(),  # Обычно это буква (A, B, C, ...)
            'name': otf_name,
            'labor_functions': []  # Здесь будут ТФ
        }
        otf_list.append(otf_data)
    
    ps_data['generalized_labor_functions'] = otf_list
    
    return ps_data


def parse_prof_standard_file(html_content: bytes) -> Dict[str, Any]:
    """
    Комплексная функция для парсинга и обработки HTML файла профстандарта.
    
    Args:
        html_content (bytes): Содержимое HTML файла в байтах
        
    Returns:
        Dict[str, Any]: Результат парсинга с ключами:
            - success (bool): Успешен ли парсинг
            - prof_standard_id (Optional[int]): ID профстандарта в БД (если сохранен)
            - code (str): Код профстандарта
            - name (str): Название профстандарта
            - markdown (str): Текст в формате Markdown
            - structure (Dict): Структурированные данные ПС
            - error (Optional[str]): Текст ошибки (если была)
    """
    # Создаем временный файл для работы с HTML
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as temp_file:
        temp_file.write(html_content)
        temp_filepath = temp_file.name
    
    try:
        # 1. Определяем кодировку
        encoding = detect_encoding(temp_filepath) or 'windows-1251'
        
        # 2. Парсим в Markdown
        markdown_text = html_to_markdown_parser_enhanced(
            temp_filepath,
            output_filepath=None,
            default_encoding=encoding
        )
        
        if not markdown_text:
            return {"success": False, "error": "Парсер не вернул текст"}
        
        # 3. Извлекаем структурированные данные
        ps_structure = extract_ps_structure(markdown_text)
        
        # 4. Формируем результат
        return {
            "success": True,
            "code": ps_structure['code'],
            "name": ps_structure['name'],
            "markdown": markdown_text,
            "structure": ps_structure
        }
        
    except Exception as e:
        return {"success": False, "error": f"Ошибка при парсинге или обработке: {str(e)}"}
    
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)