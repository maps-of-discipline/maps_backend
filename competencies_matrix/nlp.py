# filepath: competencies_matrix/nlp.py
import os
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime # Убедимся, что datetime импортирован

try:
    from google import genai
    from google.genai import types
    GOOGLE_GENAI_SDK_AVAILABLE = True
except ImportError:
    logging.error("google-genai package not found. Please install it using 'pip install google-genai'.")
    genai = None
    types = None
    GOOGLE_GENAI_SDK_AVAILABLE = False

# Импортируем утилиту парсинга дат
from .parsing_utils import parse_date_string


logger = logging.getLogger(__name__)
# Уровень DEBUG будет установлен в app.py или fgos_import.py при необходимости

# --- Конфигурация Gemini API ---
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
if not GOOGLE_AI_API_KEY: # Для локальной отладки без .env
    GOOGLE_AI_API_KEY = "AIzaSyDA0NoIT1yhuJwUzmAPqXl_lUOJ4chnaQA" # ИСПРАВЛЕНО: Используем актуальный ключ для тестов, если не из .env
    
GEMINI_MODEL_NAME = "gemini-1.5-flash-latest" # ИСПРАВЛЕНО: Использование актуальной модели

gemini_client = None
if GOOGLE_AI_API_KEY and GOOGLE_GENAI_SDK_AVAILABLE and genai:
    try:
        gemini_client = genai.Client(api_key=GOOGLE_AI_API_KEY)
        logger.info(f"Google Gemini API client configured successfully.")
    except Exception as e:
        logger.error(f"Failed to configure Google Gemini API client: {e}")
        gemini_client = None
elif GOOGLE_GENAI_SDK_AVAILABLE and genai: 
    logger.warning("GOOGLE_AI_API_KEY environment variable is not set. Gemini API will not be used for parsing.")
else:
    logger.warning("Google GenAI SDK is not available. Gemini API will not be used for parsing.")


def _create_fgos_prompt(fgos_text: str) -> str:
    """
    Создает промпт для Gemini API для извлечения структурированных данных из текста ФГОС.
    Промпт очень детально описывает желаемую JSON-структуру и правила извлечения.
    """
    prompt = f"""
You are an expert academic assistant that extracts structured information from Federal State Educational Standards (FGOS VO) documents.
Your task is to parse the provided text of a FGOS VO PDF document and extract specific, structured data in JSON format.
Strictly adhere to the specified JSON schema.

**DO NOT** include any other text, explanations, or markdown outside of the JSON block.
**DO NOT** include any conversational phrases like "Here is the JSON output:".
**DO NOT** omit any fields from the required JSON structure. If a field's value cannot be found, set it to `null` (for numbers/strings/dates) or `[]` (for lists), or `false` (for booleans).
**ENSURE** all date formats are "YYYY-MM-DD".
**ENSURE** all string values are properly escaped for JSON.
**ENSURE** that the output is **only** the JSON block wrapped in ```json ... ```.

The JSON should be formatted as follows:

```json
{{
    "metadata": {{
        "order_number": "STRING",
        "order_date": "YYYY-MM-DD",
        "direction_code": "STRING",
        "direction_name": "STRING",
        "education_level": "STRING",
        "generation": "STRING"
    }},
    "uk_competencies": [
        {{
            "code": "STRING",
            "name": "STRING",
            "category_name": "STRING"
        }}
    ],
    "opk_competencies": [
        {{
            "code": "STRING",
            "name": "STRING",
            "category_name": "STRING"
        }}
    ],
    "recommended_ps": [
        {{
            "code": "STRING",
            "name": "STRING"
        }}
    ]
}}
```

Here is the FGOS VO document text to parse:

{fgos_text}
"""
    return prompt

