# filepath: competencies_matrix/nlp_logic.py
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

# Импортируем конфигурацию и клиент из нового файла
from .nlp_config import get_gemini_client, get_gemini_types, GOOGLE_GENAI_SDK_AVAILABLE, GEMINI_MODEL_NAME

# Импортируем утилиту парсинга дат
from .parsing_utils import parse_date_string


logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG) # Уровень логирования можно настраивать через app.py

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

def _create_pk_correction_prompt(raw_phrase: str) -> str:
    """
    Создает промпт для Gemini API для грамматической коррекции сырой фразы
    в формулировку Профессиональной Компетенции.
    """
    prompt = f"""
Ты - лингвистический ассистент, специализирующийся на академических формулировках.
Твоя задача - преобразовать предоставленную сырую фразу в грамматически корректную и подходящую для описания ПРОФЕССИОНАЛЬНОЙ КОМПЕТЕНЦИИ в контексте высшего образования.

Строгие правила:
1.  Фраза ДОЛЖНА начинаться со слова "Способен" (или "Способна", если контекст женского рода, но по умолчанию "Способен").
2.  Сохрани основной смысл исходной фразы.
3.  Обеспечь грамматическую и стилистическую корректность на русском языке.
4.  НЕ добавляй никаких объяснений, преамбул, разметки Markdown, кроме самой откорректированной фразы.
5.  НЕ добавляй никаких лишних символов или знаков препинания в конце (например, точку).

Пример:
Исходная фраза: "Разработка и отладка программного кода"
Результат: "Способен разрабатывать и отлаживать программный код"

Исходная фраза: "Анализ возможностей реализации требований к компьютерному программному обеспечению"
Результат: "Способен анализировать возможности реализации требований к компьютерному программному обеспечению"

Исходная фраза: "Исправление дефектов программного кода, зафиксированных в базе данных дефектов"
Результат: "Способен исправлять дефекты программного кода, зафиксированные в базе данных дефектов"

Исходная фраза: "{raw_phrase}"
Результат:
"""
    return prompt

def _create_pk_ipk_generation_prompt(
    selected_tfs_data: List[Dict],
    selected_zun_elements: Dict[str, List[Dict]]
) -> str:
    """
    Создает промпт для Gemini API для генерации формулировок ПК и ИПК на основе
    выбранных Трудовых Функций и ЗУН-элементов.
    """
    tfs_json = json.dumps([{"code": tf['code'], "name": tf['name'], "qualification_level": tf.get('qualification_level')} for tf in selected_tfs_data], ensure_ascii=False, indent=2)
    
    actions_json = json.dumps([{"description": item['description']} for item in selected_zun_elements.get('labor_actions', [])], ensure_ascii=False, indent=2)
    skills_json = json.dumps([{"description": item['description']} for item in selected_zun_elements.get('required_skills', [])], ensure_ascii=False, indent=2)
    knowledge_json = json.dumps([{"description": item['description']} for item in selected_zun_elements.get('required_knowledge', [])], ensure_ascii=False, indent=2)

    prompt = f"""
Ты - эксперт-методист по разработке образовательных программ.
Твоя задача - на основе предоставленных данных из Профессиональных Стандартов (Трудовых Функций и их элементов: Трудовых Действий, Необходимых Умений, Необходимых Знаний) сформулировать:
1.  Наименование Профессиональной Компетенции (ПК).
2.  Три формулировки Индикаторов Достижения Компетенции (ИПК): "Знает", "Умеет", "Владеет".

Строгие правила:
1.  Возвращай ответ ТОЛЬКО в JSON-формате, обернутый в ```json ... ```.
2.  НЕ добавляй никаких объяснений, преамбул, или других фраз вне JSON.
3.  Формулировка ПК ДОЛЖНА начинаться со слова "Способен". Она должна быть обобщающей для всех предоставленных ТФ.
4.  Формулировки ИПК "Знает", "Умеет", "Владеет" должны:
    *   Быть КОРОТКИМИ, емкими, ОБОБЩАЮЩИМИ основные идеи из соответствующих разделов (НЗ, НУ, ТД).
    *   НЕ использовать прямую конкатенацию всех пунктов. СИНТЕЗИРУЙ суть.
    *   "Знает": Обобщает Необходимые Знания.
    *   "Умеет": Обобщает Необходимые Умения.
    *   "Владеет": Обобщает Трудовые Действия.
5.  Если какой-то раздел ЗУН пуст, соответствующее поле в JSON должно быть пустой строкой.
6.  Все строки должны быть на русском языке.

JSON Schema:
```json
{{
    "pk_name": "STRING (Формулировка Профессиональной Компетенции)",
    "ipk_indicators": {{
        "znaet": "STRING (Обобщенная формулировка Знаний)",
        "umeet": "STRING (Обобщенная формулировка Умений)",
        "vladeet": "STRING (Обобщенная формулировка Владения/Действий)"
    }}
}}
```

Данные:
Трудовые Функции (TF):
{tfs_json}

Трудовые Действия (Labor Actions):
{actions_json}

Необходимые Умения (Required Skills):
{skills_json}

Необходимые Знания (Required Knowledge):
{knowledge_json}
"""
    return prompt

