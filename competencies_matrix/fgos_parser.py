# competencies_matrix/fgos_parser.py
import io
import re
import datetime
from typing import Dict, List, Any, Optional
from pdfminer.high_level import extract_text
import logging
import traceback # Для вывода traceback в случае ошибки

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Установите уровень логирования: DEBUG, INFO, WARNING, ERROR

def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Парсит содержимое PDF файла ФГОС ВО (для формата 3++)
    и извлекает структурированные данные.

    Args:
        file_bytes: Содержимое PDF файла в байтах.
        filename: Имя файла (для логирования/инфо).

    Returns:
        Dict[str, Any]: Словарь с извлеченными данными или raise ValueError/Exception.
                        Структура: {
                            'metadata': { 'order_number', 'order_date', 'direction_code', 'direction_name', 'education_level', 'generation', 'order_info' },
                            'uk_competencies': [{ 'code', 'name', 'indicators': [{'code', 'formulation'}] }],
                            'opk_competencies': [{ 'code', 'name', 'indicators': [{'code', 'formulation'}] }],
                            'recommended_ps_codes': [...],
                            'raw_text': '...' # Полный извлеченный текст
                        }
    """
    logger.info(f"Starting PDF parsing for file: {filename}")
    text = ""
    try:
        # Извлекаем весь текст из PDF
        text = extract_text(io.BytesIO(file_bytes))
        logger.debug(f"Extracted raw text ({len(text)} characters). Preview: {text[:1000]}...")

        # --- Очистка текста: Удаляем переносы строк, дефисы, лишние пробелы ---
        # Удаляем переносы строк в середине слов, дефисы
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
        text = text.replace('-\n', '') # Удаляем висячие дефисы
        text = re.sub(r'\s*\n\s*', '\n', text) # Схлопываем пробелы вокруг переносов строк
        text = re.sub(r'\n{2,}', '\n\n', text) # Схлопываем множественные переносы строк до двух
        text = re.sub(r'[ \t]+', ' ', text).strip() # Удаляем лишние пробелы и табуляции

        logger.debug(f"Cleaned text ({len(text)} characters). Preview: {text[:1000]}...")

        parsed_data: Dict[str, Any] = {
            'metadata': {},
            'uk_competencies': [],
            'opk_competencies': [],
            'recommended_ps_codes': [],
            'raw_text': text # Сохраняем полный текст для отладки, если нужно
        }

        # --- 1. Извлечение метаданных ---
        # Ищем "Федеральный государственный образовательный стандарт высшего образования..."
        # Делаем паттерны даты и номера приказа более гибкими
        metadata_pattern = re.compile(
            r'Федеральный государственный образовательный стандарт высшего образования.*?$' # Начало заголовка
            r'(.*?)' # Текст между заголовком и приказом
            r'(УТВЕРЖДЕН\s+приказом\s+Министерства\s+образования\s+и\s+науки.*?$\s+' # Начало блока УТВЕРЖДЕН
            r'от\s+(' # Группа 1: Дата приказа (делаем гибкой)
              r'(\d{2}\.\d{2}\.\d{4})|' # Вариант 1: DD.MM.YYYY
              r'(\d{1,2}\s+\S+\s+\d{4}\s+г\.)' # Вариант 2: D MMMM YYYY г. (например, 19 сентября 2017 г.)
            r')\s+№\s+(' # Группа 4: Номер приказа (делаем гибким)
              r'(\d+)|' # Вариант 1: NNN
              r'N\s+(\d+)' # Вариант 2: N NNN (например, N 929)
            r'))' # Конец блока УТВЕРЖДЕН (Группа 5)
            r'(.*?)' # Текст до направления подготовки
            r'(по\s+направлению\s+подготовки\s+(\d{2}\.\d{2}\.\d{2})\s+(.*?))' # Группа 8: Направление (код + название)
            r'(.*?)' # Текст до уровня образования
            r'(уровень\s+(бакалавриата|магистратуры|специалитета))', # Группа 12: Уровень
            re.DOTALL | re.IGNORECASE
        )
        metadata_match = metadata_pattern.search(text)

        if metadata_match:
            parsed_data['metadata']['order_info'] = metadata_match.group(5).strip()
            # Извлекаем дату из группы 1 (подгруппы 2 или 3)
            date_str = metadata_match.group(2)
            parsed_data['metadata']['order_date'] = date_str # Сохраняем как строку
            # Извлекаем номер из группы 4 (подгруппы 5 или 6)
            number_str = metadata_match.group(4)
            parsed_data['metadata']['order_number'] = number_str # Сохраняем как строку

            parsed_data['metadata']['direction_code'] = metadata_match.group(9)
            parsed_data['metadata']['direction_name'] = metadata_match.group(10).strip()
            parsed_data['metadata']['education_level'] = metadata_match.group(13).strip()

            # Попытка определить поколение (требует эвристики)
            if re.search(r'ФГОС ВО 3\+\+', filename, re.IGNORECASE) or re.search(r'ФГОС ВО поколения 3\+\+', text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3++'
            elif re.search(r'ФГОС ВО 3\+', filename, re.IGNORECASE) or re.search(r'ФГОС ВО поколения 3\+', text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3+'
            else:
                 parsed_data['metadata']['generation'] = 'не определено' # Требует ручной верификации

            logger.info("Metadata extracted successfully.")
            logger.debug(f"Extracted metadata: {parsed_data['metadata']}")

        else:
             logger.warning("Metadata pattern did not match.")


        # --- 2. Извлечение компетенций и индикаторов ---
        # Ищем раздел "III. Требования к результатам освоения..."
        # А затем подразделы с таблицами компетенций (УК, ОПК)
        # Делаем поиск раздела III более гибким и захватываем его содержимое до раздела IV или конца
        competencies_section_match = re.search(
            r'III\.\s+Требования\s+к\s+результатам\s+освоения\s+программы.*?$(.*?)' # Содержание раздела III
            r'(^IV\.\s+Требования\s+к\s+условиям\s+реализации\s+программы|\Z)', # До следующего раздела или конца файла
            text, re.DOTALL | re.MULTILINE
        )

        comp_section_text = ""
        if competencies_section_match:
            comp_section_text = competencies_section_match.group(1)
            logger.debug(f"Section III text extracted ({len(comp_section_text)} characters). Preview: {comp_section_text[:500]}...")

            # Ищем блоки УК и ОПК внутри раздела III (делаем паттерны заголовков более гибкими)
            uk_block_match = re.search(
                r'Универсальные\s+компетенци(?:и|я).*?$(.*?)' # Содержание блока УК
                r'(Общепрофессиональные\s+компетенци(?:и|я)|Профессиональные\s+компетенци(?:и|я)|\Z)', # До следующего блока или конца раздела
                comp_section_text, re.DOTALL | re.MULTILINE | re.IGNORECASE # Игнорируем регистр
            )

            if uk_block_match:
                uk_text = uk_block_match.group(1)
                parsed_data['uk_competencies'] = parse_competency_block(uk_text, 'УК')
                logger.info(f"Found and parsed {len(parsed_data['uk_competencies'])} УК competencies.")
                logger.debug(f"UK data: {parsed_data['uk_competencies']}")
            else:
                 logger.warning("UK block pattern did not match in Section III.")

            opk_block_match = re.search(
                r'Общепрофессиональные\s+компетенци(?:и|я).*?$(.*?)' # Содержание блока ОПК
                r'(Профессиональные\s+компетенци(?:и|я)|\Z)', # До следующего блока или конца раздела
                comp_section_text, re.DOTALL | re.MULTILINE | re.IGNORECASE
            )

            if opk_block_match:
                opk_text = opk_block_match.group(1)
                parsed_data['opk_competencies'] = parse_competency_block(opk_text, 'ОПК')
                logger.info(f"Found and parsed {len(parsed_data['opk_competencies'])} ОПК competencies.")
                logger.debug(f"OPK data: {parsed_data['opk_competencies']}")
            else:
                 logger.warning("ОПК block pattern did not match in Section III.")


            # Если УК и ОПК не были найдены в отдельных блоках, пробуем парсить весь раздел III
            if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies'] and comp_section_text:
                 logger.warning("УК/ОПК blocks not found. Attempting to parse entire section III as combined list.")
                 all_comp_list = parse_competency_block(comp_section_text, 'УК|ОПК') # Ищем и УК, и ОПК
                 parsed_data['uk_competencies'] = [c for c in all_comp_list if c.get('code', '').startswith('УК')]
                 parsed_data['opk_competencies'] = [c for c in all_comp_list if c.get('code', '').startswith('ОПК')]
                 logger.info(f"Parsed combined list. Found {len(parsed_data['uk_competencies'])} УК and {len(parsed_data['opk_competencies'])} ОПК.")
                 logger.debug(f"Combined УК/ОПК data: {all_comp_list}")
        else:
             logger.warning("Section III pattern did not match in the text.")


        # --- 3. Извлечение списка рекомендованных ПС ---
        # Ищем в конце документа или в приложении
        # Делаем поиск более гибким, ищем коды XX.XXX после раздела III или в конце документа
        ps_search_area = text
        if competencies_section_match:
             # Если раздел III найден, ищем ПС после него
             ps_search_area = text[competencies_section_match.end():]
             logger.debug(f"Searching for PS codes after section III. Search area preview: {ps_search_area[:500]}...")
        else:
             # Иначе ищем во всем тексте (менее точно)
             logger.warning("Section III not found, searching for PS codes in the entire text.")


        # Ищем коды ПС в формате XX.XXX (например, 06.001)
        ps_codes = re.findall(r'\b(\d{2}\.\d{3})\b', ps_search_area)
        parsed_data['recommended_ps_codes'] = list(set(ps_codes)) # Убираем дубликаты
        logger.info(f"Found {len(parsed_data['recommended_ps_codes'])} potential recommended PS codes.")
        logger.debug(f"Found PS codes: {parsed_data['recommended_ps_codes']}")


        # --- Финальная проверка ---
        if not parsed_data['metadata']:
             raise ValueError("Не удалось извлечь основные метаданные ФГОС.")
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             raise ValueError("Не удалось извлечь УК и ОПК компетенции.")

        logger.info(f"PDF parsing for {filename} finished successfully.")
        return parsed_data

    except ValueError as e: # Ловим специфичные ошибки парсера
        logger.error(f"FGOS Parsing ValueError for {filename}: {e}")
        # traceback.print_exc()
        raise e # Перевыбрасываем ошибку для обработки вызывающей функцией
    except Exception as e:
        logger.error(f"Unexpected error during FGOS parsing for {filename}: {e}", exc_info=True)
        # traceback.print_exc()
        raise Exception(f"Неожиданная ошибка при парсинге файла ФГОС: {e}")


def parse_competency_block(text: str, comp_type_prefix: str) -> List[Dict[str, Any]]:
    """
    Парсит текст, содержащий список компетенций и индикаторов,
    используя регулярные выражения.
    Адаптировано для более гибкого поиска индикаторов.

    Args:
        text: Текст для парсинга.
        comp_type_prefix: Префикс типа компетенции ('УК', 'ОПК', 'ПК' или 'УК|ОПК').

    Returns:
        List[Dict[str, Any]]: Список словарей компетенций с их индикаторами.
                               Структура: [{ 'code', 'name', 'indicators': [{'code', 'formulation'}] }]
    """
    competencies: List[Dict[str, Any]] = []

    # Паттерн для поиска компетенции: начало строки, префикс, номер, точка/скобка/пробел, формулировка
    # Захватываем текст до начала следующей компетенции или конца блока
    comp_pattern = re.compile(
        rf'^\s*({comp_type_prefix})[\s-]*(\d+)\.?[\s)]*(.*?)$' # Группа 1: Префикс, Группа 2: Номер, Группа 3: Формулировка компетенции
        r'(.*?)' # Группа 4: Текст после формулировки компетенции (предполагаем, это индикаторы)
        rf'(?=\s*({comp_type_prefix})[\s-]*\d+\.?[\s)]*|\Z)', # Positive lookahead: до начала след. компетенции или конца текста
        re.DOTALL | re.MULTILINE | re.IGNORECASE
    )

    matches = comp_pattern.finditer(text)
    logger.debug(f"parse_competency_block: Found {len(list(comp_pattern.finditer(text)))} potential competencies with prefix '{comp_type_prefix}'.")


    for match in matches:
        comp_prefix_found = match.group(1)
        comp_number = match.group(2)
        comp_code = f"{comp_prefix_found.upper()}-{comp_number}" # Используем верхний регистр для консистентности
        comp_name = match.group(3).strip()
        indicators_text = match.group(4).strip()

        logger.debug(f"  - Found competency: {comp_code}, Name: '{comp_name[:50]}...', Indicators text length: {len(indicators_text)}")


        # Парсим индикаторы внутри блока индикаторов
        indicators: List[Dict[str, Any]] = []
        # Паттерн для индикатора: начало строки, код ИДК (КодКомпетенции.НомерИндикатора), точка/скобка/пробел, формулировка
        # Ищем только внутри indicators_text
        ind_pattern = re.compile(
            # Ищем код индикатора, начинающийся с кода родительской компетенции (comp_code)
            rf'^\s*({comp_code})\.?[\s-]*(\d+)\.?[\s)]*(.*?)$', # Группа 1: Код компетенции, Группа 2: Номер индикатора, Группа 3: Формулировка
            re.DOTALL | re.MULTILINE | re.IGNORECASE
        )

        ind_matches = ind_pattern.finditer(indicators_text)

        for ind_match in ind_matches:
            ind_comp_code_found = ind_match.group(1)
            ind_number = ind_match.group(2)
            ind_code = f"{ind_comp_code_found.upper()}.{ind_number}" # Используем верхний регистр для консистентности
            ind_formulation = ind_match.group(3).strip()
            
            # Простая очистка формулировки (удаляем номера списков в начале)
            ind_formulation = re.sub(r'^\s*\d+\.\s*', '', ind_formulation).strip()
            ind_formulation = re.sub(r'^\s*[a-z]\)\s*', '', ind_formulation).strip()


            indicators.append({
                'code': ind_code,
                'formulation': ind_formulation
            })
            logger.debug(f"    - Found indicator: {ind_code}, Formulation: '{ind_formulation[:50]}...'")
        
        # TODO: Если индикаторы не были найдены в стандартном формате, но текст индикаторов существует,
        # возможно, они просто идут списком. Это более сложный кейс, требующий дополнительных эвристик.
        # Можно попробовать добавить весь indicators_text как один индикатор, если он не пустой и не нашлось структурированных индикаторов.
        # if not indicators and indicators_text and len(indicators_text) > 50: # Эвристика: текст достаточно длинный
        #      logger.warning(f"    - No structured indicators found for {comp_code}, but indicator text exists. Adding raw text as one indicator.")
        #      indicators.append({'code': f'{comp_code}.raw', 'formulation': indicators_text[:500] + '...' if len(indicators_text) > 500 else indicators_text}) # Добавляем сырой текст как индикатор


        competencies.append({
            'code': comp_code,
            'name': comp_name,
            'indicators': indicators
        })

    return competencies

# Не удаляем if __name__ == '__main__': блок, он полезен для автономного тестирования парсера
if __name__ == '__main__':
    import os
    # Пример использования из командной строки для тестирования
    # Замените на путь к реальному файлу ФГОС
    test_file_path = 'ФГОС ВО 090301_B_3_15062021.pdf' # <-- CHANGE THIS to your file path
    # Настроим логирование для автономного запуска
    logging.basicConfig(level=logging.DEBUG) # Или logging.INFO для меньшей детализации

    if not os.path.exists(test_file_path):
        print(f"Тестовый файл не найден: {test_file_path}")
    else:
        print(f"Парсинг тестового файла: {test_file_path}")
        try:
            with open(test_file_path, 'rb') as f:
                file_content = f.read()

            parsed_data = parse_fgos_pdf(file_content, os.path.basename(test_file_path))

            print("\n--- Результат парсинга ---")
            print("Метаданные:", parsed_data.get('metadata'))
            print("\nУК Компетенции:", len(parsed_data.get('uk_competencies', [])))
            for comp in parsed_data.get('uk_competencies', []):
                print(f"  - {comp['code']}: {comp['name'][:80]}...")
                for ind in comp.get('indicators', []):
                    print(f"    - {ind['code']}: {ind['formulation'][:80]}...")

            print("\nОПК Компетенции:", len(parsed_data.get('opk_competencies', [])))
            for comp in parsed_data.get('opk_competencies', []):
                print(f"  - {comp['code']}: {comp['name'][:80]}...")
                for ind in comp.get('indicators', []):
                    print(f"    - {ind['code']}: {ind['formulation'][:80]}...")

            print("\nРекомендованные ПС:", parsed_data.get('recommended_ps_codes'))
            # print("\nСырой текст (превью):", parsed_data.get('raw_text', '')[:1000], "...")

        except ValueError as e:
             print(f"\n!!! ПАРСИНГ ОШИБКА (ValueError): {e} !!!")
        except Exception as e:
            print(f"\n!!! НЕОЖИДАННАЯ ОШИБКА: {e} !!!")