# filepath: cli_commands/parse_profstandard.py
"""
Flask CLI команда для парсинга файлов Профессиональных Стандартов (ПС)
и сохранения их структуры в базу данных.

Эта команда позволяет парсить HTML или DOCX файлы ПС, извлекать их структуру
(ОТФ, ТФ, ТД, НУ, НЗ) и сохранять эти данные в соответствующие таблицы БД
(competencies_prof_standard, competencies_generalized_labor_function и т.д.).

Требует установки: pip install beautifulsoup4 lxml python-docx markdownify chardet

Основные возможности:
- Поддержка парсинга HTML и DOCX файлов (DOCX требует доработки).
- Извлечение кода и названия ПС.
- Извлечение структуры ОТФ, ТФ, ТД, НУ, НЗ.
- Сохранение структуры в связанные таблицы БД.
- Опция перезаписи (--force) существующего ПС и его структуры.
- Опция "пробного запуска" (--dry-run) для проверки парсинга без сохранения.

Пример использования:
    # Пропарсить и сохранить новый ПС
    flask parse-ps "path/to/ps_06.001.html"

    # Пропарсить и перезаписать существующий ПС
    flask parse-ps "path/to/ps_06.001.html" --force

    # Только проверить парсинг без сохранения
    flask parse-ps "path/to/ps_06.001.html" --dry-run
"""
import click
from flask.cli import with_appcontext
import os
import traceback
import logging

# Импорты из вашего приложения
from maps.models import db
from competencies_matrix.logic import save_parsed_prof_standard_structure # <<-- НОВАЯ ФУНКЦИЯ
from competencies_matrix.parsers import parse_prof_standard_file # <<-- НОВАЯ ФУНКЦИЯ

# Настройка логирования
logger = logging.getLogger(__name__)

@click.command(name='parse-ps')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force save/overwrite if Professional Standard with the same code exists.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform parsing without saving to the database.')
@with_appcontext
def parse_ps_command(filepath, force, dry_run):
    """
    Парсит файл Профессионального Стандарта (HTML/DOCX) и сохраняет структуру в БД.

    FILEPATH: Путь к файлу ПС для парсинга (HTML или DOCX).
    """
    print(f"\n---> Starting Professional Standard parsing from: {filepath}")
    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved to the database. <<<")
    filename = os.path.basename(filepath)

    try:
        # 1. Парсинг файла
        print(f"Parsing file: {filename}...")
        # Используем новую функцию parse_prof_standard_file
        # Она должна возвращать словарь со структурой (ОТФ, ТФ и т.д.) и метаданными
        parsed_structure = parse_prof_standard_file(filepath)

        if not parsed_structure or not parsed_structure.get('code') or not parsed_structure.get('name'):
             print("\n!!! PARSING FAILED or incomplete: Could not extract code/name. Aborting. !!!")
             return

        print("   - File parsed successfully.")
        print(f"   - Found PS Code: {parsed_structure.get('code')}")
        print(f"   - Found PS Name: {parsed_structure.get('name')}")
        # Можно добавить вывод количества найденных ОТФ/ТФ для информации
        otf_count = len(parsed_structure.get('generalized_labor_functions', []))
        tf_count = sum(len(otf.get('labor_functions', [])) for otf in parsed_structure.get('generalized_labor_functions', []))
        print(f"   - Found {otf_count} ОТФ and {tf_count} ТФ.")

        # 2. Сохранение структуры в БД (если не dry-run)
        if not dry_run:
            print("Saving parsed structure to database...")
            # Используем новую функцию save_parsed_prof_standard_structure
            saved_ps = save_parsed_prof_standard_structure(
                parsed_data=parsed_structure,
                filename=filename, # Передаем имя файла для логов/метаданных
                session=db.session,
                force_update=force
            )

            if saved_ps:
                print(f"   - Structure for PS '{saved_ps.code}' saved/updated successfully (ID: {saved_ps.id}).")
                print(f"---> Professional Standard from '{filename}' processed successfully!\n")
            else:
                # Ошибка должна была быть залогирована внутри save_parsed_prof_standard_structure
                print("\n!!! SAVE FAILED: Error occurred while saving parsed structure. Check logs. !!!")
        else:
            print("   - Skipping database save due to --dry-run flag.")
            print(f"---> DRY RUN for '{filename}' completed successfully (parsing passed).\n")

    except FileNotFoundError:
        print(f"\n!!! ERROR: File not found at '{filepath}' !!!")
    except ImportError as e:
        print(f"\n!!! ERROR: Missing dependency for parsing: {e} !!!")
        print("   - Please ensure 'beautifulsoup4', 'lxml', 'python-docx', 'markdownify', 'chardet' are installed.")
    except Exception as e:
        if not dry_run:
            db.session.rollback()
            print("   - Database transaction rolled back due to error.")
        print(f"\n!!! UNEXPECTED ERROR during parsing/saving: {e} !!!")
        traceback.print_exc()