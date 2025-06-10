# competencies_matrix/nlp.py
import os
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

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
logger.setLevel(logging.DEBUG)

# --- Конфигурация Gemini API ---
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
if not GOOGLE_AI_API_KEY: # Для локальной отладки без .env
    GOOGLE_AI_API_KEY = "AIzaSyDA0NoIT1yhuJwUzmAPqXl_lUOJ4chnaQA" # не менять
    
GEMINI_MODEL_NAME = "gemini-2.0-flash-lite" # не менять

gemini_client = None
if GOOGLE_AI_API_KEY and GOOGLE_GENAI_SDK_AVAILABLE and genai:
    try:
        gemini_client = genai.Client(api_key=GOOGLE_AI_API_KEY) # не менять
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
            "name": "STRING",
            "approval_date": "YYYY-MM-DD"
        }}
    ]
}}
```

- `code`: Extract the exact code (e.g., "26.001", "40.042").
- `title`: Extract only the *short, clean name* of the Professional Standard, without legal citations, registration numbers, or dates. Just the core title, like "Специалист по производству".
- `approval_date`: Extract the approval date of the *Professional Standard itself* if it is explicitly mentioned in the recommendation text for that specific PS. If not found, set to `null`. Format as "YYYY-MM-DD".

Here is the FGOS VO document text to parse:

{fgos_text}
"""
    return prompt

def _create_uk_indicators_disposition_prompt(disposition_text: str, education_level: str) -> str:
    """
    Создает промпт для Gemini API для извлечения структурированных данных
    из текста Распоряжения об установлении индикаторов универсальных компетенций,
    с учетом указанного уровня образования.
    """
    prompt = f"""
You are an expert academic assistant that extracts structured information from official dispositions (Распоряжения) regarding Universal Competency Indicators (ИУК).
Your task is to parse the provided text of a disposition document and extract specific, structured data in JSON format.
Strictly adhere to the specified JSON schema.

Important: Analyze the entire document, but ONLY extract the universal competencies and their indicators that apply to the specified education level: '{education_level}'.
If the disposition defines indicators for multiple education levels (e.g., a table for 'бакалавриат' and another for 'специалитет'), you must return data ONLY for the '{education_level}' section.

**DO NOT** include any other text, explanations, or markdown outside of the JSON block.
**DO NOT** omit any fields from the required JSON structure. If a field's value cannot be found, set it to `null` (for numbers/strings/dates) or `[]` (for lists).
**ENSURE** all date formats are "YYYY-MM-DD".
**ENSURE** all string values are properly escaped for JSON.
**ENSURE** that the output is **only** the JSON block wrapped in ```json ... ```.

The JSON should be formatted as follows:

```json
{{
    "disposition_metadata": {{
        "number": "STRING",
        "date": "YYYY-MM-DD",
        "title": "STRING"
    }},
    "uk_competencies_with_indicators": [
        {{
            "code": "STRING",
            "name": "STRING",
            "category_name": "STRING",
            "indicators": [
                {{
                    "code": "STRING",
                    "formulation": "STRING"
                }}
            ]
        }}
    ]
}}
```

**Extraction Rules:**
- `disposition_metadata.number`: Extract the number of the disposition (e.g., "505-Р").
- `disposition_metadata.date`: Extract the date of the disposition (e.g., "30.05.2023"). Format as "YYYY-MM-DD".
- `disposition_metadata.title`: Extract the full title of the disposition (e.g., "Об установлении индикаторов достижения универсальных компетенций").
- `uk_competencies_with_indicators.code`: Extract the exact UK code (e.g., "УК-1").
- `uk_competencies_with_indicators.name`: Extract the full name of the UK.
- `uk_competencies_with_indicators.category_name`: Extract the category name of the UK (e.g., "Системное и критическое мышление", "Коммуникация"). If not explicitly mentioned, try to infer based on typical categories, or set to `null`.
- `uk_competencies_with_indicators.indicators.code`: Extract the exact indicator code (e.g., "ИУК-1.1", "ИУК-2.3").
- `uk_competencies_with_indicators.indicators.formulation`: Extract the full formulation of the indicator.

Here is the disposition document text to parse:

{disposition_text}
"""
    return prompt

def _call_gemini_api(prompt_content: str) -> Dict[str, Any]:
    """Helper function to call the Gemini API and parse the response."""
    if not gemini_client:
        raise RuntimeError("Gemini API client is not configured.")

    logger.debug(f"Sending prompt to Gemini (first 500 chars):\n{prompt_content[:500]}...")
    
    # не менять
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=[prompt_content],
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=8192 
        )
    )
    
    # ИСПРАВЛЕНО: Более надежная обработка ответа
    try:
        response_text = response.text
    except Exception as e:
        logger.error(f"Failed to access response.text, trying parts. Error: {e}")
        try:
            response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
        except Exception as part_e:
            logger.error(f"Failed to extract text from response.parts. Error: {part_e}")
            raise ValueError("Gemini response is empty or in an unexpected format.")
    
    if not response_text:
        raise ValueError("Gemini response is empty.")
    
    logger.debug(f"Full Gemini response for debugging (potentially large):\n{response_text}")

    json_match = re.search(r'```\s*json\s*(.*?)\s*```', response_text, re.DOTALL | re.IGNORECASE)
    if not json_match:
        logger.warning("Gemini response did not contain a JSON markdown block. Attempting to parse response as raw JSON.")
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as json_err:
            raise ValueError(f"Gemini response was not valid JSON. Error: {json_err}")
    else:
        json_str = json_match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as json_err:
            raise ValueError(f"Extracted JSON string from markdown block was not valid. Error: {json_err}")

def parse_uk_indicators_disposition_with_gemini(disposition_text: str, education_level: str) -> Dict[str, Any]:
    """
    Использует Gemini API для парсинга текста Распоряжения
    и извлечения структурированных данных об индикаторах УК.
    Принимает education_level для фильтрации результатов от LLM.
    """
    try:
        prompt = _create_uk_indicators_disposition_prompt(disposition_text, education_level)
        parsed_data = _call_gemini_api(prompt)

        # --- Валидация и очистка данных ---
        if 'disposition_metadata' in parsed_data and isinstance(parsed_data['disposition_metadata'], dict):
            date_val = parsed_data['disposition_metadata'].get('date')
            parsed_data['disposition_metadata']['date'] = parse_date_string(date_val)
        
        # Очистка от \n в именах и формулировках
        if 'uk_competencies_with_indicators' in parsed_data and isinstance(parsed_data['uk_competencies_with_indicators'], list):
            for uk_comp in parsed_data['uk_competencies_with_indicators']:
                if isinstance(uk_comp.get('name'), str):
                    uk_comp['name'] = re.sub(r'\s+', ' ', uk_comp['name']).strip()
                if isinstance(uk_comp.get('category_name'), str):
                    uk_comp['category_name'] = re.sub(r'\s+', ' ', uk_comp['category_name']).strip()
                
                if isinstance(uk_comp.get('indicators'), list):
                    for indicator in uk_comp['indicators']:
                        if isinstance(indicator.get('formulation'), str):
                            indicator['formulation'] = re.sub(r'\s+', ' ', indicator['formulation']).strip()

        logger.info("Successfully parsed disposition text using Gemini API.")
        return parsed_data
    except Exception as e:
        logger.error(f"Error parsing disposition with Gemini API: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка при парсинге распоряжения с помощью Gemini API: {e}")

def parse_fgos_with_gemini(fgos_text: str) -> Dict[str, Any]:
    """
    Использует Gemini API для парсинга текста ФГОС ВО
    и извлечения структурированных данных.
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
        
        if not hasattr(response, 'text') or not response.text:
            logger.error("Gemini response is empty or does not contain any text.")
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
            
        logger.debug(f"Full Gemini response for debugging (potentially large):\n{response_text}")

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

        # --- ГАРАНТИЯ ПРЕОБРАЗОВАНИЯ ДАТЫ для metadata.order_date и recommended_ps.approval_date ---
        if 'metadata' in parsed_data and isinstance(parsed_data['metadata'], dict):
            order_date_value = parsed_data['metadata'].get('order_date')
            if isinstance(order_date_value, str):
                parsed_date_obj = parse_date_string(order_date_value)
                if parsed_date_obj:
                    parsed_data['metadata']['order_date'] = parsed_date_obj
                    logger.info(f"Successfully parsed metadata 'order_date' from string '{order_date_value}' to date object: {parsed_date_obj}")
                else:
                    logger.error(f"Could not parse metadata 'order_date' string '{order_date_value}' from Gemini output. Setting to None.")
                    parsed_data['metadata']['order_date'] = None
            elif isinstance(order_date_value, datetime):
                parsed_data['metadata']['order_date'] = order_date_value.date()
                logger.info(f"Converted metadata 'order_date' from datetime '{order_date_value}' to date object: {parsed_data['metadata']['order_date']}")
            elif not isinstance(order_date_value, datetime.date) and order_date_value is not None:
                logger.error(f"Metadata 'order_date' has unexpected type: {type(order_date_value)}. Value: {order_date_value}. Setting to None.")
                parsed_data['metadata']['order_date'] = None
        else:
            if 'metadata' not in parsed_data: parsed_data['metadata'] = {}
            parsed_data['metadata']['order_date'] = None # Ensure it exists if parsing failed

        if 'recommended_ps' in parsed_data and isinstance(parsed_data['recommended_ps'], list):
            for ps_entry in parsed_data['recommended_ps']:
                if isinstance(ps_entry, dict):
                    approval_date_value = ps_entry.get('approval_date')
                    if isinstance(approval_date_value, str):
                        parsed_date_obj = parse_date_string(approval_date_value)
                        if parsed_date_obj:
                            ps_entry['approval_date'] = parsed_date_obj
                            logger.info(f"Successfully parsed recommended_ps 'approval_date' from string '{approval_date_value}' to date object: {parsed_date_obj}")
                        else:
                            logger.warning(f"Could not parse recommended_ps 'approval_date' string '{approval_date_value}'. Setting to None.")
                            ps_entry['approval_date'] = None
                    elif isinstance(approval_date_value, datetime):
                        ps_entry['approval_date'] = approval_date_value.date()
                        logger.info(f"Converted recommended_ps 'approval_date' from datetime '{approval_date_value}' to date object: {ps_entry['approval_date']}")
                    elif not isinstance(approval_date_value, datetime.date) and approval_date_value is not None:
                        logger.warning(f"Recommended_ps 'approval_date' has unexpected type: {type(approval_date_value)}. Value: {approval_date_value}. Setting to None.")
                        ps_entry['approval_date'] = None

        logger.info("Successfully parsed FGOS text using Gemini API.")
        return parsed_data

    except Exception as e:
        logger.error(f"Error parsing FGOS with Gemini API: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка при парсинге ФГОС с помощью Gemini API: {e}")