def _call_gemini_api(prompt_content: str) -> Dict[str, Any]:
    """Helper function to call the Gemini API and parse the response."""
    gemini_client = get_gemini_client() # Получаем клиент
    gemini_types = get_gemini_types() # Получаем types
    
    if not gemini_client:
        raise RuntimeError("Gemini API client is not configured.")

    logger.debug(f"Sending prompt to Gemini (first 500 chars):\n{prompt_content[:500]}...")
    
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=[prompt_content],
        config=gemini_types.GenerateContentConfig( # ИСПРАВЛЕНО: используем gemini_types
            temperature=0.0,
            max_output_tokens=8192 
        )
    )
    
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
    gemini_client = get_gemini_client() # Получаем клиент
    gemini_types = get_gemini_types() # Получаем types

    if not gemini_client:
        if not GOOGLE_GENAI_SDK_AVAILABLE:
            logger.error("Gemini SDK (google-genai) is not available.")
            raise RuntimeError("Gemini SDK (google-genai) is not available. Cannot parse FGOS with NLP.")
        # else: GOOGLE_AI_API_KEY check is done in get_gemini_client()
        else:
            logger.error("Gemini API client model was not initialized (likely due to configuration error).")
            raise RuntimeError("Gemini API client model was not initialized. Cannot parse FGOS with NLP.")

    try:
        prompt_content = _create_fgos_prompt(fgos_text)
        
        logger.debug(f"Sending prompt to Gemini (first 500 chars of prompt):\n{prompt_content[:500]}...")
        
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=[prompt_content],
            config=gemini_types.GenerateContentConfig( # ИСПРАВЛЕНО: используем gemini_types
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

# НОВАЯ ФУНКЦИЯ
def correct_pk_name_with_gemini(raw_phrase: str) -> Dict[str, str]:
    """
    Использует Gemini API для грамматической коррекции сырой фразы
    в формулировку Профессиональной Компетенции.
    """
    try:
        prompt = _create_pk_correction_prompt(raw_phrase)
        response_text = _call_gemini_api(prompt) # _call_gemini_api теперь возвращает сырой текст, если нет JSON
        
        # Если NLP вернет только текст, то просто используем его
        if isinstance(response_text, str):
            return {"corrected_name": response_text.strip()}
        # Если вдруг вернет JSON, который мы не ожидали (что маловероятно для такого промпта),
        # то можно добавить логику обработки. Пока будем считать, что он возвращает только текст.
        
        # Fallback for unexpected JSON response
        if isinstance(response_text, dict) and 'corrected_name' in response_text:
            return response_text # If Gemini decides to output JSON despite prompt
        
        # Fallback if text is not in 'response_text' (e.g. LLM decided to put it in a different key)
        if response_text is not None and isinstance(response_text, dict):
            logger.warning(f"Unexpected non-string response from PK correction prompt: {response_text}. Trying to extract text.")
            for key, value in response_text.items():
                if isinstance(value, str) and len(value) > 20: # Heuristic: assume it's the long text
                    return {"corrected_name": value.strip()}

        logger.error(f"Gemini did not return expected string for PK name correction. Raw response: {response_text}")
        raise ValueError("NLP не смог сгенерировать корректное название ПК.")
    except Exception as e:
        logger.error(f"Error calling Gemini for PK name correction: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка при коррекции названия ПК через NLP: {e}")

# НОВАЯ ФУНКЦИЯ
def generate_pk_ipk_with_gemini(
    selected_tfs_data: List[Dict],
    selected_zun_elements: Dict[str, List[Dict]]
) -> Dict[str, Any]:
    """
    Использует Gemini API для генерации формулировок ПК и ИПК на основе
    выбранных Трудовых Функций и ЗУН-элементов.
    """
    try:
        prompt = _create_pk_ipk_generation_prompt(selected_tfs_data, selected_zun_elements)
        parsed_data = _call_gemini_api(prompt)
        
        # Basic validation of the expected JSON structure
        if not isinstance(parsed_data, dict) or \
           'pk_name' not in parsed_data or \
           not isinstance(parsed_data.get('ipk_indicators'), dict) or \
           'znaet' not in parsed_data['ipk_indicators'] or \
           'umeet' not in parsed_data['ipk_indicators'] or \
           'vladeet' not in parsed_data['ipk_indicators']:
            logger.error(f"Generated JSON from Gemini has unexpected structure: {parsed_data}")
            raise ValueError("Сгенерированный JSON имеет неверную структуру.")
        
        # Clean up formulations (remove extra spaces, newlines)
        if isinstance(parsed_data['pk_name'], str):
            parsed_data['pk_name'] = re.sub(r'\s+', ' ', parsed_data['pk_name']).strip()
        
        for key in ['znaet', 'umeet', 'vladeet']:
            if isinstance(parsed_data['ipk_indicators'].get(key), str):
                parsed_data['ipk_indicators'][key] = re.sub(r'\s+', ' ', parsed_data['ipk_indicators'][key]).strip()
        
        logger.info("Successfully generated PK/IPK formulations using Gemini API.")
        return parsed_data
    except Exception as e:
        logger.error(f"Error generating PK/IPK with Gemini API: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка при генерации ПК/ИПК через NLP: {e}")
