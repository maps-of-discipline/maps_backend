# filepath: competencies_matrix/fgos_parser.py
import io
import logging
from typing import Dict, Any

from pdfminer.high_level import extract_text

from . import nlp
from .parsing_utils import preprocess_text_for_llm

logger = logging.getLogger(__name__)


def parse_fgos_file(file_bytes: bytes, filename: str) -> dict:
    """Parses an FGOS PDF file and returns structured data."""
    try:
        logger.debug(f"FGOS Parser: Starting text extraction from {filename}")
        raw_text = extract_text(io.BytesIO(file_bytes))
        logger.debug(f"FGOS Parser: Raw text extracted. Length: {len(raw_text)} chars.")
        
        clean_text = preprocess_text_for_llm(raw_text)
        logger.debug(f"FGOS Parser: Cleaned text prepared. Length: {len(clean_text)} chars.")
        
        if not clean_text.strip():
            logger.error(f"FGOS Parser: Cleaned text is empty or only whitespace for {filename}. Cannot send to LLM.")
            raise ValueError("Извлеченный текст из файла пуст или содержит только пробелы после очистки.")

        data = nlp.parse_fgos_with_llm(clean_text)
        
        if not data or not data.get('metadata'):
             logger.error(f"Upload FGOS: Parsing succeeded but essential metadata missing for {filename}. Parsed data: {data}")
             raise ValueError("Не удалось извлечь основные метаданные из файла ФГОС.")

        return data
    except ValueError as e:
        logger.error(f"FGOS Parser: ValueError for {filename}: {e}", exc_info=True)
        raise
    except Exception as e:
        error_message = str(e)
        if "maximum context length" in error_message:
            logger.error(f"LLM API input size error for {filename} AFTER cleaning: File too large for processing. Error: {error_message}")
            raise ValueError(f"Текст файла '{filename}' слишком большой для обработки LLM. Возможно, это нестандартный или очень объемный документ.")
        else:
            logger.error(f"FGOS Parser: Unexpected error parsing {filename}: {e}", exc_info=True)
            raise ValueError(f"Неожиданная ошибка при парсинге файла '{filename}': {e}")