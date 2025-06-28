# filepath: cli_commands/fgos_import.py
import click
from flask.cli import with_appcontext
import os
import traceback
import datetime
import logging

from maps.models import db
from competencies_matrix.logic.fgos_processing import save_fgos_data, delete_fgos, parse_fgos_file
from competencies_matrix.models import FgosVo
from competencies_matrix.parsing_utils import parse_date_string
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
    loggers_to_modify = {
        'competencies_matrix.fgos_parser': logging.DEBUG if debug_parser else logging.INFO,
        'competencies_matrix.nlp_logic': logging.DEBUG if debug_parser else logging.INFO,
        'pdfminer': logging.WARNING,
    }
    original_levels = {name: logging.getLogger(name).level for name in loggers_to_modify}
    
    for name, level in loggers_to_modify.items():
        logging.getLogger(name).setLevel(level)

    click.echo(f"\n---> Starting FGOS import from: {filepath}")
    if dry_run:
        click.echo("   >>> DRY RUN MODE ENABLED: No changes will be saved/deleted from the database. <<<")
    
    filename = os.path.basename(filepath)

    try:
        logger.info(f"Reading and parsing FGOS file: {filename}...")
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
        
        parsed_data = parse_fgos_file(file_bytes, filename)

        if not parsed_data or not parsed_data.get('metadata'):
            logger.error("\n!!! PARSING FAILED: parse_fgos_file returned insufficient data. !!!")
            if not dry_run: db.session.rollback()
            return

        logger.info("   - File parsed successfully.")
        
        metadata = parsed_data.get('metadata', {})
        click.echo("   - Extracted Metadata:")
        for key, value in metadata.items():
             click.echo(f"     - {key}: {value}")
             
        click.echo(f"   - Found {len(parsed_data.get('uk_competencies', []))} УК competencies.")
        click.echo(f"   - Found {len(parsed_data.get('opk_competencies', []))} ОПК competencies.")
        click.echo(f"   - Found {len(parsed_data.get('recommended_ps', []))} recommended PS.")

        # --- Common logic for delete and save ---
        number = metadata.get('order_number')
        date_str = metadata.get('order_date')
        direction_code = metadata.get('direction_code')
        education_level = metadata.get('education_level')
        
        date_obj = None
        if isinstance(date_str, str):
            date_obj = parse_date_string(date_str)
        elif isinstance(date_str, (datetime.datetime, datetime.date)):
            date_obj = date_str

        if not all([number, date_obj, direction_code, education_level]):
            logger.error("   - Missing identifying metadata from parsed file for lookup. Cannot proceed.")
            return
        # --- End of common logic ---

        if delete_only:
             logger.info("\n---> DELETE ONLY mode enabled.")
             try:
                fgos_to_delete = db.session.query(FgosVo).filter_by(
                    number=number,
                    date=date_obj,
                    direction_code=direction_code,
                    education_level=education_level
                ).first()

                if fgos_to_delete:
                    if not dry_run:
                        logger.info(f"   - Found existing FGOS (id: {fgos_to_delete.id}). Deleting...")
                        with db.session.begin():
                            deleted = delete_fgos(fgos_to_delete.id, db.session)
                        if deleted:
                            logger.info("   - FGOS deleted successfully.")
                        else:
                            logger.error("   - Failed to delete FGOS (check logs).")
                    else:
                        logger.info(f"   - DRY RUN: Found existing FGOS (id: {fgos_to_delete.id}). Would delete.")
                else:
                    logger.warning("   - No existing FGOS found matching identifying metadata. Nothing to delete.")

             except SQLAlchemyError as e:
                logger.error(f"   - Database error during lookup for delete: {e}")
                db.session.rollback()
                return
             
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
        db.session.rollback()
        logger.error(f"\n!!! DATABASE INTEGRITY ERROR during import: {e.orig} !!!", exc_info=True)
        logger.error(f"   - An FGOS with the same identifying data (number, date, direction code, education level) may already exist.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"\n!!! UNEXPECTED ERROR during import: {e} !!!", exc_info=True)
    finally:
        for name, level in original_levels.items():
            logging.getLogger(name).setLevel(level)