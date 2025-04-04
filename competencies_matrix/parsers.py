# competencies_matrix/parsers.py
"""
Module for parsing Professional Standards into structured data.
"""
import re
import pandas as pd
import io
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional, Tuple
import tempfile
import os

def detect_encoding(file_bytes: bytes) -> str:
    """
    Detect the encoding of a file.
    
    Args:
        file_bytes: Bytes of the file to detect encoding for
        
    Returns:
        str: Detected encoding
    """
    # Try common encodings
    encodings = ['utf-8', 'cp1251', 'iso-8859-1', 'utf-16']
    
    for enc in encodings:
        try:
            file_bytes.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    
    # Default to utf-8 if detection fails
    return 'utf-8'

def html_to_markdown_parser_enhanced(html_content: str) -> str:
    """
    Convert HTML content to enhanced Markdown with proper structure for PS.
    
    Args:
        html_content: HTML content of professional standard
        
    Returns:
        str: Markdown formatted content
    """
    # Basic implementation - would need to be expanded for real use
    # This would use libraries like markdownify or custom conversion logic
    from bs4 import BeautifulSoup
    
    # Implement a real conversion from HTML to Markdown for PS
    # For now, just a simplified version for demonstration
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text()
    
    # Basic formatting: headers
    text = re.sub(r'(Обобщенная трудовая функция|ОТФУНКЦИЯ)\s+([А-Я])[.\s]+(.*)', r'## \2. \3', text)
    text = re.sub(r'(Трудовая функция|ФУНКЦИЯ)\s+([А-Я])/(\d+\.\d+)[.\s]+(.*)', r'### \2/\3. \4', text)
    
    # Basic formatting: sections
    text = re.sub(r'Трудовые действия', r'#### Трудовые действия', text)
    text = re.sub(r'Необходимые умения', r'#### Необходимые умения', text)
    text = re.sub(r'Необходимые знания', r'#### Необходимые знания', text)
    
    return text

def extract_ps_structure(markdown_text: str) -> Dict[str, Any]:
    """
    Extract structured data from a Markdown formatted PS.
    
    Args:
        markdown_text: Markdown text of the professional standard
        
    Returns:
        dict: Structured data of the PS
    """
    # Initialize result structure
    ps_data = {
        'code': '',  # Will be filled later or from filename
        'name': '',  # Will be filled later or from metadata
        'generalized_labor_functions': []
    }
    
    otf_list = []
    # Паттерн для поиска ОТФ
    otf_pattern = r'## ([А-Я])\. (.*?)\n'
    otf_matches = re.finditer(otf_pattern, markdown_text)
    
    for match in otf_matches:
        otf_code = match.group(1).strip()
        otf_name = match.group(2).strip()
        otf_data = {
            'code': otf_code,
            'name': otf_name,
            'labor_functions': []  # Здесь будут ТФ
        }
        otf_list.append(otf_data)
        
        # Найдем ТФ внутри этой ОТФ
        # Это упрощенная логика, в реальности нужно учитывать границы ОТФ
        tf_pattern = r'### ' + otf_code + r'/(\d+\.\d+)\. (.*?)\n'
        tf_matches = re.finditer(tf_pattern, markdown_text)
        
        for tf_match in tf_matches:
            tf_code = otf_code + '/' + tf_match.group(1)
            tf_name = tf_match.group(2).strip()
            tf_data = {
                'code': tf_code,
                'name': tf_name,
                'labor_actions': [],
                'required_skills': [],
                'required_knowledge': []
            }
            otf_data['labor_functions'].append(tf_data)
    
    ps_data['generalized_labor_functions'] = otf_list
    
    return ps_data

def parse_prof_standard(file_path: str) -> Dict[str, Any]:
    """
    Parse a professional standard file and extract its structure.
    
    Args:
        file_path: Path to the professional standard file
        
    Returns:
        dict: Structured data from the professional standard
    """
    # Read file
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
    
    # Detect encoding
    encoding = detect_encoding(file_bytes)
    
    # Decode the file
    file_content = file_bytes.decode(encoding)
    
    # Convert to markdown if it's HTML
    if file_path.lower().endswith('.html'):
        markdown_text = html_to_markdown_parser_enhanced(file_content)
    else:
        # Assume it's already markdown or plain text
        markdown_text = file_content
    
    # Extract structure
    ps_structure = extract_ps_structure(markdown_text)
    
    # Add metadata
    ps_structure['parsed_content'] = markdown_text
    
    return ps_structure

# Функция, вызываемая из routes.py для парсинга загруженного файла
def parse_uploaded_prof_standard(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Parse an uploaded professional standard file.
    
    Args:
        file_bytes: Bytes of the uploaded file
        filename: Name of the uploaded file
        
    Returns:
        dict: Structured data from the professional standard
    """
    # Detect encoding
    encoding = detect_encoding(file_bytes)
    
    # Decode the file
    try:
        file_content = file_bytes.decode(encoding)
    except UnicodeDecodeError:
        # Fallback to latin-1 which usually doesn't fail
        file_content = file_bytes.decode('latin-1')
    
    # Convert to markdown if it's HTML
    if filename.lower().endswith('.html'):
        markdown_text = html_to_markdown_parser_enhanced(file_content)
    else:
        # Assume it's already markdown or plain text
        markdown_text = file_content
    
    # Extract structure
    ps_structure = extract_ps_structure(markdown_text)
    
    # Add metadata
    ps_structure['parsed_content'] = markdown_text
    
    # Try to extract code from filename (e.g., "ps_06.001.html" -> "06.001")
    code_match = re.search(r'ps[_-]?(\d+\.\d+)', filename.lower())
    if code_match:
        ps_structure['code'] = code_match.group(1)
    
    return ps_structure