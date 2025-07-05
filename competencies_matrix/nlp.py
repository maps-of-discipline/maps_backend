# filepath: competencies_matrix/nlp.py
import json
import logging
import re
from typing import Dict, List, Any, Optional

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
    KLUSTER_AI_API_KEY, KLUSTER_AI_BASE_URL, KLUSTER_AI_MODEL_NAME
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
            base_url = LOCAL_LLM_BASE_URL if LLM_PROVIDER == 'local' else KLUSTER_AI_BASE_URL
            api_key = LOCAL_LLM_API_KEY if LLM_PROVIDER == 'local' else KLUSTER_AI_API_KEY
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
}},
    "warning": false,
    "message": null
}}
```

**Дополнительные правила и обработка ошибок:**
- Если документ не кажется полным ФГОС 3++ документом (например, отсутствуют разделы с метаданными, УК, ОПК или рекомендованными ПС, или содержание кажется нерелевантным), установи `"warning": true` и добавь соответствующее сообщение в поле `"message"`.
- Сообщение в `"message"` должно быть на русском языке и объяснять, почему документ может быть неполным или недействительным ФГОС 3++ (например, "Документ не содержит всех ожидаемых разделов ФГОС 3++" или "Не удалось извлечь универсальные компетенции.").
- Если все данные извлечены успешно и документ кажется полным, установи `"warning": false` и `"message": null`.

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
    batch_tfs_data: List[Dict]
) -> str:
    """
    Создает промпт для LLM для пакетной генерации формулировок ПК и ИПК на основе
    списка Трудовых Функций и их элементов (ТД, НУ, НЗ).
    Каждый элемент в `batch_tfs_data` должен содержать:
    - 'unique_tf_id': уникальный идентификатор ТФ, чтобы сопоставить результат
    - 'tf_name': название ТФ
    - 'labor_actions': список описаний ТД
    - 'required_skills': список описаний НУ
    - 'required_knowledge': список описаний НЗ
    """
    # Подготавливаем данные для LLM, чтобы они были максимально чистыми и структурированными
    formatted_tfs = []
    for tf_data in batch_tfs_data:
        tf_dict = {
            "unique_tf_id": tf_data.get('unique_tf_id'), # Важно для сопоставления ответа
            "tf_name": tf_data.get('tf_name'),
            "labor_actions": [a.get('description') for a in tf_data.get('labor_actions', []) if a.get('description')],
            "required_skills": [s.get('description') for s in tf_data.get('required_skills', []) if s.get('description')],
            "required_knowledge": [k.get('description') for k in tf_data.get('required_knowledge', []) if k.get('description')],
        }
        formatted_tfs.append(tf_dict)

    tfs_json_str = json.dumps(formatted_tfs, ensure_ascii=False, indent=2)

    prompt = f"""
Ты - эксперт-методист по разработке образовательных программ.
Твоя задача - на основе предоставленного списка Трудовых Функций (ТФ) и их элементов
(Трудовых Действий, Необходимых Умений, Необходимых Знаний) сформулировать для КАЖДОЙ ТФ:
1.  Наименование Профессиональной Компетенции (ПК).
2.  Три формулировки Индикаторов Достижения Компетенции (ИПК): "Знает", "Умеет", "Владеет".

Строгие правила:
1.  Возвращай ответ ТОЛЬКО в JSON-формате, обернутый в ```json ... ```.
2.  НЕ добавляй никаких объяснений, преамбул, или других фраз вне JSON.
3.  Выходной JSON ДОЛЖЕН быть СПИСКОМ объектов, где каждый объект соответствует одной входной ТФ.
4.  Каждый выходной объект должен содержать `unique_tf_id` из соответствующей входной ТФ. Это критически важно для сопоставления.
5.  Формулировка ПК ДОЛЖНА начинаться со слова "Способен". Она должна быть обобщающей для предоставленной ТФ.
6.  Формулировки ИПК "Знает", "Умеет", "Владеет" должны:
    *   Быть КОРОТКИМИ, емкими, ОБОБЩАЮЩИМИ основные идеи из соответствующих разделов (НЗ, НУ, ТД).
    *   НЕ использовать прямую конкатенацию всех пунктов. СИНТЕЗИРУЙ суть.
    *   "Знает": Обобщает Необходимые Знания из `required_knowledge`.
    *   "Умеет": Обобщает Необходимые Умения из `required_skills`.
    *   "Владеет": Обобщает Трудовые Действия из `labor_actions`.
7.  Если какой-то раздел ЗУН пуст для ТФ, соответствующее поле в JSON должно быть пустой строкой.
8.  Все строки должны быть на русском языке.

JSON Schema для каждого элемента в выходном списке:
```json
[
    {{
        "unique_tf_id": "STRING (Идентификатор ТФ из входа)",
        "pk_name": "STRING (Формулировка Профессиональной Компетенции)",
        "ipk_indicators": {{
            "znaet": "STRING (Обобщенная формулировка Знаний)",
            "umeet": "STRING (Обобщенная формулировка Умений)",
            "vladeet": "STRING (Обобщенная формулировка Владения/Действий)"
        }}
    }}
]
```

Данные для генерации (список Трудовых Функций):
{tfs_json_str}
"""
    return prompt

# --- Обновленные публичные функции ---
def parse_fgos_with_llm(fgos_text: str) -> Dict[str, Any]:
    """Использует сконфигурированный LLM для парсинга ФГОС."""
    model_name = KLUSTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
    prompt = _create_fgos_prompt(fgos_text)
    parsed_data = _call_llm_api(prompt, model_name=model_name)

    # Инициализация полей warning и message, если они отсутствуют (хотя промпт должен их включать)
    parsed_data.setdefault('warning', False)
    parsed_data.setdefault('message', None)

    # Валидация и очистка данных
    if parsed_data.get('metadata'):
        parsed_data['metadata']['order_date'] = parse_date_string(parsed_data['metadata'].get('order_date'))
    
    if parsed_data.get('recommended_ps'):
        for ps in parsed_data['recommended_ps']:
            ps['approval_date'] = parse_date_string(ps.get('approval_date'))

    # Проверка на полноту данных для установки предупреждения
    warning_messages = []
    if not parsed_data.get('metadata') or not all(parsed_data['metadata'].get(k) for k in ['order_number', 'order_date', 'direction_code', 'education_level']):
        warning_messages.append("Не удалось извлечь основные метаданные ФГОС (номер, дата, код направления, уровень образования).")
    if not parsed_data.get('uk_competencies'):
        warning_messages.append("Не удалось извлечь универсальные компетенции (УК).")
    if not parsed_data.get('opk_competencies'):
        warning_messages.append("Не удалось извлечь общепрофессиональные компетенции (ОПК).")
    if not parsed_data.get('recommended_ps'):
        warning_messages.append("Не удалось извлечь рекомендованные профессиональные стандарты.")

    if warning_messages:
        parsed_data['warning'] = True
        parsed_data['message'] = "Документ может быть неполным или недействительным ФГОС 3++: " + "; ".join(warning_messages)
    
    return parsed_data

def parse_uk_indicators_disposition_with_llm(disposition_text: str, education_level: str) -> Dict[str, Any]:
    """Использует сконфигурированный LLM для парсинга Распоряжения."""
    model_name = KLUSTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
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
    model_name = KLUSTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
    prompt = _create_pk_correction_prompt(raw_phrase)
    # Максимальное количество токенов для коррекции обычно меньше, чем для генерации.
    # Если название длинное, лучше дать побольше. Например, 50-100.
    response_data = _call_llm_api(prompt, model_name=model_name, max_tokens=100)
    
    # Валидация и очистка, как в вашем предыдущем коде
    if isinstance(response_data, str):
        return {"corrected_name": response_data.strip()}
    
    if isinstance(response_data, dict) and 'corrected_name' in response_data:
        return response_data
    
    if response_data is not None and isinstance(response_data, dict):
        logger.warning(f"Unexpected non-string response from PK correction prompt: {response_data}. Trying to extract text.")
        for key, value in response_data.items():
            if isinstance(value, str) and (len(value) > 20 or (key == 'corrected_name' and len(value) > 0)):
                return {"corrected_name": value.strip()}

    logger.error(f"LLM did not return expected string for PK name correction. Raw response: {response_data}")
    raise ValueError("NLP не смог сгенерировать корректное название ПК.")

def generate_pk_ipk_with_llm(batch_tfs_data: List[Dict]) -> List[Dict]:
    """
    (ИЗМЕНЕНО) Использует сконфигурированный LLM для пакетной генерации ПК/ИПК.
    Принимает список словарей, каждый из которых представляет одну ТФ с ее элементами ЗУН.
    Возвращает список сгенерированных результатов, сопоставленных по unique_tf_id.
    """
    model_name = KLUSTER_AI_MODEL_NAME if LLM_PROVIDER == 'klusterai' else LOCAL_LLM_MODEL_NAME
    prompt = _create_pk_ipk_generation_prompt(batch_tfs_data)
    
    # Увеличиваем max_tokens, так как ожидаем больше выходных данных
    # Каждый PK/IPK генерирует ~150 токенов, 10 ТФ -> 1500 токенов
    max_tokens_for_batch = max(2000, len(batch_tfs_data) * 200) # Динамически настраиваем
    
    generated_results = _call_llm_api(prompt, model_name=model_name, max_tokens=max_tokens_for_batch)
    
    if not isinstance(generated_results, list):
        logger.error(f"Generated data is not a list: {generated_results}")
        raise ValueError("NLP вернул неверный формат ответа для пакетной генерации (ожидается список).")

    final_parsed_results = []
    for item in generated_results:
        # Валидация и очистка каждого элемента в пакете
        if not isinstance(item, dict) or \
           'unique_tf_id' not in item or \
           'pk_name' not in item or \
           not isinstance(item.get('ipk_indicators'), dict) or \
           'znaet' not in item['ipk_indicators'] or \
           'umeet' not in item['ipk_indicators'] or \
           'vladeet' not in item['ipk_indicators']:
            logger.warning(f"Skipping malformed generated item: {item}")
            continue # Пропускаем некорректные элементы
        
        # Очистка строк
        item['pk_name'] = re.sub(r'\s+', ' ', item['pk_name']).strip()
        for key in ['znaet', 'umeet', 'vladeet']:
            item['ipk_indicators'][key] = re.sub(r'\s+', ' ', item['ipk_indicators'].get(key, '')).strip()
        
        final_parsed_results.append(item)
    
    return final_parsed_results