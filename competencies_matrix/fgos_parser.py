# competencies_matrix/fgos_parser.py (УПРОЩЕННАЯ ВЕРСИЯ ДЛЯ MVP ПОСЛЕ АНАЛИЗА ДОКУМЕНТОВ)

import io
import re
import datetime
from typing import Dict, List, Any, Optional
from pdfminer.high_level import extract_text
import logging
import traceback

logger = logging.getLogger(__name__)

# --- Функции для извлечения УК/ОПК (только код и название) ---
def parse_uk_opk_simple(text: str, comp_prefix: str) -> List[Dict[str, str]]:
    """
    Парсит УК или ОПК компетенции (код и название) из текста раздела III ФГОС,
    без индикаторов (т.к. их нет в структурированном виде в этих PDF).

    Args:
        text: Текст для парсинга (предполагается текст раздела III).
        comp_prefix: Префикс компетенции ('УК', 'ОПК').

    Returns:
        List[Dict[str, str]]: Список словарей с {'code': '...', 'name': '...'}.
    """
    competencies = []
    # Ищем код компетенции в начале строки, затем захватываем остаток строки как название
    # Учитываем разные разделители после кода.
    pattern = re.compile(
        # ^\s* : Начало строки с опциональными пробелами
        # ({comp_prefix}) : Группа 1 - сам префикс (УК или ОПК)
        # [\s-]* : Ноль или более пробелов или дефисов
        # (\d+) : Группа 2 - номер компетенции
        # \.?[\s)]* : Опциональная точка, опциональные пробелы/скобка
        # (.*?) : Группа 3 - остаток строки (формулировка), нежадный поиск
        # $ : Конец строки
        rf'^\s*({comp_prefix})[\s-]*(\d+)\.?[\s)]*(.*?)$',
        re.MULTILINE | re.IGNORECASE # MULTILINE для ^ и $, IGNORECASE для регистронезависимости
    )
    logger.debug(f"  parse_uk_opk_simple: Searching for '{comp_prefix}' with pattern '{pattern.pattern}' in text.")

    for match in pattern.finditer(text):
        code = f"{match.group(1).upper()}-{match.group(2)}"
        name = match.group(3).strip()
        # Удаляем возможные висячие точки в конце названия, если они остались после strip()
        name = name.rstrip('.')
        
        if name: # Пропускаем пустые названия
            competencies.append({'code': code, 'name': name})
            logger.debug(f"    Found {comp_prefix}: {code}, Name: '{name[:80]}...'")
        else:
            logger.debug(f"    Skipping {comp_prefix} {code} due to empty name after strip.")

    logger.debug(f"  parse_uk_opk_simple: Finished parsing {comp_prefix}. Found {len(competencies)} items.")
    return competencies

