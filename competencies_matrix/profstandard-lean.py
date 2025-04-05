# -*- coding: utf-8 -*-
"""
===================================================================================
                    HTML Parser for Professional Standards (ПС)
===================================================================================

Назначение скрипта в контексте веб-приложения "Матрицы компетенций":

Этот скрипт выполняет ключевую вспомогательную функцию для бэкенда веб-приложения,
отвечающего за управление матрицами компетенций. Его основная задача - преобра-
зование "сырых" HTML-файлов, содержащих тексты Профессиональных Стандартов (ПС)
(полученных с внешних ресурсов, например, classinform.ru или официальных порталов),
в чистый и структурированный формат Markdown.

Зачем это нужно:
Профессиональные стандарты часто публикуются в виде сложных, перегруженных стилями
и скриптами HTML-страниц. Работать с таким форматом напрямую в бэкенде для
извлечения Трудовых Функций (ТФ), знаний, умений (необходимых для формирования
Профессиональных Компетенций (ПК) и Индикаторов их Достижения (ИДК)) или для
анализа с помощью NLP-модулей крайне неэффективно и чревато ошибками.

Что делает скрипт:
1.  **Определяет кодировку** HTML-файла (часто нестандартную, как windows-1251).
2.  **Парсит HTML**, используя BeautifulSoup и lxml.w
3.  **Идентифицирует и извлекает основной контент** стандарта, отсекая навигацию,
    рекламу, шапки, подвалы и прочий "мусор" веб-страницы.
4.  **Производит глубокую очистку** контента: удаляет скрипты, стили, ненужные
    атрибуты, специфические блоки (формы поиска, ссылки на PDF и т.д.).
5.  **Обрабатывает таблицы** с помощью библиотеки Pandas, преобразуя их в
    стандартный Markdown-формат, который лучше подходит для машинной обработки
    и отображения.
6.  **Конвертирует оставшийся текст** (заголовки, параграфы, списки, сноски)
    в Markdown с помощью markdownify.
7.  **Выдает на выходе** единый текстовый файл в формате Markdown, содержащий
    только релевантную информацию из Профессионального Стандарта в максимально
    чистом и структурированном виде.

Результат работы скрипта (Markdown-файл) может затем использоваться бэкендом
веб-приложения для:
-   Отображения текста ПС пользователю (методисту) в удобном виде.
-   Дальнейшей обработки NLP-модулем для автоматического извлечения ТФ, знаний,
    умений или помощи в формулировании ИДК.
-   Индексации и поиска по содержимому стандартов.

Таким образом, этот скрипт служит важным этапом предварительной обработки данных,
позволяя основной логике веб-приложения работать с более качественными и
подготовленными данными Профессиональных Стандартов.

===================================================================================

Требует установки:
pip install beautifulsoup4 lxml markdownify chardet pandas tabulate
"""

import os
import pandas as pd
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from markdownify import markdownify
import chardet
import re # Для поиска сносок

def detect_encoding(filepath):
    """Определяет кодировку файла."""
    # Сначала проверим мета-тег, т.к. он часто более надежен
    try:
        with open(filepath, 'rb') as f:
            # Читаем только начало файла для поиска мета-тега
            head_data = f.read(2048)
            # Ищем charset=... в мета-теге content-type
            match = re.search(rb'<meta.*?content=".*?charset=([\w-]+)".*?>', head_data, re.IGNORECASE)
            if match:
                declared_encoding = match.group(1).decode('ascii', errors='ignore')
                print(f"Кодировка заявлена в HTML: {declared_encoding}")
                # Проверяем, поддерживается ли кодировка Python
                import codecs
                try:
                    codecs.lookup(declared_encoding)
                    return declared_encoding
                except LookupError:
                    print(f"Заявленная кодировка {declared_encoding} не поддерживается Python, используем chardet.")
                    # Fall through to chardet
    except Exception as e:
        print(f"Ошибка при поиске кодировки в мета-теге: {e}")

    # Если не нашли в мета-теге или ошибка, используем chardet
    try:
        with open(filepath, 'rb') as f:
            rawdata = f.read()
        result = chardet.detect(rawdata)
        encoding = result['encoding'] if result['encoding'] and result['confidence'] > 0.5 else None
        print(f"Chardet определил кодировку: {encoding} с уверенностью {result.get('confidence', 'N/A')}")
        return encoding
    except Exception as e:
        print(f"Ошибка при определении кодировки файла {filepath} через chardet: {e}")
        return None


def clean_html_tag(tag):
    """Удаляет ненужные атрибуты из ОДНОГО тега soup (in-place)."""
    if not isinstance(tag, Tag):
        return tag

    allowed_attrs = ['href', 'src', 'alt']
    # Удаляем специфичные для форматирования атрибуты таблиц, они обработаются Pandas
    table_formatting_attrs = ['border', 'cellpadding', 'cellspacing', 'style', 'width', 'align', 'valign', 'colspan', 'rowspan']
    attrs = dict(tag.attrs)
    for attr in attrs:
        if attr not in allowed_attrs and attr not in table_formatting_attrs:
             # print(f"Удаляется атрибут {attr} из тега {tag.name}") # Для отладки
             del tag[attr]
        elif attr == 'style' and tag.name != 'table': # Удаляем style у всех, кроме таблиц (хотя и там не нужен)
             # print(f"Удаляется атрибут style из тега {tag.name}") # Для отладки
             del tag[attr]

    return tag


