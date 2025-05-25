# filepath: competencies_matrix/nlp.py
import os
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

# ИСПРАВЛЕНО: Добавлен импорт os для получения переменной окружения
# Импортируем genai только если API_KEY доступен, чтобы избежать ошибок при инициализации
try:
    from google import genai
    from google.genai import types
    GOOGLE_GENAI_SDK_AVAILABLE = True
except ImportError:
    logging.error("google-genai package not found. Please install it using 'pip install google-genai'.")
    genai = None
    types = None
    GOOGLE_GENAI_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

# --- Конфигурация Gemini API ---
# ИСПРАВЛЕНО: Получаем API ключ из переменной окружения
# GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY") 
GOOGLE_AI_API_KEY = "AIzaSyDA0NoIT1yhuJwUzmAPqXl_lUOJ4chnaQA" 
GEMINI_MODEL_NAME = "gemini-2.0-flash"

# Инициализируем клиент один раз при загрузке модуля, если ключ доступен
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
    pass 


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
        "order_number": "STRING", // The order number from the main command (e.g., "922" from "Приказ ... № 922").
        "order_date": "YYYY-MM-DD", // The date of the order in YYYY-MM-DD format (e.g., "2020-08-07" from "от 7 августа 2020 г.").
        "direction_code": "STRING", // The direction code (e.g., "18.03.01").
        "direction_name": "STRING", // The name of the direction (e.g., "Химическая технология"). Capture the full name, removing quotes if present.
        "education_level": "STRING", // The education level (e.g., "бакалавриат", "магистратура", "специалитет").
        "generation": "STRING" // The FGOS generation (e.g., "3+", "3++"). If not found, use "unknown".
    }},
    "uk_competencies": [ // List of Universal Competencies (УК) from Section III.
        {{
            "code": "STRING", // УК code (e.g., "УК-1").
            "name": "STRING", // Full formulation of the UK competence. Remove trailing dots. Consolidate internal newlines and multiple spaces into single spaces.
            "category_name": "STRING" // Category name (e.g., "Системное и критическое мышление", "Самоорганизация и саморазвитие", "Безопасность жизнедеятельности", "Экономическая культура", "Гражданская позиция", "Инклюзивная компетентность", "Коммуникация", "Разработка и реализация проектов", "Командная работа и лидерство", "Межкультурное взаимодействие", "Самоорганизация и саморазвитие"). Ensure accurate category mapping.
        }}
        // ... more УК competencies
    ],
    "opk_competencies": [ // List of General Professional Competencies (ОПК) from Section III.
        {{
            "code": "STRING", // ОПК code (e.g., "ОПК-1").
            "name": "STRING", // Full formulation of the ОПК competence. Remove trailing dots. Consolidate internal newlines and multiple spaces into single spaces.
            "category_name": "STRING" // Category name (e.g., "Естественно-научная подготовка", "Профессиональная методология", "Адаптация к производственным условиям", "Инженерная и технологическая подготовка", "Научные исследования и разработки", "Информационно-коммуникационные технологии для профессиональной деятельности"). Ensure accurate category mapping.
        }}
        // ... more ОПК competencies
    ],
    "recommended_ps": [ // List of Recommended Professional Standards (ПС) from the appendix.
        {{
            "code": "STRING", // PS code (e.g., "26.001"). Format as XX.XXX.
            "name": "STRING" // Full name of the PS (e.g., "Специалист по обеспечению комплексного контроля производства наноструктурированных композиционных материалов"). Remove quotes. Consolidate internal newlines and multiple spaces into single spaces.
        }}
        // ... more recommended PS
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
            logger.error("Gemini API client was not initialized (likely due to configuration error).")
            raise RuntimeError("Gemini API client was not initialized. Cannot parse FGOS with NLP.")

    try:
        prompt_content = _create_fgos_prompt(fgos_text)
        
        logger.debug(f"Sending prompt to Gemini (first 500 chars of prompt):\n{prompt_content[:500]}...")
        logger.debug(f"Sending prompt to Gemini (first 2000 chars of FGOS_TEXT):\n{fgos_text[:2000]}...")
        
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=[prompt_content],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=8192 
            )
        )
        
        if not response.text:
            logger.error("Gemini response is empty or does not contain any text.")
            raise ValueError("Gemini response is empty.")
            
        response_text = response.text.strip()
        logger.debug(f"Received response from Gemini (first 500 chars):\n{response_text[:500]}...")
        logger.debug(f"Full Gemini response for debugging (potentially large):\n{response_text}")

        json_match = re.search(r'```\s*json\s*(.*?)\s*```', response_text, re.DOTALL | re.IGNORECASE)
        if not json_match:
            logger.error("Gemini response did not contain a valid JSON markdown block. Attempting to parse response as raw JSON.")
            try:
                parsed_data = json.loads(response_text)
                logger.info("Successfully parsed response_text as raw JSON.")
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse response_text as raw JSON: {json_err}")
                logger.error(f"Content that failed to parse: {response_text}")
                raise ValueError(f"Gemini response was not valid JSON and did not contain a JSON markdown block. Error: {json_err}")
        else:
            json_str = json_match.group(1).strip() 
            try:
                parsed_data = json.loads(json_str)
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse extracted JSON string from markdown block: {json_err}")
                logger.error(f"Extracted JSON string that failed to parse: {json_str}")
                raise ValueError(f"Extracted JSON string from markdown block was not valid JSON. Error: {json_err}")

        # Дополнительная валидация и приведение типов после парсинга JSON
        if 'metadata' in parsed_data and isinstance(parsed_data['metadata'], dict) and \
           'order_date' in parsed_data['metadata'] and parsed_data['metadata']['order_date']:
            try:
                date_str = parsed_data['metadata']['order_date']
                if isinstance(date_str, str):
                    parsed_data['metadata']['order_date'] = datetime.strptime(
                        date_str, '%Y-%m-%d'
                    ).date()
                elif isinstance(date_str, datetime):
                     parsed_data['metadata']['order_date'] = date_str.date()
            except (ValueError, TypeError) as e_date:
                logger.warning(f"Could not parse order_date '{parsed_data['metadata']['order_date']}' from Gemini output to date object: {e_date}. Keeping as is or setting to None.")
                pass
        
        logger.info("Successfully parsed FGOS text using Gemini API.")
        return parsed_data

    except Exception as e:
        logger.error(f"Error parsing FGOS with Gemini API: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка при парсинге ФГОС с помощью Gemini API: {e}")