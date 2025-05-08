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

# Настройка логирования для этого модуля
logger = logging.getLogger(__name__)
# Уровень логирования для CLI можно настроить здесь или в основном конфиге Flask
# logger.setLevel(logging.INFO)

@click.command(name='import-fgos')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force import/overwrite if FGOS with same identifying data exists.')
@click.option('--delete-only', is_flag=True, default=False,
              help='Only delete FGOS if it exists, do not import.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform read and validation without saving or deleting.')
@click.option('--debug-parser', is_flag=True, default=False,
              help='Enable DEBUG logging for the FGOS parser.') # Новый флаг для отладки парсера
@with_appcontext
def import_fgos_command(filepath, force, delete_only, dry_run, debug_parser):
    """
    Импортирует данные ФГОС ВО из PDF-файла, парсит и сохраняет в БД.
    Поиск существующего ФГОС производится по коду направления, уровню, номеру и дате приказа.

    FILEPATH: Путь к PDF файлу ФГОС для импорта.
    """
    # Временно повышаем уровень логирования для парсера, если включен флаг отладки
    parser_logger = logging.getLogger('competencies_matrix.fgos_parser')
    original_parser_level = parser_logger.level
    if debug_parser:
        parser_logger.setLevel(logging.DEBUG)


    print(f"\n---> Starting FGOS import from: {filepath}")
    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved/deleted from the database. <<<")
    filename = os.path.basename(filepath)

    try:
        # 1. Чтение и парсинг Excel файла
        logger.info(f"Reading and parsing FGOS file: {filename}...")
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
        
        # Вызываем парсер. Ошибки парсинга (ValueError) перехватываются ниже.
        parsed_data = parse_fgos_file(file_bytes, filename)

        # Если парсинг завершился, но данные пустые (парсинг вернул None, хотя по логике не должен)
        if not parsed_data:
            logger.error("\n!!! PARSING FAILED UNEXPECTEDLY: parse_fgos_file returned None !!!")
            logger.error(f"   - This indicates an issue where the parser didn't raise an exception but returned empty data.")
            logger.error("   - Please check the parser logic and the input file.")
            if not dry_run:
                db.session.rollback()
            return


        logger.info("   - File parsed successfully.")
        
        # Выводим извлеченные метаданные для информации
        metadata = parsed_data.get('metadata', {})
        print("   - Extracted Metadata:")
        for key, value in metadata.items():
             print(f"     - {key}: {value}")
             
        # Выводим количество найденных компетенций/индикаторов
        print(f"   - Found {len(parsed_data.get('uk_competencies', []))} УК competencies.")
        print(f"   - Found {len(parsed_data.get('opk_competencies', []))} ОПК competencies.")
        total_indicators = sum(len(c.get('indicators', [])) for c in parsed_data.get('uk_competencies', []) + parsed_data.get('opk_competencies', []))
     #    print(f"   - Found {total_indicators} indicators.")
        print(f"   - Found {len(parsed_data.get('recommended_ps_codes', []))} recommended PS codes.")


        if delete_only:
             # В режиме delete-only парсинг нужен только для получения ключевых данных для поиска
             logger.info("\n---> DELETE ONLY mode enabled.")
             fgos_to_delete = None
             
             # Проверяем наличие всех ключевых метаданных для поиска
             if metadata.get('direction_code') and metadata.get('education_level') and metadata.get('order_number') and metadata.get('order_date'):
                  try:
                       # Пытаемся распарсить дату для поиска в БД
                       fgos_date_obj = datetime.datetime.strptime(metadata['order_date'], '%d.%m.%Y').date()
                       fgos_to_delete = db.session.query(FgosVo).filter_by(
                            direction_code=metadata['direction_code'],
                            education_level=metadata['education_level'],
                            number=metadata['order_number'],
                            date=fgos_date_obj
                       ).first()
                  except (ValueError, TypeError):
                        logger.error(f"   - Could not parse date '{metadata['order_date']}' from parsed metadata for lookup. Cannot perform delete.")
                        fgos_to_delete = None # Устанавливаем None, если дату не распарсили
                  except SQLAlchemyError as e:
                        logger.error(f"   - Database error during lookup for delete: {e}")
                        db.session.rollback()
                        # Восстанавливаем уровень логирования парсера перед выходом
                        parser_logger.setLevel(original_parser_level)
                        return
             else:
                  logger.error("   - Missing identifying metadata from parsed file for lookup. Cannot perform delete.")
                  
             if fgos_to_delete:
                  if not dry_run:
                       logger.info(f"   - Found existing FGOS (id: {fgos_to_delete.id}, code: {fgos_to_delete.direction_code}). Deleting...")
                       deleted = delete_fgos(fgos_to_delete.id, db.session) # delete_fgos управляет своей транзакцией
                       if deleted:
                            logger.info("   - FGOS deleted successfully.")
                       else:
                            logger.error("   - Failed to delete FGOS (check logs).")
                  else:
                       logger.info(f"   - DRY RUN: Found existing FGOS (id: {fgos_to_delete.id}). Would delete.")
             else:
                  logger.warning("   - No existing FGOS found matching identifying metadata. Nothing to delete.")

             logger.info("---> FGOS import finished (delete only mode).\n")
             # Восстанавливаем уровень логирования парсера перед выходом
             parser_logger.setLevel(original_parser_level)
             return # Выходим после удаления

        # 2. Сохранение данных в БД (только если не dry-run и не delete-only)
        if not dry_run:
            logger.info("Saving data to database...")
            
            # Вызываем функцию сохранения данных. save_fgos_data управляет своей транзакцией.
            saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=force)

            if saved_fgos is None:
                 logger.error("\n!!! SAVE FAILED !!!")
                 logger.error("   - Error occurred while saving FGOS data (check logs from save_fgos_data).")
                 # save_fgos_data уже откатил транзакцию при ошибке БД
            else:
                 logger.info(f"\n---> FGOS from '{filename}' imported successfully with ID {saved_fgos.id}!\n")

        else:
            logger.info("   - Skipping database save due to --dry-run flag.")
            logger.info(f"---> DRY RUN for '{filename}' completed successfully (parsing passed).\n")

    except FileNotFoundError:
        logger.error(f"\n!!! ERROR: File not found at '{filepath}' !!!")
    except ImportError as e:
        logger.error(f"\n!!! ERROR: Missing dependency for reading PDF files: {e} !!!")
        logger.error("   - Please ensure 'pdfminer.six' is installed.")
    except ValueError as e: # Ловим специфичные ошибки от parse_fgos_file (например, "Не удалось извлечь...")
        logger.error(f"\n!!! PARSING ERROR: {e} !!!")
        logger.error(f"   - Error occurred during parsing file '{filename}'.")
        if not dry_run:
             db.session.rollback() # Откат, если сессия была изменена
    except Exception as e:
        if not dry_run:
            db.session.rollback()
            logger.error("   - Database transaction might have been rolled back.")
        logger.error(f"\n!!! UNEXPECTED ERROR during import: {e} !!!", exc_info=True)
        logger.error(f"   - Database transaction might have been rolled back.")
        # traceback.print_exc() # Вывод traceback уже включен в exc_info=True
    finally:
         # Восстанавливаем уровень логирования парсера после выполнения команды
         parser_logger.setLevel(original_parser_level)