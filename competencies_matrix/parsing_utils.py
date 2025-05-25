# filepath: competencies_matrix/parsing_utils.py
import datetime
import re
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

def parse_date_string(date_str: Optional[str]) -> Optional[datetime.date]:
    """
    Attempts to parse date strings from common formats (YYYY-MM-DD, DD.MM.YYYY, DD MonthName YYYY,
    and DayName, DD MonName YYYY HH:MM:SS GMT/UTC).
    Handles variations in format and returns a datetime.date object or None if parsing fails.
    """
    if not date_str:
        logger.debug("parse_date_string: Input date string is empty.")
        return None

    date_str = date_str.strip()

    # Try YYYY-MM-DD format (common in XML, or requested from LLM)
    try:
        parsed_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        logger.debug(f"parse_date_string: Successfully parsed '{date_str}' as YYYY-MM-DD.")
        return parsed_date
    except ValueError:
        logger.debug(f"parse_date_string: '{date_str}' did not match YYYY-MM-DD format. Trying other formats.")
        pass 

    # Try DD.MM.YYYY format
    try:
        parsed_date = datetime.datetime.strptime(date_str, '%d.%m.%Y').date()
        logger.debug(f"parse_date_string: Successfully parsed '{date_str}' as DD.MM.YYYY.")
        return parsed_date
    except ValueError:
        logger.debug(f"parse_date_string: '{date_str}' did not match DD.MM.YYYY format.")
        pass 

    # Try DD MonthName YYYY format (e.g., '7 августа 2020', '19 сентября 2017 г.')
    month_names = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
        'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    match = re.match(r'(\d{1,2})\s+([а-яА-Я]+)(?:\s+года)?\s+(\d{4})\s*г?\.?', date_str, re.IGNORECASE)
    if match:
        day_str, month_name_str, year_str = match.groups()[:3] 
        month = month_names.get(month_name_str.lower())
        if month:
            try:
                parsed_date = datetime.date(int(year_str), month, int(day_str))
                logger.debug(f"parse_date_string: Successfully parsed '{date_str}' as DD MonthName YYYY.")
                return parsed_date
            except ValueError:
                logger.warning(f"parse_date_string: Invalid date components for format 'DD MonthName YYYY': {year_str}-{month}-{day_str}")
                return None
        else:
            logger.warning(f"parse_date_string: Unknown month name '{month_name_str}' for format 'DD MonthName YYYY'.")
            return None

    try:
        cleaned_date_str = re.sub(r'\s*(GMT|UTC)$', '', date_str, flags=re.IGNORECASE).strip()
        parsed_date = datetime.datetime.strptime(cleaned_date_str, '%a, %d %b %Y %H:%M:%S').date()
        logger.debug(f"parse_date_string: Successfully parsed '{date_str}' as DayName, DD MonName YYYY HH:MM:SS.")
        return parsed_date
    except ValueError:
        logger.debug(f"parse_date_string: '{date_str}' did not match DayName, DD MonName YYYY HH:MM:SS format.")
        pass

    logger.warning(f"parse_date_string: Could not parse date string: '{date_str}' using any known format.")
    return None