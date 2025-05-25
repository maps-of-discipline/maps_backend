# filepath: cli_commands/fgos_import.py
import click
from flask.cli import with_appcontext
import os
import traceback
import datetime
import logging

from maps.models import db
from competencies_matrix.logic import save_fgos_data, delete_fgos, parse_fgos_file
from competencies_matrix.models import FgosVo 

logger = logging.getLogger(__name__)

@click.command(name='import-fgos')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force import/overwrite if FGOS with same identifying data exists.')
@click.option('--delete-only', is_flag=True, default=False,
              help='Only delete FGOS if it exists, do not import.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform read and validation without saving or deleting.')
@click.option('--debug-parser', is_flag=True, default=False,
              help='Enable DEBUG logging for the FGOS parser.')
@with_appcontext
def import_fgos_command(filepath, force, delete_only, dry_run, debug_parser):
    """
    Импортирует данные ФГОС ВО из PDF-файла, парсит и сохраняет в БД.
    Поиск существующего ФГОС производится по коду направления, уровню, номеру и дате приказа.

    FILEPATH: Путь к PDF файлу ФГОС для импорта.
    """
    parser_logger = logging.getLogger('competencies_matrix.parsers')
    original_parser_level = parser_logger.level
    if debug_parser:
        parser_logger.setLevel(logging.DEBUG)

    print(f"\n---> Starting FGOS import from: {filepath}")
    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved/deleted from the database. <<<")
    filename = os.path.basename(filepath)

    try:
        logger.info(f"Reading and parsing FGOS file: {filename}...")
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
        
        parsed_data = parse_fgos_file(file_bytes, filename)

        if not parsed_data:
            logger.error("\n!!! PARSING FAILED: parse_fgos_file returned None unexpectedly !!!")
            if not dry_run: db.session.rollback()
            return

        logger.info("   - File parsed successfully.")
        
        metadata = parsed_data.get('metadata', {})
        print("   - Extracted Metadata:")
        for key, value in metadata.items():
             print(f"     - {key}: {value}")
             
        print(f"   - Found {len(parsed_data.get('uk_competencies', []))} УК competencies.")
        print(f"   - Found {len(parsed_data.get('opk_competencies', []))} ОПК competencies.")
        print(f"   - Found {len(parsed_data.get('recommended_ps_codes', []))} recommended PS codes.")

        if delete_only:
             logger.info("\n---> DELETE ONLY mode enabled.")
             fgos_to_delete = None
             
             fgos_number = metadata.get('order_number')
             fgos_date = metadata.get('order_date')
             fgos_direction_code = metadata.get('direction_code')
             fgos_education_level = metadata.get('education_level')

             if fgos_number and fgos_date and fgos_direction_code and fgos_education_level:
                  try:
                       fgos_to_delete = db.session.query(FgosVo).filter_by(
                            number=fgos_number,
                            date=fgos_date,
                            direction_code=fgos_direction_code,
                            education_level=fgos_education_level
                       ).first()
                  except SQLAlchemyError as e:
                        logger.error(f"   - Database error during lookup for delete: {e}")
                        db.session.rollback()
                        return
             else:
                  logger.error("   - Missing identifying metadata from parsed file for lookup. Cannot perform delete.")
                  
             if fgos_to_delete:
                  if not dry_run:
                       logger.info(f"   - Found existing FGOS (id: {fgos_to_delete.id}, code: {fgos_to_delete.direction_code}). Deleting...")
                       with db.session.begin(): 
                            deleted = delete_fgos(fgos_to_delete.id, db.session) 
                       if deleted: logger.info("   - FGOS deleted successfully.")
                       else: logger.error("   - Failed to delete FGOS (check logs).")
                  else:
                       logger.info(f"   - DRY RUN: Found existing FGOS (id: {fgos_to_delete.id}). Would delete.")
             else:
                  logger.warning("   - No existing FGOS found matching identifying metadata. Nothing to delete.")

             logger.info("---> FGOS import finished (delete only mode).\n")
             return

        if not dry_run:
            logger.info("Saving data to database...")
            with db.session.begin(): 
                 saved_fgos = save_fgos_data(parsed_data, filename, db.session, force_update=force)
            
            if saved_fgos is None:
                 logger.error("\n!!! SAVE FAILED !!!")
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
    except ValueError as e:
        logger.error(f"\n!!! PARSING ERROR: {e} !!!")
        logger.error(f"   - Error occurred during parsing file '{filename}'.")
    except IntegrityError as e: 
        logger.error(f"\n!!! DATABASE INTEGRITY ERROR during import: {e.orig} !!!", exc_info=True)
        logger.error(f"   - An FGOS with the same identifying data (number, date, direction code, education level) already exists.")
    except Exception as e:
        logger.error(f"\n!!! UNEXPECTED ERROR during import: {e} !!!", exc_info=True)
    finally:
         parser_logger.setLevel(original_parser_level)