# --- Основная функция парсинга ФГОС ---
def parse_fgos_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Парсит содержимое PDF файла ФГОС ВО (для формата 3++),
    извлекая метаданные, УК/ОПК (код и название), и список рекомендованных ПС.
    НЕ ПАРСИТ ИНДИКАТОРЫ ИЗ PDF, т.к. их там нет в структурированном виде.

    Args:
        file_bytes: Содержимое PDF файла в байтах.
        filename: Имя файла (для логирования/инфо).

    Returns:
        Dict[str, Any]: Словарь с извлеченными данными или raise ValueError/Exception.
                        Структура: {
                            'metadata': { 'order_number', 'order_date', 'direction_code', 'direction_name', 'education_level', 'generation', 'order_date_raw' },
                            'uk_competencies': [{ 'code', 'name' }], # Без индикаторов здесь
                            'opk_competencies': [{ 'code', 'name' }], # Без индикаторов здесь
                            'recommended_ps_codes': [...],
                            'raw_text': '...' # Полный извлеченный текст (опционально)
                        }
    """
    logger.info(f"Starting PDF parsing for file: {filename}")
    text = ""
    try:
        # --- 1. Извлечение и очистка текста ---
        text = extract_text(io.BytesIO(file_bytes))
        logger.debug(f"Extracted raw text ({len(text)} characters).")
        if logger.level == logging.DEBUG:
             logger.debug(f"Raw text preview (first 1000 chars):\n{text[:1000]}...")

        # Базовая очистка текста: удаляем переносы в середине слов, лишние пробелы/переносы
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text) # Слово- \n Слово -> СловоСлово
        text = text.replace('-\n', '') # Висячий дефис в конце строки
        text = re.sub(r'[ \t]+', ' ', text) # Множественные пробелы/табы в один пробел
        text = re.sub(r'(\s*\n){2,}', '\n\n', text).strip() # Схлопываем множественные переносы строк до двух
        logger.debug(f"Cleaned text ({len(text)} characters).")
        if logger.level == logging.DEBUG:
            logger.debug(f"Cleaned text preview (first 1000 chars):\n{text[:1000]}...")


        parsed_data: Dict[str, Any] = {
            'metadata': {},
            'uk_competencies': [],
            'opk_competencies': [],
            'recommended_ps_codes': [],
            'raw_text': text # Сохраняем весь текст для отладки или будущих парсеров
        }

        # --- 2. Извлечение метаданных ---
        # Используем регулярку, которая хорошо работала до этого момента
        metadata_pattern = re.compile(
            # Ищем блок, начинающийся с "от" (дата) и содержащий номер приказа, направление и уровень
            # Сделано устойчивее к вариациям
            r'.*?от\s+'  # Начинаем поиск с "от "
            r'((' # Группа 1 (полная дата):
                r'\d{2}\.\d{2}\.\d{4}' # Вариант 1: DD.MM.YYYY (Группа 2)
            r')|(' # ИЛИ
                r'\d{1,2}\s+\S+\s+\d{4}\s+г\.' # Вариант 2: D MMMM YYYY г. (Группа 3)
            r'))\s+' # Конец группы даты
            r'[№N]\s*(\d+)' # Группа 4 (номер приказа)
            r'.*?по\s+направлению\s+подготовки\s+(\d{2}\.\d{2}\.\d{2})\s+' # Группа 5 (код направления)
            r'([^(\n]+)' # Группа 6 (название направления, до "(" или переноса строки)
            r'.*?уровень\s+(бакалавриата|магистратуры|специалитета)', # Группа 7 (уровень)
            re.DOTALL | re.IGNORECASE # DOTALL позволяет . совпадать с \n, IGNORECASE игнорирует регистр
        )
        metadata_match = metadata_pattern.search(text)

        if metadata_match:
            date_str_ddmmyyyy = metadata_match.group(2)
            date_str_text = metadata_match.group(3)
            parsed_data['metadata']['order_date_raw'] = date_str_ddmmyyyy or date_str_text

            fgos_date_obj = None
            # Парсинг даты в объект Date (поддерживаем DD.MM.YYYY и "D MMMM YYYY г.")
            if date_str_ddmmyyyy:
                 try: fgos_date_obj = datetime.datetime.strptime(date_str_ddmmyyyy, '%d.%m.%Y').date()
                 except (ValueError, TypeError): logger.warning(f"Could not parse date '{date_str_ddmmyyyy}' from DD.MM.YYYY format.")
            elif date_str_text:
                 try:
                     month_names = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}
                     parts = date_str_text.replace(' г.', '').split()
                     if len(parts) == 3:
                         day = int(parts[0]); month_str = parts[1].lower(); year = int(parts[2])
                         month = month_names.get(month_str)
                         if month: fgos_date_obj = datetime.date(year, month, day)
                         else: logger.warning(f"Could not parse month name '{parts[1]}' from text date.")
                     else: logger.warning(f"Unexpected number of parts in text date '{date_str_text}'.")
                 except (ValueError, TypeError) as e: logger.warning(f"Could not parse text date '{date_str_text}': {e}")

            parsed_data['metadata']['order_date'] = fgos_date_obj
            parsed_data['metadata']['order_number'] = metadata_match.group(4).strip()
            parsed_data['metadata']['direction_code'] = metadata_match.group(5).strip()
            # Убираем возможные остатки типа " (с изменениями и" из названия направления
            direction_name_raw = metadata_match.group(6).strip()
            parsed_data['metadata']['direction_name'] = re.sub(r'\s*\(с изменениями.*$', '', direction_name_raw).strip()
            # Уровень приводим к нижнему регистру для консистентности
            parsed_data['metadata']['education_level'] = metadata_match.group(7).strip().lower()

            # Попытка определить поколение (3+ или 3++) - ищем в начале документа (первые 1500 символов) или в имени файла
            preview_text = text[:1500]
            if re.search(r'ФГОС\s+ВО\s+3\+\+', filename, re.IGNORECASE) or re.search(r'ФГОС\s+ВО\s+(?:поколения\s+)?3\+\+', preview_text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3++'
            elif re.search(r'ФГОС\s+ВО\s+3\+', filename, re.IGNORECASE) or re.search(r'ФГОС\s+ВО\s+(?:поколения\s+)?3\+', preview_text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3+'
            else:
                 parsed_data['metadata']['generation'] = 'не определено'
            logger.info("Metadata extracted successfully.")
            logger.debug(f"Extracted metadata: {parsed_data['metadata']}")
        else:
             logger.error("Metadata pattern did not match in the document.")
             raise ValueError("Не удалось извлечь основные метаданные ФГОС.")


        # --- 3. Извлечение компетенций (только код и название) ---
        # Ищем начало и конец раздела III "Требования к результатам освоения..."
        section_iii_start_match = re.search(r'III\.\s+Требования\s+к\s+результатам\s+освоения\s+программы', text, re.IGNORECASE | re.DOTALL)
        # Ищем начало раздела IV "Требования к условиям реализации..." (для определения конца раздела III)
        section_iv_start_match = re.search(r'IV\.\s+Требования\s+к\s+условиям\s+реализации\s+программы', text, re.IGNORECASE | re.DOTALL)

        comp_section_text = ""
        if section_iii_start_match:
            start_index = section_iii_start_match.end()
            end_index = len(text)
            if section_iv_start_match and section_iv_start_match.start() > start_index:
                 end_index = section_iv_start_match.start()

            # Извлекаем текст раздела III
            comp_section_text = text[start_index:end_index].strip()
            logger.debug(f"Section III text extracted (length {len(comp_section_text)}). Preview (first 500 chars):\n{comp_section_text[:500]}...")

            # Используем простую функцию для извлечения УК и ОПК из текста раздела III
            parsed_data['uk_competencies'] = parse_uk_opk_simple(comp_section_text, 'УК')
            parsed_data['opk_competencies'] = parse_uk_opk_simple(comp_section_text, 'ОПК')

            logger.info(f"Parsed Section III. Found {len(parsed_data['uk_competencies'])} УК and {len(parsed_data['opk_competencies'])} ОПК.")
            # Индикаторы не парсятся из этого файла, поэтому не определяем их количество здесь
            # total_indicators_found теперь не определяется из парсера, они из сидера
            # logger.info(f"Found a total of {total_indicators_found} indicators across all competencies.")

        else:
             logger.warning("Section III pattern did not match in the text.")
             # Если раздел III не найден, возможно, компетенции в другом месте или формате
             # Пока это считается критичным, т.к. УК/ОПК - обязательная часть ФГОС
             raise ValueError("Не удалось найти раздел III 'Требования к результатам освоения программы'.")


        # --- 4. Извлечение списка рекомендованных ПС ---
        # Ищем в конце документа или в приложении раздел с перечнем ПС
        # Используем регулярку для поиска заголовка "Перечень профессиональных стандартов"
        # Модифицируем поиск, чтобы он был менее чувствителен к регистру и контексту
        ps_section_header_pattern = r'Перечень\s+профессиональных\s+стандартов'

        # Область поиска для заголовка ПС: после раздела III, если он найден, иначе весь текст
        ps_search_area_start = section_iii_start_match.end() if section_iii_start_match else 0

        # Ищем заголовок раздела ПС
        ps_section_header_match = re.search(ps_section_header_pattern, text[ps_search_area_start:], re.IGNORECASE | re.MULTILINE)

        ps_text_for_code_search = ""
        if ps_section_header_match:
            # Если заголовок найден, берем текст от найденного заголовка до конца документа
            ps_text_for_code_search = text[ps_search_area_start + ps_section_header_match.start():].strip()
            logger.debug(f"Found PS section header. Searching for PS codes in text (length {len(ps_text_for_code_search)}). Preview: {ps_text_for_code_search[:300]}...")
        else:
            logger.warning("PS section header 'Перечень профессиональных стандартов' not found after Section III. Searching in entire document as fallback (less reliable).")
            # Если заголовок не найден, ищем коды ПС во всем документе, что менее надежно.
            ps_text_for_code_search = text.strip()


        # Ищем коды ПС в формате XX.XXX (например, 06.001)
        # \b для границ слова, чтобы не находить части других чисел или кодов
        ps_codes_found = re.findall(r'\b(\d{2}\.\d{3})\b', ps_text_for_code_search)
        # Убираем дубликаты и сортируем для консистентности
        parsed_data['recommended_ps_codes'] = sorted(list(set(ps_codes_found)))
        logger.info(f"Found {len(parsed_data['recommended_ps_codes'])} unique recommended PS codes: {parsed_data['recommended_ps_codes']}")


        # --- 5. Финальная проверка ---
        # Проверяем наличие обязательных метаданных и хотя бы УК/ОПК
        if not parsed_data['metadata'].get('order_number') or not parsed_data['metadata'].get('direction_code'):
             logger.error("Final check failed: Missing core metadata (order_number or direction_code).")
             raise ValueError("Не удалось извлечь основные метаданные ФГОС (номер, код направления).")
        # Теперь проверяем только наличие УК/ОПК, индикаторы приходят из другого источника (сидера)
        if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
             logger.error("Final check failed: No УК or ОПК competencies were extracted from Section III.")
             raise ValueError("Не удалось извлечь ни УК, ни ОПК компетенции из раздела III.")

        # Отчет о найденном
        logger.info(f"PDF parsing for {filename} finished successfully.")
        logger.info(f"Extracted FGOS: {parsed_data['metadata'].get('direction_code')} ({parsed_data['metadata'].get('education_level')}) - Приказ №{parsed_data['metadata'].get('order_number')} от {parsed_data['metadata'].get('order_date')}")
        logger.info(f"Found {len(parsed_data['uk_competencies'])} УК, {len(parsed_data['opk_competencies'])} ОПК.")
        logger.info(f"Found {len(parsed_data['recommended_ps_codes'])} Recommended PS codes.")


        return parsed_data

    except ValueError as ve:
        logger.error(f"FGOS Parsing ValueError for {filename}: {ve}", exc_info=False) # Логируем ошибку парсинга без traceback
        raise ve
    except Exception as e:
        logger.error(f"Unexpected error during FGOS parsing for {filename}: {e}", exc_info=True) # Логируем неожиданные ошибки с traceback
        raise Exception(f"Неожиданная ошибка при парсинге файла ФГОС '{filename}': {e}")


# --- Блок if __name__ == '__main__': для автономного тестирования ---
# Этот блок не изменялся, он использует только parse_fgos_pdf.
# Вывод индикаторов закомментирован, так как они не парсятся из PDF.
if __name__ == '__main__':
    import os
    # Укажите путь к вашему тестовому файлу ФГОС
    test_file_path = 'ФГОС ВО 090301_B_3_15062021.pdf' # <-- CHANGE THIS to your file path
    
    # Настроим логирование для автономного запуска скрипта
    # Уровень DEBUG покажет подробности парсинга регулярок
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Установим уровень DEBUG для логгера парсера явно, если основной уровень ниже
    parser_logger = logging.getLogger('competencies_matrix.fgos_parser')
    parser_logger.setLevel(logging.DEBUG)

    print(f"Парсинг тестового файла: {test_file_path}")
    if not os.path.exists(test_file_path):
        print(f"Тестовый файл не найден: {test_file_path}")
    else:
        try:
            with open(test_file_path, 'rb') as f:
                file_content = f.read()

            parsed_data = parse_fgos_pdf(file_content, os.path.basename(test_file_path))

            print("\n--- Результат парсинга ---")
            print("Метаданные:", parsed_data.get('metadata'))
            print("\nУК Компетенции:", len(parsed_data.get('uk_competencies', [])))
            for comp in parsed_data.get('uk_competencies', []):
                print(f"  - {comp['code']}: {comp['name'][:80]}...")
                # # Индикаторы не парсятся из этого файла, поэтому не выводим
                # for ind in comp.get('indicators', []):
                #     print(f"    - {ind['code']}: {ind['formulation'][:80]}...")

            print("\nОПК Компетенции:", len(parsed_data.get('opk_competencies', [])))
            for comp in parsed_data.get('opk_competencies', []):
                print(f"  - {comp['code']}: {comp['name'][:80]}...")
                # # Индикаторы не парсятся из этого файла, поэтому не выводим
                # for ind in comp.get('indicators', []):
                #     print(f"    - {ind['code']}: {ind['formulation'][:80]}...")

            print("\nРекомендованные ПС:", parsed_data.get('recommended_ps_codes'))
            print("\nСырой текст (превью):", parsed_data.get('raw_text', '')[:1000], "...")

        except ValueError as e:
             print(f"\n!!! ПАРСИНГ ОШИБКА (ValueError): {e} !!!")
        except Exception as e:
            print(f"\n!!! НЕОЖИДАННАЯ ОШИБКА: {e} !!!")
            traceback.print_exc()