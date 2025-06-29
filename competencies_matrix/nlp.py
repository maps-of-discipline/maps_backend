import json
import logging
import re
from typing import Dict, List, Any

# --- ИМПОРТЫ КЛИЕНТОВ LLM ---
try:
    from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    logging.warning("openai package not found. Providers 'local' and 'klusterai' will be unavailable.")
    OpenAI, APIConnectionError, RateLimitError, APIStatusError = None, None, None, None
    OPENAI_SDK_AVAILABLE = False

# Импорт конфигурации и утилит
from config import (
    LLM_PROVIDER,
    LOCAL_LLM_BASE_URL, LOCAL_LLM_API_KEY, LOCAL_LLM_MODEL_NAME,
    KLUDESTER_AI_API_KEY, KLUDESTER_AI_BASE_URL, KLUDESTER_AI_MODEL_NAME
)
from .parsing_utils import parse_date_string

logger = logging.getLogger(__name__)

# --- ГЛОБАЛЬНЫЕ КЛИЕНТЫ (ленивая инициализация) ---
_openai_compatible_clients: Dict[str, Any] = {} # Словарь для хранения клиентов по base_url

def _get_openai_compatible_client(base_url: str, api_key: str):
    global _openai_compatible_clients
    if not OPENAI_SDK_AVAILABLE:
        raise RuntimeError("OpenAI SDK is not installed. Please run 'pip install openai'.")
    
    if base_url not in _openai_compatible_clients:
        try:
            _openai_compatible_clients[base_url] = OpenAI(base_url=base_url, api_key=api_key)
            logger.info(f"OpenAI-compatible client configured for base URL: {base_url}.")
        except Exception as e:
            logger.error(f"Failed to configure OpenAI-compatible client for {base_url}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize OpenAI-compatible client: {e}")
    return _openai_compatible_clients[base_url]

def _call_llm_api(prompt_content: str, model_name: str, temperature: float = 0.0, max_tokens: int = 4000) -> Dict[str, Any]:
    """Универсальная функция для вызова LLM API с логированием токенов и надежной обработкой ошибок."""
    response_text, prompt_tokens, completion_tokens = None, 0, 0
    logger.debug(f"Sending prompt to LLM ({LLM_PROVIDER}, model: {model_name}, first 500 chars):\n{prompt_content[:500]}...")

    if LLM_PROVIDER in ['local', 'klusterai']:
        try:
            base_url = LOCAL_LLM_BASE_URL if LLM_PROVIDER == 'local' else KLUDESTER_AI_BASE_URL
            api_key = LOCAL_LLM_API_KEY if LLM_PROVIDER == 'local' else KLUDESTER_AI_API_KEY
            client = _get_openai_compatible_client(base_url, api_key)
            messages = [{"role": "user", "content": prompt_content}]
            
            completion = client.chat.completions.create(
                model=model_name, messages=messages, temperature=temperature, max_tokens=max_tokens
            )
            response_text = completion.choices[0].message.content
            if completion.usage:
                prompt_tokens = completion.usage.prompt_tokens
                completion_tokens = completion.usage.completion_tokens
        except (APIConnectionError, RateLimitError, APIStatusError, RuntimeError) as e:
            logger.error(f"LLM API error ({LLM_PROVIDER}): {e}", exc_info=True)
            raise RuntimeError(f"Ошибка LLM API ({LLM_PROVIDER}): {e}")
    else:
        raise RuntimeError(f"LLM_PROVIDER '{LLM_PROVIDER}' is not supported. Please set LLM_PROVIDER to 'local' or 'klusterai'.")

    logger.info(f"LLM Token Usage: Prompt Tokens = {prompt_tokens}, Completion Tokens = {completion_tokens}")
    # logger.info(f"LLM Raw Response:\n{response_text}")

    if not response_text:
        raise ValueError("LLM response text is empty.")

    json_match = re.search(r'```\s*json\s*(.*?)\s*```', response_text, re.DOTALL | re.IGNORECASE)
    if json_match:
        return json.loads(json_match.group(1).strip())
    
    logger.warning("LLM response did not contain a JSON markdown block. Attempting to parse raw response.")
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as err:
        raise ValueError(f"LLM response was not valid JSON. Error: {err}. Full response:\n{response_text}")

# --- Промпты ---

