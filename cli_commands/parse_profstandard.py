# cli_commands/parse_profstandard.py

import click
from flask.cli import with_appcontext
import os
import traceback
import logging

# Импорты из вашего приложения
from maps.models import db # db используется для доступа к сессии
# from competencies_matrix.logic import save_prof_standard_data, parse_prof_standard_file # <--- ИСПРАВЛЕНО
from competencies_matrix.logic import (
    save_prof_standard_data, # Импортируем функцию сохранения из logic.py
    parse_prof_standard_file # Импортируем оркестратор парсинга из logic.py
)
# from competencies_matrix.parsers import parse_prof_standard_file # <-- Был импорт из parsers, теперь парсинг оркестрируется в logic

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
    Парсит файл Профессионального Стандарта (HTML/DOCX/PDF), извлекает структуру
    и сохраняет в БД.

    FILEPATH: Путь к файлу ПС для парсинга.
    """
    print(f"\n---> Starting Professional Standard parsing from: {filepath}")
    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved to the database. <<<")
    filename = os.path.basename(filepath)

    # Получаем сессию БД, если не в dry-run режиме
    session = db.session if not dry_run else None

    try:
        # 1. Парсинг файла (используем оркестратор из logic.py)
        print(f"Parsing file: {filename}...")
        # parse_prof_standard_file теперь возвращает {'success': bool, 'error': str, 'parsed_data': {...}}
        parse_result = parse_prof_standard_file(filepath) # Теперь принимает путь, читает файл внутри

        if not parse_result['success']:
             print(f"\n!!! PARSING FAILED: {parse_result['error']} !!!")
             return # Выходим при ошибке парсинга


        parsed_data = parse_result.get('parsed_data')
        if not parsed_data or not parsed_data.get('code') or not parsed_data.get('name'):
             # Эта проверка может быть избыточна, если parse_prof_standard_file выбрасывает исключения или возвращает success=False
             print("\n!!! PARSING FAILED or incomplete: Could not extract code/name after successful parse. Aborting. !!!")
             return


        print("   - File parsed successfully.")
        print(f"   - Found PS Code: {parsed_data.get('code')}")
        print(f"   - Found PS Name: {parsed_data.get('name')}")
        # Выводим количество найденных ОТФ/ТФ для информации
        otf_count = len(parsed_data.get('generalized_labor_functions', []))
        tf_count = sum(len(otf.get('labor_functions', [])) for otf in parsed_data.get('generalized_labor_functions', [])) if otf_count > 0 else 0
        print(f"   - Found {otf_count} ОТФ and {tf_count} ТФ.")


        # 2. Сохранение структуры в БД (если не dry-run)
        if not dry_run:
            print("Saving parsed structure to database...")
            # Вызываем логику сохранения, передавая парсенные данные и сессию
            # save_prof_standard_data управляет своей транзакцией (savepoint), но commit/rollback должен быть на уровне CLI
            try:
                # Используем явную транзакцию для всей операции сохранения ПС
                with db.session.begin(): # Начинаем явную транзакцию
                    saved_ps = save_prof_standard_data( # <-- ИСПРАВЛЕНО
                        parsed_data=parsed_data,
                        filename=filename,
                        session=db.session, # Передаем текущую сессию
                        force_update=force
                    )

                # Транзакция коммитится при выходе из with блока, если нет исключений
                if saved_ps:
                    print(f"   - Structure for PS '{saved_ps.code}' saved/updated successfully (ID: {saved_ps.id}).")
                    print(f"---> Professional Standard from '{filename}' processed successfully!\n")
                else:
                    # Ошибка должна была быть залогирована внутри save_prof_standard_data
                    print("\n!!! SAVE FAILED: Error occurred while saving parsed structure. Check logs. !!!")

            except Exception as e: # Ловим ошибки при сохранении
                # Транзакция откатится автоматически при выходе из with блока после исключения
                db.session.rollback() # Явный откат на всякий случай, хотя with block должен справиться
                print(f"\n!!! SAVE FAILED during transaction: {e} !!!")
                print("   - Database transaction rolled back.")
                traceback.print_exc()

        else:
            print("   - Skipping database save due to --dry-run flag.")
            print(f"---> DRY RUN for '{filename}' completed successfully (parsing passed).\n")

    except FileNotFoundError:
        print(f"\n!!! ERROR: File not found at '{filepath}' !!!")
    except ImportError as e:
        print(f"\n!!! ERROR: Missing dependency for parsing: {e} !!!")
        print("   - Please ensure 'beautifulsoup4', 'lxml', 'python-docx', 'markdownify', 'chardet', 'pdfminer.six' are installed.") # Добавил pdfminer на всякий случай
    except Exception as e: # Ловим другие ошибки (кроме парсинга)
        if not dry_run and session and session.dirty: session.rollback() # Откат, если сессия была изменена до ошибки
        print(f"\n!!! UNEXPECTED ERROR during processing: {e} !!!")
        traceback.print_exc()

    finally:
         # Не нужно закрывать сессию здесь, т.к. она управляется flask.cli.with_appcontext
         pass