def html_to_markdown_parser_enhanced(
        html_filepath,
        output_filepath=None,
        content_selector="div#cont_txt", # Используем селектор для целевого блока
        default_encoding='windows-1251' # Явно указано в HTML
    ):
    """
    Парсит HTML, извлекает и очищает основной контент ('div#cont_txt'),
    обрабатывает таблицы через Pandas и конвертирует в Markdown.
    """
    detected_enc = detect_encoding(html_filepath)
    encoding = detected_enc or default_encoding
    print(f"Используется кодировка: {encoding}")

    try:
        with open(html_filepath, 'r', encoding=encoding, errors='ignore') as f:
            html_content = f.read()
    except FileNotFoundError:
        print(f"Ошибка: Файл не найден {html_filepath}")
        return None
    except Exception as e:
        print(f"Ошибка при чтении файла {html_filepath} с кодировкой {encoding}: {e}")
        return None

    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception as e:
        print(f"Ошибка при парсинге HTML: {e}")
        return None

    # --- Шаг 1: Удаление глобального мусора (левая колонка, шапка, подвал, реклама) ---
    elements_to_remove_globally = [
        'div#head100', 'div#menu', 'div#header', 'div#cont_left',
        'div#banner_bottom', 'div#footer', 'div#ffoot',
        'script', 'style', 'noscript', 'form.search' # Удаляем все скрипты, стили и формы поиска
    ]
    for selector in elements_to_remove_globally:
        for element in soup.select(selector):
            element.decompose()

    # Удаляем рекламные блоки по ID внутри #cont_right (если они там есть)
    for ad_block_id in ["yandex_rtb_R-A-164017-16", "yandex_rtb_R-A-164017-12", "cont_banner"]:
         ad_block = soup.find(id=ad_block_id)
         if ad_block:
             # Иногда сам блок или его родительский div нужно удалить
             parent_div = ad_block.find_parent('div', style=re.compile(r'text-align:center'))
             if parent_div:
                 parent_div.decompose()
             else:
                 ad_block.decompose()

    # --- Шаг 2: Извлечение основного контента ---
    main_content_area = soup.select_one(content_selector)
    if not main_content_area:
        print(f"Ошибка: Селектор контента '{content_selector}' не найден.")
        # Попробуем найти #cont_right как запасной вариант
        main_content_area = soup.select_one('div#cont_right')
        if not main_content_area:
             print("Ошибка: Не найдены ни 'div#cont_txt', ни 'div#cont_right'.")
             return None

    # --- Шаг 3: Очистка ВНУТРИ основного контента ---
    # Удаляем навигационные пути "path"
    for path_div in main_content_area.select('div.path'):
        path_div.find_parent('div', class_='full_width').decompose()

    # Удаляем параграф со ссылкой на PDF
    pdf_link_p = main_content_area.find('a', href=re.compile(r'\.pdf$'))
    if pdf_link_p:
        # Удаляем родительский параграф <p>, если он есть
        parent_p = pdf_link_p.find_parent('p')
        if parent_p:
            parent_p.decompose()
        else:
            pdf_link_p.decompose() # На всякий случай, если 'a' без 'p'

    # Удаляем пустые <p> теги, которые могли остаться
    for p_tag in main_content_area.find_all('p'):
         if not p_tag.get_text(strip=True) and not p_tag.find(['img', 'br']):
             p_tag.decompose()

    # Удаляем HTML-комментарии
    for comment in main_content_area.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # --- Шаг 4: Обработка оставшегося контента ---
    markdown_parts = []
    # Работаем с элементами внутри main_content_area
    # Обрабатываем вложенность, включая текст внутри тега <em>
    content_elements = main_content_area.find_all(recursive=False) # Начнем с прямых потомков
    if not content_elements: # Если контент сразу внутри, как в случае <div id="cont_txt"><em>...</em></div>
         content_elements = main_content_area.contents

    for element in content_elements:
        if isinstance(element, NavigableString):
            text = element.strip()
            if text:
                markdown_parts.append(text)
        elif isinstance(element, Tag):
            # Рекурсивно обработать элементы, если это контейнер типа div или em
            if element.name in ['div', 'em']:
                 # Обрабатываем дочерние элементы этого контейнера
                 for child in element.contents:
                     if isinstance(child, NavigableString):
                         text = child.strip()
                         if text:
                             # Проверяем, не является ли текст сноской
                             if re.match(r'^<\d+>', text):
                                 markdown_parts.append(f"\n{text}\n") # Добавляем переносы строк для сносок
                             else:
                                 markdown_parts.append(text)
                     elif isinstance(child, Tag):
                         if child.name == 'table':
                             # Обработка таблицы через Pandas
                             try:
                                 # Используем lxml напрямую для лучшей обработки HTML таблиц
                                 dfs = pd.read_html(str(child), flavor='lxml', header=0, encoding=encoding, keep_default_na=False)
                                 if dfs:
                                     for df in dfs:
                                         # Убираем пустые строки/столбцы, которые мог создать Pandas из-за rowspan/colspan
                                         df.dropna(axis=0, how='all', inplace=True)
                                         df.dropna(axis=1, how='all', inplace=True)
                                         # Замена пустых строк на '-' для ясности (опционально)
                                         # df = df.replace('', '-', regex=False)
                                         # Конвертируем DataFrame в Markdown
                                         md_table = df.to_markdown(index=False, tablefmt='pipe')
                                         markdown_parts.append(md_table)
                                 else:
                                      print("Предупреждение: Pandas не смог извлечь DataFrame из таблицы (возможно, пустая).")
                             except Exception as e:
                                 print(f"Ошибка при обработке таблицы через Pandas: {e}. Пропуск таблицы.")
                                 # Можно добавить markdownify как fallback, но он скорее всего тоже не справится
                         elif child.name == 'br':
                              # Обычно не нужно явно добавлять, т.к. markdownify и структура блоков их подразумевают
                              pass
                         elif child.name in ['div']: # Обрабатываем div внутри em/div (сноски, заголовки стандарта)
                               text_inside = child.get_text(strip=True)
                               if text_inside:
                                   # Проверяем на сноски
                                   if re.match(r'^<\d+>', text_inside) or "--------------------------------" in text_inside:
                                        markdown_parts.append(f"\n{text_inside}\n")
                                   # Проверяем на заголовки разделов стандарта
                                   elif re.match(r'^[IVX]+\.\s', text_inside) or re.match(r'^\d+\.\d+(\.\d+)?\.\s', text_inside):
                                        markdown_parts.append(f"### {text_inside}") # Делаем подзаголовком 3 уровня
                                   else:
                                        # Преобразуем в обычный текст или Markdown
                                        md_part = markdownify(str(child), heading_style="ATX", bullets='-').strip()
                                        if md_part:
                                             markdown_parts.append(md_part)
                         else:
                            # Обработка других тегов внутри em/div через Markdownify
                            clean_html_tag(child)
                            md_part = markdownify(str(child), heading_style="ATX", bullets='-').strip()
                            if md_part:
                                markdown_parts.append(md_part)

            elif element.name == 'table':
                 # Таблицы, которые являются прямыми потомками main_content_area
                 try:
                     dfs = pd.read_html(str(element), flavor='lxml', header=0, encoding=encoding, keep_default_na=False)
                     if dfs:
                         for df in dfs:
                             df.dropna(axis=0, how='all', inplace=True)
                             df.dropna(axis=1, how='all', inplace=True)
                             # df = df.replace('', '-', regex=False)
                             md_table = df.to_markdown(index=False, tablefmt='pipe')
                             markdown_parts.append(md_table)
                     else:
                          print("Предупреждение: Pandas не смог извлечь DataFrame из таблицы (прямой потомок).")
                 except Exception as e:
                     print(f"Ошибка при обработке таблицы (прямой потомок) через Pandas: {e}. Пропуск таблицы.")

            elif element.name in ['h1', 'h2', 'h3', 'p']:
                 # Обработка заголовков и параграфов
                 clean_html_tag(element)
                 md_part = markdownify(str(element), heading_style="ATX", bullets='-').strip()
                 if md_part:
                     markdown_parts.append(md_part)
            # Игнорируем другие теги на этом уровне (например, <br>)

    # Собираем итоговый Markdown
    final_markdown = "\n\n".join(filter(None, markdown_parts))
    final_markdown = '\n'.join(line for line in final_markdown.splitlines() if line.strip()) # Удаляем пустые строки

    # --- Шаг 5: Сохранение или возврат результата ---
    if output_filepath:
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(final_markdown)
            print(f"Улучшенный Markdown сохранен в {output_filepath}")
            return None
        except Exception as e:
            print(f"Ошибка при сохранении файла {output_filepath}: {e}")
            return final_markdown
    else:
        return final_markdown


if __name__ == '__main__':
    input_html = 'input.html'
    output_md = 'output_classinform.md' # Новое имя файла

    # Селектор определен из анализа HTML
    content_container_selector = 'div#cont_txt'

    print(f"Запуск улучшенного парсера для файла: {input_html}")
    print(f"Используется селектор для контента: '{content_container_selector}'")

    markdown_result = html_to_markdown_parser_enhanced(
        input_html,
        output_md,
        content_selector=content_container_selector
    )

    if markdown_result:
        print("\n--- Начало результата Markdown (первые 1000 символов) ---")
        print(markdown_result[:1000] + ("..." if len(markdown_result) > 1000 else ""))
        print("--- Конец превью результата ---")
    elif os.path.exists(output_md):
         print(f"\nКонвертация завершена. Результат в файле: {output_md}")
    else:
         print("\nКонвертация завершилась с ошибкой или без результата.")