def parse_fgos_with_gemini(fgos_text: str) -> Dict[str, Any]:
    """
    Использует Gemini API для парсинга текста ФГОС ВО и извлечения структурированных данных.
    """
    if not gemini_client:
        if not GOOGLE_GENAI_SDK_AVAILABLE:
            logger.error("Gemini SDK (google-genai) is not available.")
            raise RuntimeError("Gemini SDK (google-genai) is not available. Cannot parse FGOS with NLP.")
        elif not GOOGLE_AI_API_KEY:
            logger.error("GOOGLE_AI_API_KEY environment variable is not set.")
            raise RuntimeError("GOOGLE_AI_API_KEY environment variable is not set. Cannot parse FGOS with NLP.")
        else:
            logger.error("Gemini API client model was not initialized (likely due to configuration error).")
            raise RuntimeError("Gemini API client model was not initialized. Cannot parse FGOS with NLP.")

    try:
        prompt_content = _create_fgos_prompt(fgos_text)
        
        logger.debug(f"Sending prompt to Gemini (first 500 chars of prompt):\n{prompt_content[:500]}...")
        
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=[prompt_content],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=8192 
            )
        )
        
        # ИСПРАВЛЕНО: Доступ к тексту ответа через response.text
        if not hasattr(response, 'text') or not response.text:
            logger.error("Gemini response is empty or does not contain any text.")
            # Попытка извлечь из parts, если text пустой, но есть parts
            if hasattr(response, 'parts') and response.parts:
                logger.info("Trying to extract text from response.parts as response.text was empty.")
                response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                if not response_text:
                    logger.error("response.parts also did not yield any text.")
                    raise ValueError("Gemini response is empty (checked text and parts).")
            else:
                raise ValueError("Gemini response is empty (no text attribute and no parts).")
        else:
            response_text = response.text.strip()
            
        logger.debug(f"Received response from Gemini (first 500 chars):\n{response_text[:500]}...")
        # Уменьшим объем полного лога, если он слишком большой
        # logger.debug(f"Full Gemini response for debugging (potentially large):\n{response_text}")

        json_match = re.search(r'```\s*json\s*(.*?)\s*```', response_text, re.DOTALL | re.IGNORECASE)
        if not json_match:
            logger.warning("Gemini response did not contain a JSON markdown block. Attempting to parse response as raw JSON.")
            try:
                parsed_data = json.loads(response_text)
                logger.info("Successfully parsed response_text as raw JSON.")
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse response_text as raw JSON: {json_err}")
                logger.debug(f"Content that failed to parse: {response_text}") # Полный текст для отладки
                raise ValueError(f"Gemini response was not valid JSON and did not contain a JSON markdown block. Error: {json_err}")
        else:
            json_str = json_match.group(1).strip()
            try:
                parsed_data = json.loads(json_str)
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse extracted JSON string from markdown block: {json_err}")
                logger.debug(f"Extracted JSON string that failed to parse: {json_str}") # Полный текст для отладки
                raise ValueError(f"Extracted JSON string from markdown block was not valid JSON. Error: {json_err}")

        # --- ИСПРАВЛЕНИЕ и ГАРАНТИЯ ПРЕОБРАЗОВАНИЯ ДАТЫ ---
        if 'metadata' in parsed_data and isinstance(parsed_data['metadata'], dict) and \
           'order_date' in parsed_data['metadata']:
            order_date_value = parsed_data['metadata']['order_date']
            if isinstance(order_date_value, str):
                parsed_date_obj = parse_date_string(order_date_value) # Используем нашу утилиту
                if parsed_date_obj:
                    parsed_data['metadata']['order_date'] = parsed_date_obj
                    logger.info(f"Successfully parsed 'order_date' from string '{order_date_value}' to date object: {parsed_date_obj}")
                else:
                    logger.error(f"Could not parse 'order_date' string '{order_date_value}' from Gemini output. Setting to None.")
                    parsed_data['metadata']['order_date'] = None
            elif isinstance(order_date_value, datetime): # На случай если LLM вернет datetime
                parsed_data['metadata']['order_date'] = order_date_value.date()
                logger.info(f"Converted 'order_date' from datetime '{order_date_value}' to date object: {parsed_data['metadata']['order_date']}")
            elif isinstance(order_date_value, datetime.date): # Уже в нужном формате
                 logger.info(f"'order_date' is already a date object: {order_date_value}")
                 pass # Уже datetime.date
            elif order_date_value is None:
                 logger.warning("FGOS metadata 'order_date' is null from Gemini output.")
            else:
                logger.error(f"FGOS metadata 'order_date' has unexpected type: {type(order_date_value)}. Value: {order_date_value}. Setting to None.")
                parsed_data['metadata']['order_date'] = None
        elif 'metadata' in parsed_data and isinstance(parsed_data['metadata'], dict):
             logger.warning("FGOS metadata 'order_date' key is missing. Setting to None.")
             parsed_data['metadata']['order_date'] = None
        else:
             logger.error("FGOS 'metadata' key is missing or not a dict. Cannot process 'order_date'.")
             if 'metadata' not in parsed_data: parsed_data['metadata'] = {} # Ensure metadata dict exists
             parsed_data['metadata']['order_date'] = None


        logger.info("Successfully parsed FGOS text using Gemini API.")
        return parsed_data

    except Exception as e:
        logger.error(f"Error parsing FGOS with Gemini API: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка при парсинге ФГОС с помощью Gemini API: {e}")