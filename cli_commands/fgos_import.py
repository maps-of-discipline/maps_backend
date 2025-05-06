# cli_commands/fgos_import.py
import click
from flask.cli import with_appcontext
import os
import traceback
import datetime

# --- Импортируем необходимые компоненты ---
from maps.models import db
from competencies_matrix.logic import parse_fgos_file, save_fgos_data, delete_fgos
from competencies_matrix.models import FgosVo # Нужно для поиска
import logging

logger = logging.getLogger(__name__)

@click.command(name='import-fgos')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force import/overwrite if FGOS with same identifying data exists.')
@click.option('--delete-only', is_flag=True, default=False,
              help='Only delete FGOS if it exists, do not import.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform read and validation without saving or deleting.')
@with_appcontext
def import_fgos_command(filepath, force, delete_only, dry_run):
    """
    Импортирует данные ФГОС ВО из PDF-файла, парсит и сохраняет в БД.
    Поиск существующего ФГОС производится по коду направления, уровню, номеру и дате приказа.

    FILEPATH: Путь к PDF файлу ФГОС для импорта.
    """
    print(f"\n---> Starting FGOS import from: {filepath}")
    filename = os.path.basename(filepath)

    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved/deleted from the database. <<<")

    try:
        # 1. Чтение и парсинг Excel файла
        print(f"Reading and parsing FGOS file: {filename}...")
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
        
        # Вызываем парсер
        # Ловим ValueError от парсера
        parsed_data = parse_fgos_file(file_bytes, filename)

        if not parsed_data:
            print("\n!!! PARSING FAILED !!!")
            print(f"   - Could not parse file or extract essential metadata from '{filename}'.")
            print("   - Please check the file format and content.")
            if not dry_run:
                db.session.rollback() # Откат, если сессия была изменена (хотя parse не меняет)
            return

        print("   - File parsed successfully.")
        
        # Выводим извлеченные метаданные для информации
        metadata = parsed_data.get('metadata', {})
        print("   - Extracted Metadata:")
        for key, value in metadata.items():
             print(f"     - {key}: {value}")
             
        if delete_only:
             # В режиме delete-only парсинг нужен только для получения ключевых данных для поиска
             print("\n---> DELETE ONLY mode enabled.")
             fgos_to_delete = None
             if metadata.get('direction_code') and metadata.get('education_level') and metadata.get('order_number') and metadata.get('order_date'):
                  try:
                       fgos_date_obj = datetime.datetime.strptime(metadata['order_date'], '%d.%m.%Y').date()
                       fgos_to_delete = db.session.query(FgosVo).filter_by(
                            direction_code=metadata['direction_code'],
                            education_level=metadata['education_level'],
                            number=metadata['order_number'],
                            date=fgos_date_obj
                       ).first()
                  except (ValueError, TypeError):
                        print(f"   - Could not parse date '{metadata['order_date']}' for lookup. Cannot perform delete.")
                        fgos_to_delete = None # Устанавливаем None, если дату не распарсили
                  except SQLAlchemyError as e:
                        print(f"   - Database error during lookup for delete: {e}")
                        db.session.rollback()
                        return
             else:
                  print("   - Missing identifying metadata for lookup. Cannot perform delete.")
             
             if fgos_to_delete:
                  if not dry_run:
                       print(f"   - Found existing FGOS (id: {fgos_to_delete.id}, code: {fgos_to_delete.direction_code}). Deleting...")
                       deleted = delete_fgos(fgos_to_delete.id, db.session)
                       if deleted:
                            print("   - FGOS deleted successfully.")
                       else:
                            print("   - Failed to delete FGOS (check logs).")
                  else:
                       print(f"   - DRY RUN: Found existing FGOS (id: {fgos_to_delete.id}). Would delete.")
             else:
                  print("   - No existing FGOS found matching identifying metadata. Nothing to delete.")

             print("---> FGOS import finished (delete only mode).\n")
             return # Выходим после удаления

        # 2. Сохранение данных в БД (только если не dry-run и не delete-only)
        if not dry_run:
            print("Saving data to database...")
            
            # Вызываем функцию сохранения данных
            # Передаем сессию явно
            saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=force)

            if saved_fgos is None:
                 print("\n!!! SAVE FAILED !!!")
                 print("   - Error occurred while saving FGOS data (check logs).")
                 # save_fgos_data уже откатил транзакцию при ошибке БД
            else:
                 print(f"\n---> FGOS from '{filename}' imported successfully with ID {saved_fgos.id}!\n")

        else:
            print("   - Skipping database save due to --dry-run flag.")
            print(f"---> DRY RUN for '{filename}' completed successfully (parsing passed).\n")


    except FileNotFoundError:
        print(f"\n!!! ERROR: File not found at '{filepath}' !!!")
    except ImportError as e:
        print(f"\n!!! ERROR: Missing dependency for reading PDF files: {e} !!!")
        print("   - Please ensure 'pdfminer.six' is installed.")
    except ValueError as e: # Ловим ошибки от parse_fgos_file
        print(f"\n!!! PARSING ERROR: {e} !!!")
        if not dry_run:
             db.session.rollback() # Откат, если сессия была изменена
    except Exception as e:
        if not dry_run:
            db.session.rollback()
            print("   - Database transaction might have been rolled back.")
        print(f"\n!!! UNEXPECTED ERROR during import: {e} !!!")
        print("   - Database transaction might have been rolled back.")
        traceback.print_exc()