def _create_fgos_prompt(fgos_text: str) -> str:
    """
    Создает промпт для LLM для извлечения структурированных данных из текста ФГОС.
    Промпт очень детально описывает желаемую JSON-структуру и правила извлечения.
    """
    prompt = f"""
Ты - эксперт-академический ассистент, извлекающий структурированную информацию из документов Федеральных государственных образовательных стандартов (ФГОС ВО).
Твоя задача - спарсить предоставленный текст документа ФГОС ВО в формате PDF и извлечь конкретные, структурированные данные в формате JSON.
Строго придерживайся указанной JSON-схемы.

**НЕ ВКЛЮЧАЙ** никакого другого текста, объяснений или разметки Markdown за пределами блока JSON.
**НЕ ВКЛЮЧАЙ** никаких разговорных фраз, таких как "Вот вывод JSON:".
**НЕ ОПУСКАЙ** никакие поля из требуемой JSON-структуры. Если значение поля не может быть найдено, установи его в `null` (для чисел/строк/дат) или `[]` (для списков), или `false` (для булевых значений). `uk_competencies.category_name` должен идти перед `uk_competencies.name`, что означает, что каждая компетенция должна иметь название категории.
**УБЕДИСЬ**, что все форматы дат - "YYYY-MM-DD".
**УБЕДИСЬ**, что все строковые значения правильно экранированы для JSON.
**УБЕДИСЬ**, что вывод является **ТОЛЬКО** блоком JSON, обернутым в ```json ... ```.

JSON должен быть отформатирован следующим образом:

```json
{{
    "metadata": {{
        "order_number": "STRING",
        "order_date": "YYYY-MM-DD",
        "direction_code": "STRING",
        "direction_name": "STRING",
        "education_level": "STRING",
        "generation": "3++"
    }},
    "uk_competencies": [
        {{
            "code": "STRING",
            "category_name": "STRING",
            "name": "STRING"
        }}
    ],
    "opk_competencies": [
        {{
            "code": "STRING",
            "name": "STRING"
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

- `code`: Извлеки точный код (например, "26.001", "40.042").
- `name`: Извлеки только *короткое, чистое название* Профессионального Стандарта, без юридических ссылок, регистрационных номеров или дат. Только основное название, например "Специалист по производству".
- `approval_date`: Извлеки дату утверждения *самого Профессионального Стандарта*, если она явно указана в тексте рекомендации для этого конкретного ПС. Если не найдена, установи в `null`. Формат "YYYY-MM-DD".

Вот текст документа ФГОС ВО для парсинга:

{fgos_text}
"""
    return prompt

def _create_uk_indicators_disposition_prompt(disposition_text: str, education_level: str) -> str:
    """
    Создает промпт для LLM для извлечения структурированных данных
    из текста Распоряжения об установлении индикаторов универсальных компетенций,
    с учетом указанного уровня образования.
    """
    prompt = f"""
Ты - эксперт-академический ассистент, извлекающий структурированную информацию из официальных распоряжений об Индикаторах Универсальных Компетенций (ИУК).
Твоя задача - спарсить предоставленный текст документа распоряжения и извлечь конкретные, структурированные данные в формате JSON.
Строго придерживайся указанной JSON-схемы.

Важно: Проанализируй весь документ, но возвращай данные ТОЛЬКО по универсальным компетенциям и их индикаторам, которые относятся к указанному уровню образования: '{education_level}'.
Если распоряжение определяет индикаторы для нескольких уровней образования (например, таблица для 'бакалавриат' и другая для 'специалитет'), ты должен вернуть данные ТОЛЬКО для раздела, соответствующего '{education_level}'.

**НЕ ВКЛЮЧАЙ** никакого другого текста, объяснений или разметки Markdown за пределами блока JSON.
**НЕ ОПУСКАЙ** никакие поля из требуемой JSON-структуры. Если значение поля не может быть найдено, установи его в `null` (для чисел/строк/дат) или `[]` (для списков).
**УБЕДИСЬ**, что все форматы дат - "YYYY-MM-DD".
**УБЕДИСЬ**, что все строковые значения правильно экранированы для JSON.
**УБЕДИСЬ**, что вывод является **ТОЛЬКО** блоком JSON, обернутым в ```json ... ```.

JSON должен быть отформатирован следующим образом:

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

**Правила извлечения:**
- `disposition_metadata.number`: Извлеки номер распоряжения (например, "505-Р").
- `disposition_metadata.date`: Извлеки дату распоряжения (например, "30.05.2023"). Формат "YYYY-MM-DD".
- `disposition_metadata.title`: Извлеки полное название распоряжения (например, "Об установлении индикаторов достижения универсальных компетенций").
- `uk_competencies_with_indicators.code`: Извлеки точный код УК (например, "УК-1").
- `uk_competencies_with_indicators.name`: Извлеки полное название УК.
- `uk_competencies_with_indicators.category_name`: Извлеки название категории УК (например, "Системное и критическое мышление", "Коммуникация"). Если явно не указано, попробуй вывести из типичных категорий, или установи в `null`.
- `uk_competencies_with_indicators.indicators.code`: Извлеки точный код индикатора (например, "ИУК-1.1", "ИУК-2.3").
- `uk_competencies_with_indicators.indicators.formulation`: Извлеки полную формулировку индикатора.

Вот текст документа распоряжения для парсинга:

{disposition_text}
"""
    return prompt

