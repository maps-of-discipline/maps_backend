# filepath: competencies_matrix/parsing_utils.py
import datetime
import re
import logging
from typing import Optional, Any
from collections import Counter

logger = logging.getLogger(__name__)


def preprocess_text_for_llm(text: str) -> str:
    """
    Очистка посылаемого текста от мусора в целях экономии на инференсе языковыми моделями
    """
    lines = text.splitlines()
    processed_lines = []
    
    page_number = re.compile(r'^\s*(\d+\s*/\s*\d+|\d+)\s*$')
    garant = re.compile(r'система гарант', re.IGNORECASE)
    date_and_page = re.compile(r'^\s*\d{2}\.\d{2}\.\d{4}\s+\d+/\d+\s*$', re.IGNORECASE) # e.g., "21.06.2021 1/13"
    long_string = re.compile(r'^[^\s]{100,}$')

    for line in lines:
        stripped_line = line.strip()

        if not stripped_line:
            continue
            
        if page_number.match(stripped_line) or date_and_page.match(stripped_line):
            continue
            
        if garant.search(stripped_line):
            continue

        if long_string.match(stripped_line):
            logger.debug(f"Skipping long unbroken line: {stripped_line[:50]}...")
            continue
            
        if processed_lines and processed_lines[-1].endswith('-'):
            processed_lines[-1] = processed_lines[-1][:-1] + stripped_line
        else:
            processed_lines.append(stripped_line)

    cleaned_text = "\n".join(processed_lines)
    
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)

    original_len = len(text)
    cleaned_len = len(cleaned_text)
    reduction_percent = (1 - cleaned_len / original_len) * 100 if original_len > 0 else 0
    
    logger.info(
        f"Text preprocessing completed. Original length: {original_len}, "
        f"Cleaned length: {cleaned_len}, Reduction: {reduction_percent:.2f}%"
    )
    
    return cleaned_text


def parse_date_string(date_str: Optional[str]) -> Optional[datetime.date]:
    """Парсит строку даты в объект datetime.date, обрабатывая несколько форматов."""
    if not date_str:
        return None
    
    try:
        return datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass
    
    try:
        if isinstance(date_str, str):
            day, month, year = map(int, date_str.split('.'))
            return datetime.date(year, month, day)
    except (ValueError, TypeError):
        pass
    
    logger.warning(f"Не удалось распознать формат даты: '{date_str}'. Возвращаем None.")
    return None