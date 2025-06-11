# filepath: competencies_matrix/fgos_parser.py
import io
import logging
from typing import Dict, List, Any # Убираем Tuple, т.к. не используется

from pdfminer.high_level import extract_text

from .nlp_logic import parse_fgos_with_gemini 

logger = logging.getLogger(__name__)

def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Главная функция парсинга PDF файла ФГОС ВО.
    Теперь использует NLP-модуль для извлечения структурированных данных.
    """
    logger.info(f"Starting PDF parsing for FGOS file: {filename} using NLP module.")
    
    try:
        # Извлекаем весь текст из PDF с помощью pdfminer.six
        text_content = extract_text(io.BytesIO(file_bytes))
        
        # Передаем весь текст в NLP-парсер
        parsed_data_from_nlp = parse_fgos_with_gemini(text_content)
        
        # Добавляем сырой текст в итоговые данные для сохранения или отладки
        parsed_data_from_nlp['raw_text'] = text_content

        # Проверяем наличие критически важных метаданных
        if 'metadata' not in parsed_data_from_nlp or not isinstance(parsed_data_from_nlp['metadata'], dict):
            logger.error(f"Critical 'metadata' key missing or not a dict after NLP parsing for {filename}.")
            raise ValueError(f"Ключ 'metadata' отсутствует или имеет неверный формат в ответе NLP-парсера для файла '{filename}'.")

        critical_fields = ['order_number', 'direction_code', 'education_level']
        # ИСПРАВЛЕНО: Правильная переменная для доступа к метаданным
        missing_critical = [field for field in critical_fields if not parsed_data_from_nlp['metadata'].get(field)]
        
        if missing_critical:
             logger.error(f"Missing one or more CRITICAL metadata fields after NLP parsing for {filename}. Missing: {', '.join(missing_critical)}.")
             raise ValueError(f"Не удалось извлечь критически важные метаданные из файла ФГОС '{filename}' через NLP-парсер. Отсутствуют: {', '.join(missing_critical)}.")

        # Basic check for other expected top-level keys from NLP
        expected_keys = ['uk_competencies', 'opk_competencies', 'recommended_ps']
        for key in expected_keys:
            if key not in parsed_data_from_nlp:
                 logger.warning(f"Expected key '{key}' missing from NLP parser result for {filename}. Initializing to empty list.")
                 parsed_data_from_nlp[key] = [] # Инициализируем пустым списком, если LLM что-то не вернул.


        logger.info(f"PDF parsing for FGOS {filename} finished via NLP. Metadata Extracted: {bool(parsed_data_from_nlp.get('metadata'))}, UK Found: {len(parsed_data_from_nlp.get('uk_competencies', []))}, OPK Found: {len(parsed_data_from_nlp.get('opk_competencies', []))}, Recommended PS Found: {len(parsed_data_from_nlp.get('recommended_ps', []))}")
        
        return parsed_data_from_nlp

    except FileNotFoundError:
        logger.error(f"File not found: {filename}")
        raise
    except ImportError as e:
        logger.error(f"Missing dependency (pdfminer.six or google-genai): {e}.")
        raise ImportError(f"Отсутствует зависимость: {e}. Пожалуйста, установите необходимые пакеты.")
    except ValueError as e: # Catch custom ValueErrors or from NLP parser
        logger.error(f"Data validation or parsing error for {filename}: {e}")
        raise # Re-raise to be handled by calling code
    except RuntimeError as e: # Catch RuntimeError from nlp_parser for API issues
        logger.error(f"NLP parsing failed for {filename}: {e}", exc_info=True)
        raise Exception(f"Не удалось спарсить ФГОС с помощью NLP-модуля: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during PDF parsing for {filename}: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")