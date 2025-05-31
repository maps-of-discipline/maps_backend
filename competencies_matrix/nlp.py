# filepath: competencies_matrix/nlp.py
import os
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime # Убедимся, что datetime импортирован

# --- ИМПОРТЫ КЛИЕНТОВ LLM ---
try:
    from google import genai
    from google.genai import types as gemini_types
    GOOGLE_GENAI_SDK_AVAILABLE = True
except ImportError:
    logging.error("google-genai package not found. Please install it using 'pip install google-genai'.")
    genai = None
    gemini_types = None
    GOOGLE_GENAI_SDK_AVAILABLE = False

try:
    from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    logging.warning("openai package not found. Please install it using 'pip install openai'. This is needed for local or Kluster.ai providers.")
    OpenAI = None
    APIConnectionError = None
    RateLimitError = None
    APIStatusError = None
    OPENAI_SDK_AVAILABLE = False

# Импортируем утилиту парсинга дат и конфигурацию
from .parsing_utils import parse_date_string
from config import (
    LLM_PROVIDER,
    GOOGLE_AI_API_KEY, GEMINI_MODEL_NAME, # Gemini
    LOCAL_LLM_BASE_URL, LOCAL_LLM_API_KEY, LOCAL_LLM_MODEL_NAME, # Local OpenAI-like
    KLUDESTER_AI_API_KEY, KLUDESTER_AI_BASE_URL, KLUDESTER_AI_MODEL_NAME # Kluster.ai
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# --- КЛИЕНТЫ LLM --- 
gemini_client = None
openai_compatible_client = None # For local or Kluster.ai

if LLM_PROVIDER == 'gemini':
    if GOOGLE_AI_API_KEY and GOOGLE_GENAI_SDK_AVAILABLE and genai:
        try:
            gemini_client = genai.Client(api_key=GOOGLE_AI_API_KEY)
            logger.info(f"Google Gemini API client configured successfully for model {GEMINI_MODEL_NAME}.")
        except Exception as e:
            logger.error(f"Failed to configure Google Gemini API client: {e}")
            gemini_client = None
    elif not GOOGLE_GENAI_SDK_AVAILABLE:
        logger.error("Google GenAI SDK is not available, but LLM_PROVIDER is 'gemini'. Parsing will fail.")
    elif not GOOGLE_AI_API_KEY:
        logger.error("GOOGLE_AI_API_KEY is not set, but LLM_PROVIDER is 'gemini'. Parsing will fail.")

elif LLM_PROVIDER == 'local':
    if OPENAI_SDK_AVAILABLE and OpenAI:
        try:
            openai_compatible_client = OpenAI(
                base_url=LOCAL_LLM_BASE_URL,
                api_key=LOCAL_LLM_API_KEY if LOCAL_LLM_API_KEY else 'no-api-key' # Some local LLMs don't require a key
            )
            logger.info(f"Local OpenAI-compatible LLM client configured for model {LOCAL_LLM_MODEL_NAME} at {LOCAL_LLM_BASE_URL}.")
        except Exception as e:
            logger.error(f"Failed to configure Local LLM client: {e}")
            openai_compatible_client = None
    elif not OPENAI_SDK_AVAILABLE:
        logger.error("OpenAI SDK is not available, but LLM_PROVIDER is 'local'. Parsing will fail.")

elif LLM_PROVIDER == 'klusterai':
    if OPENAI_SDK_AVAILABLE and OpenAI and KLUDESTER_AI_API_KEY:
        try:
            openai_compatible_client = OpenAI(
                api_key=KLUDESTER_AI_API_KEY,
                base_url=KLUDESTER_AI_BASE_URL
            )
            logger.info(f"Kluster.ai client configured successfully for model {KLUDESTER_AI_MODEL_NAME}.")
        except Exception as e:
            logger.error(f"Failed to configure Kluster.ai client: {e}")
            openai_compatible_client = None
    elif not OPENAI_SDK_AVAILABLE:
        logger.error("OpenAI SDK is not available, but LLM_PROVIDER is 'klusterai'. Parsing will fail.")
    elif not KLUDESTER_AI_API_KEY:
        logger.error("KLUDESTER_AI_API_KEY is not set, but LLM_PROVIDER is 'klusterai'. Parsing will fail.")
else:
    logger.error(f"Invalid LLM_PROVIDER: {LLM_PROVIDER}. Supported: 'gemini', 'local', 'klusterai'. No LLM client will be initialized.")


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

def parse_fgos_with_llm(fgos_text: str) -> Dict[str, Any]:
    """
    Использует выбранный LLM API для парсинга текста ФГОС ВО и извлечения структурированных данных.
    """
    prompt_content = _create_fgos_prompt(fgos_text)
    response_text = None
    parsed_data = {}

    logger.info(f"Attempting to parse FGOS using LLM provider: {LLM_PROVIDER}")

    if LLM_PROVIDER == 'gemini':
        if not gemini_client:
            if not GOOGLE_GENAI_SDK_AVAILABLE:
                raise RuntimeError("Gemini SDK (google-genai) is not available. Cannot parse FGOS with Gemini.")
            elif not GOOGLE_AI_API_KEY:
                raise RuntimeError("GOOGLE_AI_API_KEY environment variable is not set. Cannot parse FGOS with Gemini.")
            else:
                raise RuntimeError("Gemini API client model was not initialized. Cannot parse FGOS with Gemini.")
        try:
            logger.debug(f"Sending prompt to Gemini (model: {GEMINI_MODEL_NAME}, first 500 chars of prompt):\n{prompt_content[:500]}...")
            response = gemini_client.generate_content( # ИСПРАВЛЕНО: Прямой вызов generate_content
                model=GEMINI_MODEL_NAME,
                contents=[prompt_content],
                generation_config=gemini_types.GenerationConfig( # ИСПРАВЛЕНО: Использование GenerationConfig
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
                        logger.error("Failed to extract text from response.parts.")
                        raise RuntimeError("Gemini response was empty and no text found in parts.")
                else:
                    raise RuntimeError("Gemini response was empty.")
            else:
                response_text = response.text.strip()
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}", exc_info=True)
            raise RuntimeError(f"Ошибка при вызове Gemini API: {e}")

    elif LLM_PROVIDER in ['local', 'klusterai']:
        if not openai_compatible_client:
            if not OPENAI_SDK_AVAILABLE:
                raise RuntimeError(f"OpenAI SDK is not available. Cannot parse FGOS with {LLM_PROVIDER}.")
            else:
                raise RuntimeError(f"{LLM_PROVIDER} client was not initialized. Cannot parse FGOS.")
        
        current_model_name = LOCAL_LLM_MODEL_NAME if LLM_PROVIDER == 'local' else KLUDESTER_AI_MODEL_NAME
        logger.debug(f"Sending prompt to {LLM_PROVIDER} (model: {current_model_name}, first 500 chars of prompt):\n{prompt_content[:500]}...")
        
        try:
            completion = openai_compatible_client.chat.completions.create(
                model=current_model_name,
                messages=[
                    {"role": "system", "content": "You are an expert academic assistant. Your task is to parse the provided text of a FGOS VO PDF document and extract specific, structured data in JSON format. Strictly adhere to the specified JSON schema. DO NOT include any other text, explanations, or markdown outside of the JSON block. DO NOT include any conversational phrases. DO NOT omit any fields. If a field's value cannot be found, set it to null (for numbers/strings/dates) or [] (for lists), or false (for booleans). ENSURE all date formats are \"YYYY-MM-DD\". ENSURE all string values are properly escaped for JSON. ENSURE that the output is ONLY the JSON block wrapped in ```json ... ```."},
                    {"role": "user", "content": prompt_content} # The prompt from _create_fgos_prompt already contains the document text
                ],
                temperature=0.0,
                max_tokens=8000 # Adjust as needed, ensure it's high enough for full JSON
            )
            if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
                response_text = completion.choices[0].message.content.strip()
            else:
                logger.error(f"{LLM_PROVIDER} response is empty or malformed.")
                raise RuntimeError(f"{LLM_PROVIDER} response was empty or malformed.")
        except APIConnectionError as e:
            logger.error(f"Connection error with {LLM_PROVIDER} API: {e}", exc_info=True)
            raise RuntimeError(f"Ошибка подключения к {LLM_PROVIDER} API: {e}")
        except RateLimitError as e:
            logger.error(f"Rate limit exceeded for {LLM_PROVIDER} API: {e}", exc_info=True)
            raise RuntimeError(f"Превышен лимит запросов к {LLM_PROVIDER} API: {e}")
        except APIStatusError as e:
            logger.error(f"Error from {LLM_PROVIDER} API (status {e.status_code}): {e.response}", exc_info=True)
            raise RuntimeError(f"Ошибка от {LLM_PROVIDER} API (статус {e.status_code}): {e.message}")
        except Exception as e:
            logger.error(f"Error calling {LLM_PROVIDER} API: {e}", exc_info=True)
            raise RuntimeError(f"Ошибка при вызове {LLM_PROVIDER} API: {e}")
    else:
        logger.error(f"LLM_PROVIDER '{LLM_PROVIDER}' is not supported or client not initialized.")
        raise RuntimeError(f"LLM_PROVIDER '{LLM_PROVIDER}' is not supported or client not initialized.")

    # --- ОБЩАЯ ОБРАБОТКА ОТВЕТА --- 
    if not response_text:
        logger.error("LLM response text is empty after API call.")
        raise RuntimeError("Ответ от LLM API пуст.")

    logger.debug(f"Full LLM response for debugging (provider: {LLM_PROVIDER}, potentially large):\n{response_text}")

    json_match = re.search(r'```\s*json\s*(.*?)\s*```', response_text, re.DOTALL | re.IGNORECASE)
    if not json_match:
        logger.warning(f"LLM response (provider: {LLM_PROVIDER}) did not contain a JSON markdown block. Attempting to parse response as raw JSON.")
        try:
            parsed_data = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse raw JSON response from {LLM_PROVIDER}: {json_err}. Response text:\n{response_text}")
            raise RuntimeError(f"Не удалось распознать JSON из ответа {LLM_PROVIDER} (даже без markdown блока): {json_err}")
    else:
        json_str = json_match.group(1).strip()
        try:
            parsed_data = json.loads(json_str)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON from markdown block (provider: {LLM_PROVIDER}): {json_err}. JSON string:\n{json_str}")
            raise RuntimeError(f"Не удалось распознать JSON из markdown блока от {LLM_PROVIDER}: {json_err}")

    # --- ГАРАНТИЯ ПРЕОБРАЗОВАНИЯ ДАТЫ для FGOS metadata.order_date ---
    if 'metadata' in parsed_data and isinstance(parsed_data['metadata'], dict):
        order_date_value = parsed_data['metadata'].get('order_date')
        if isinstance(order_date_value, str):
            parsed_data['metadata']['order_date'] = parse_date_string(order_date_value)
        elif isinstance(order_date_value, datetime):
            parsed_data['metadata']['order_date'] = order_date_value.date()
        elif not isinstance(order_date_value, datetime.date) and order_date_value is not None:
            logger.warning(f"metadata.order_date has an unexpected type: {type(order_date_value)}. Attempting to clear.")
            parsed_data['metadata']['order_date'] = None
        
        # Гарантия преобразования дат для recommended_ps.approval_date
        if 'recommended_ps' in parsed_data and isinstance(parsed_data['recommended_ps'], list):
            for ps_item in parsed_data['recommended_ps']:
                if isinstance(ps_item, dict) and 'approval_date' in ps_item:
                    approval_date_value = ps_item.get('approval_date')
                    if isinstance(approval_date_value, str):
                        ps_item['approval_date'] = parse_date_string(approval_date_value)
                    elif isinstance(approval_date_value, datetime):
                        ps_item['approval_date'] = approval_date_value.date()
                    elif not isinstance(approval_date_value, datetime.date) and approval_date_value is not None:
                        logger.warning(f"recommended_ps.approval_date has an unexpected type: {type(approval_date_value)}. Setting to None.")
                        ps_item['approval_date'] = None
    else: # If metadata is missing or not a dict
         if 'metadata' not in parsed_data:
             logger.warning("'metadata' key missing in parsed_data. Initializing with None for order_date.")
             parsed_data['metadata'] = {} # Initialize if completely missing
         parsed_data['metadata']['order_date'] = None # Ensure order_date exists, even if None

    logger.info(f"Successfully parsed FGOS text using {LLM_PROVIDER} API.")
    return parsed_data

# Для обратной совместимости, если где-то еще используется старое имя функции
parse_fgos_with_gemini = parse_fgos_with_llm