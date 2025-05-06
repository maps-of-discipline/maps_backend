# competencies_matrix/fgos_parser.py
import io
import re
from typing import Dict, List, Any, Optional
from pdfminer.high_level import extract_text

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
                            'metadata': { ... },
                            'uk_competencies': [{ 'code': 'УК-N', 'name': '...', 'indicators': [{'code': 'ИУК-N.M', 'formulation': '...'}] }],
                            'opk_competencies': [{ 'code': 'ОПК-N', 'name': '...', 'indicators': [{'code': 'ИОПК-N.M', 'formulation': '...'}] }],
                            'recommended_ps_codes': ['06.001', '06.015', ...],
                            'raw_text': '...' # Полный извлеченный текст
                        }
    """
    try:
        # Извлекаем весь текст из PDF
        text = extract_text(io.BytesIO(file_bytes))
        # Удаляем переносы строк в середине слов, дефисы
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
        text = text.replace('-\n', '') # Удаляем висячие дефисы
        text = re.sub(r'\n{2,}', '\n\n', text) # Схлопываем множественные переносы строк
        
        parsed_data: Dict[str, Any] = {
            'metadata': {},
            'uk_competencies': [],
            'opk_competencies': [],
            'recommended_ps_codes': [],
            'raw_text': text # Сохраняем полный текст для отладки
        }

        # --- 1. Извлечение метаданных ---
        # Ищем "Федеральный государственный образовательный стандарт высшего образования..."
        metadata_section_match = re.search(
            r'Федеральный государственный образовательный стандарт высшего образования'
            r'.*?'
            r'(УТВЕРЖДЕН\s+приказом.*?\s+от\s+(\d{2}\.\d{2}\.\d{4})\s+№\s+(\d+))'
            r'.*?'
            r'(по\s+направлению\s+подготовки\s+(\d{2}\.\d{2}\.\d{2})\s+(.*?))'
            r'.*?'
            r'(уровень\s+(бакалавриата|магистратуры|специалитета))',
            text,
            re.DOTALL | re.IGNORECASE
        )

        if metadata_section_match:
            parsed_data['metadata']['order_info'] = metadata_section_match.group(1).strip()
            parsed_data['metadata']['order_date'] = metadata_section_match.group(2)
            parsed_data['metadata']['order_number'] = metadata_section_match.group(3)
            parsed_data['metadata']['direction_code'] = metadata_section_match.group(5)
            parsed_data['metadata']['direction_name'] = metadata_section_match_text = metadata_section_match.group(6).strip()
            parsed_data['metadata']['education_level'] = metadata_section_match.group(8).strip()
            
            # Попытка определить поколение (не всегда явно указано в тексте)
            # Это требует эвристики или знания структуры документа
            # В 3++ обычно есть упоминание в преамбуле или названии
            if re.search(r'ФГОС ВО 3\+\+', filename, re.IGNORECASE) or re.search(r'ФГОС ВО поколения 3\+\+', text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3++'
            elif re.search(r'ФГОС ВО 3\+', filename, re.IGNORECASE) or re.search(r'ФГОС ВО поколения 3\+', text, re.IGNORECASE):
                 parsed_data['metadata']['generation'] = '3+'
            else:
                 parsed_data['metadata']['generation'] = 'не определено' # Требует ручной верификации

        # --- 2. Извлечение компетенций и индикаторов ---
        # Ищем раздел "III. Требования к результатам освоения..."
        # А затем подразделы с таблицами компетенций (УК, ОПК)
        competencies_section_match = re.search(
            r'III\.\s+Требования\s+к\s+результатам\s+освоения\s+программы.*?$(.*?)' # Содержание раздела III
            r'(^IV\.\s+Требования\s+к\s+условиям\s+реализации\s+программы|\Z)', # До следующего раздела или конца файла
            text, re.DOTALL | re.MULTILINE
        )

        if competencies_section_match:
            comp_section_text = competencies_section_match.group(1)

            # Ищем блок УК
            uk_block_match = re.search(
                r'Универсальные\s+компетенции.*?$(.*?)' # Содержание блока УК
                r'(Общепрофессиональные\s+компетенции|Профессиональные\s+компетенции|\Z)', # До следующего блока или конца раздела
                comp_section_text, re.DOTALL | re.MULTILINE
            )

            if uk_block_match:
                uk_text = uk_block_match.group(1)
                parsed_data['uk_competencies'] = parse_competency_block(uk_text, 'УК')

            # Ищем блок ОПК
            opk_block_match = re.search(
                r'Общепрофессиональные\s+компетенции.*?$(.*?)' # Содержание блока ОПК
                r'(Профессиональные\s+компетенции|\Z)', # До следующего блока или конца раздела
                comp_section_text, re.DOTALL | re.MULTILINE
            )
             # Если нет отдельного блока ОПК, но есть в общем списке, его может найти парсер parse_competency_block
            if opk_block_match:
                opk_text = opk_block_match.group(1)
                parsed_data['opk_competencies'] = parse_competency_block(opk_text, 'ОПК')


            # Если УК и ОПК не были найдены в отдельных блоках (например, они идут сплошным списком)
            # Можно попробовать пропарсить весь раздел III как единый список, а затем разделить
            if not parsed_data['uk_competencies'] and not parsed_data['opk_competencies']:
                 print("Warning: УК/ОПК blocks not found. Attempting to parse entire section III as combined list.")
                 all_comp_list = parse_competency_block(comp_section_text, 'УК|ОПК') # Ищем и УК, и ОПК
                 # Разделяем по типу
                 parsed_data['uk_competencies'] = [c for c in all_comp_list if c.get('code', '').startswith('УК')]
                 parsed_data['opk_competencies'] = [c for c in all_comp_list if c.get('code', '').startswith('ОПК')]


        # --- 3. Извлечение списка рекомендованных ПС ---
        # Часто находится в приложении или в конце документа
        ps_section_match = re.search(
            r'(Приложение.*?^Перечень\s+профессиональных\s+стандартов.*?$|\Z)' # Начало раздела/приложения
            r'(.*?)' # Содержимое
            r'(\Z|^)', # Конец файла или другой явный маркер (трудно найти универсальный)
            text, re.DOTALL | re.MULTILINE
        )

        if ps_section_match:
             ps_section_text = ps_section_match.group(2)

             # Ищем коды ПС в формате XX.XXX (например, 06.001)
             ps_codes = re.findall(r'\b(\d{2}\.\d{3})\b', ps_section_text)
             parsed_data['recommended_ps_codes'] = list(set(ps_codes)) # Убираем дубликаты

        return parsed_data

    except Exception as e:
        print(f"Error parsing FGOS PDF file {filename}: {e}")
        # traceback.print_exc() # Для отладки
        raise ValueError(f"Ошибка при парсинге файла ФГОС: {e}")


def parse_competency_block(text: str, comp_type_prefix: str) -> List[Dict[str, Any]]:
    """
    Парсит текст, содержащий список компетенций и индикаторов,
    используя регулярные выражения.

    Args:
        text: Текст для парсинга.
        comp_type_prefix: Префикс типа компетенции ('УК', 'ОПК', 'ПК' или 'УК|ОПК').

    Returns:
        List[Dict[str, Any]]: Список словарей компетенций с их индикаторами.
                               Структура: [{ 'code': '...', 'name': '...', 'indicators': [{'code': '...', 'formulation': '...'}] }]
    """
    competencies: List[Dict[str, Any]] = []

    # Паттерн для поиска компетенции: начало строки, префикс, номер, точка, пробел, формулировка
    # Учитываем возможное наличие индикаторов после формулировки (текст до следующей компетенции или конца блока)
    comp_pattern = re.compile(
        rf'^\s*({comp_type_prefix})-\s*(\d+)\.\s*(.*?)$' # Группа 1: Префикс, Группа 2: Номер, Группа 3: Формулировка компетенции (до конца строки)
        r'(.*?)' # Группа 4: Текст после формулировки компетенции (предполагаем, что это индикаторы)
        rf'(?=\s*({comp_type_prefix})-\s*\d+\.\s*|\Z)', # Positive lookahead: до начала следующей компетенции или конца текста
        re.DOTALL | re.MULTILINE
    )

    matches = comp_pattern.finditer(text)

    for match in matches:
        comp_code = f"{match.group(1)}-{match.group(2)}"
        comp_name = match.group(3).strip()
        indicators_text = match.group(4).strip()

        # Парсим индикаторы внутри блока индикаторов
        indicators: List[Dict[str, Any]] = []
        # Паттерн для индикатора: начало строки, код ИДК (Префикс-НомерКомпетенции.НомерИндикатора), точка, пробел, формулировка
        # Учитываем, что формулировка индикатора может быть многострочной (re.DOTALL)
        ind_pattern = re.compile(
            rf'^\s*({comp_code})\.\s*(\d+)\.\s*(.*?)$', # Группа 1: Код компетенции, Группа 2: Номер индикатора, Группа 3: Формулировка
            re.DOTALL | re.MULTILINE
        )

        ind_matches = ind_pattern.finditer(indicators_text)

        for ind_match in ind_matches:
            ind_code = f"{ind_match.group(1)}.{ind_match.group(2)}"
            ind_formulation = ind_match.group(3).strip()
            indicators.append({
                'code': ind_code,
                'formulation': ind_formulation
            })
        
        # Если индикаторы не были найдены в стандартном формате "Компетенция.Номер.",
        # но текст индикаторов существует, возможно, они просто идут списком.
        # Это более сложный кейс, требующий дополнительных эвристик, пока оставим как есть.
        # Если индикаторов не нашлось, но индикаторный текст не пустой, можно его добавить как один индикатор
        # if not indicators and indicators_text:
        #      indicators.append({'code': f'{comp_code}.?', 'formulation': indicators_text})


        competencies.append({
            'code': comp_code,
            'name': comp_name,
            'indicators': indicators
        })

    return competencies

if __name__ == '__main__':
    # Пример использования из командной строки для тестирования
    # Замените на путь к реальному файлу ФГОС
    test_file_path = 'path/to/your/fgos_09_03_01_bak_3++.pdf' # <-- CHANGE THIS

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
                print(f"  - {comp['code']}: {comp['name'][:50]}...")
                for ind in comp.get('indicators', []):
                    print(f"    - {ind['code']}: {ind['formulation'][:50]}...")

            print("\nОПК Компетенции:", len(parsed_data.get('opk_competencies', [])))
            for comp in parsed_data.get('opk_competencies', []):
                print(f"  - {comp['code']}: {comp['name'][:50]}...")
                for ind in comp.get('indicators', []):
                    print(f"    - {ind['code']}: {ind['formulation'][:50]}...")

            print("\nРекомендованные ПС:", parsed_data.get('recommended_ps_codes'))
            # print("\nСырой текст (превью):", parsed_data.get('raw_text', '')[:1000], "...")

        except Exception as e:
            print(f"\nОшибка при выполнении парсера: {e}")