def _create_pk_correction_prompt(raw_phrase: str) -> str:
    """
    Создает промпт для LLM для грамматической коррекции сырой фразы
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
    Создает промпт для LLM для генерации формулировок ПК и ИПК на основе
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

# --- Обновленные публичные функции ---
def parse_fgos_with_llm(fgos_text: str) -> Dict[str, Any]:
    """Использует сконфигурированный LLM для парсинга ФГОС."""
    model_name = KLUDESTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
    prompt = _create_fgos_prompt(fgos_text)
    parsed_data = _call_llm_api(prompt, model_name=model_name)
    if parsed_data.get('metadata'):
        parsed_data['metadata']['order_date'] = parse_date_string(parsed_data['metadata'].get('order_date'))
    if parsed_data.get('recommended_ps'):
        for ps in parsed_data['recommended_ps']:
            ps['approval_date'] = parse_date_string(ps.get('approval_date'))
    return parsed_data

def parse_uk_indicators_disposition_with_llm(disposition_text: str, education_level: str) -> Dict[str, Any]:
    """Использует сконфигурированный LLM для парсинга Распоряжения."""
    model_name = KLUDESTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
    prompt = _create_uk_indicators_disposition_prompt(disposition_text, education_level)
    parsed_data = _call_llm_api(prompt, model_name=model_name)

    # Валидация и очистка данных, как в вашем предыдущем коде
    if 'disposition_metadata' in parsed_data and isinstance(parsed_data['disposition_metadata'], dict):
        date_val = parsed_data['disposition_metadata'].get('date')
        parsed_data['disposition_metadata']['date'] = parse_date_string(date_val)
    
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
    return parsed_data


def correct_pk_name_with_llm(raw_phrase: str) -> Dict[str, str]:
    """Использует сконфигурированный LLM для коррекции названия ПК."""
    model_name = KLUDESTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
    prompt = _create_pk_correction_prompt(raw_phrase)
    response_data = _call_llm_api(prompt, model_name=model_name)
    
    # Валидация и очистка, как в вашем предыдущем коде
    if isinstance(response_data, str):
        return {"corrected_name": response_data.strip()}
    
    if isinstance(response_data, dict) and 'corrected_name' in response_data:
        return response_data
    
    if response_data is not None and isinstance(response_data, dict):
        logger.warning(f"Unexpected non-string response from PK correction prompt: {response_data}. Trying to extract text.")
        for key, value in response_data.items():
            if isinstance(value, str) and len(value) > 20: # Эвристика: ищем длинную строку, которая может быть ответом
                return {"corrected_name": value.strip()}

    logger.error(f"LLM did not return expected string for PK name correction. Raw response: {response_data}")
    raise ValueError("NLP не смог сгенерировать корректное название ПК.")

def generate_pk_ipk_with_llm(selected_tfs_data: List[Dict], selected_zun_elements: Dict[str, List[Dict]]) -> Dict[str, Any]:
    """Использует сконфигурированный LLM для генерации ПК/ИПК."""
    model_name = KLUDESTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
    prompt = _create_pk_ipk_generation_prompt(selected_tfs_data, selected_zun_elements)
    parsed_data = _call_llm_api(prompt, model_name=model_name)
    
    # Валидация и очистка, как в вашем предыдущем коде
    if not isinstance(parsed_data, dict) or \
       'pk_name' not in parsed_data or \
       not isinstance(parsed_data.get('ipk_indicators'), dict) or \
       'znaet' not in parsed_data['ipk_indicators'] or \
       'umeet' not in parsed_data['ipk_indicators'] or \
       'vladeet' not in parsed_data['ipk_indicators']:
        logger.error(f"Generated JSON from LLM has unexpected structure: {parsed_data}")
        raise ValueError("Сгенерированный JSON имеет неверную структуру.")
    
    if isinstance(parsed_data['pk_name'], str):
        parsed_data['pk_name'] = re.sub(r'\s+', ' ', parsed_data['pk_name']).strip()
    
    for key in ['znaet', 'umeet', 'vladeet']:
        if isinstance(parsed_data['ipk_indicators'].get(key), str):
            parsed_data['ipk_indicators'][key] = re.sub(r'\s+', ' ', parsed_data['ipk_indicators'][key]).strip()
    
    return parsed_data