# filepath: cli_commands/parse_profstandard.py

import click
from flask.cli import with_appcontext
import os
import traceback
import logging

from sqlalchemy.exc import IntegrityError

from maps.models import db 
from competencies_matrix.logic.prof_standards import (
    save_prof_standard_data,
    handle_prof_standard_upload_parsing, 
    get_prof_standard_details, 
    delete_prof_standard 
)
from competencies_matrix.models import ProfStandard 

logger = logging.getLogger(__name__)

@click.command(name='parse-ps')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force save/overwrite if Professional Standard with the same code exists.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform parsing without saving to the database.')
@click.option('--delete-only', is_flag=True, default=False, 
              help='Only delete Professional Standard if it exists, do not import.')
@with_appcontext
def parse_ps_command(filepath, force, dry_run, delete_only):
    """
    Парсит файл Профессионального Стандарта (XML), извлекает структуру
    и сохраняет в БД.

    FILEPATH: Путь к файлу ПС для парсинга.
    """
    print(f"\n---> Starting Professional Standard parsing from: {filepath}")
    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved to the database. <<<")
    if delete_only:
        print("   >>> DELETE ONLY MODE ENABLEED: Only deletion will be attempted. <<<")
    
    filename = os.path.basename(filepath)

    try:
        print(f"Parsing file: {filename}...")
        parse_result = handle_prof_standard_upload_parsing(open(filepath, 'rb').read(), filename)

        if not parse_result['success']:
             print(f"\n!!! PARSING FAILED: {parse_result['error']} !!!")
             return 

        parsed_data = parse_result.get('parsed_data')
        if not parsed_data or not parsed_data.get('code') or not parsed_data.get('name'):
             print("\n!!! PARSING FAILED or incomplete: Could not extract code/name after successful parse. Aborting. !!!")
             logger.error(f"Parsing successful for {filename}, but essential metadata (code/name) missing.")
             return

        print("   - File parsed successfully.")
        print(f"   - Found PS Code: {parsed_data.get('code')}")
        print(f"   - Found PS Name: {parsed_data.get('name')}")
        
        otf_count = len(parsed_data.get('generalized_labor_functions', []))
        tf_count = sum(len(otf.get('labor_functions', [])) for otf in parsed_data.get('generalized_labor_functions', [])) if otf_count > 0 else 0
        print(f"   - Found {otf_count} ОТФ and {tf_count} ТФ.")

        if delete_only:
            logger.info("Delete only mode enabled. Attempting to delete PS...")
            ps_code_to_delete = parsed_data.get('code')
            if not ps_code_to_delete:
                logger.error("Could not determine PS code for deletion from parsed data. Aborting delete.")
                return

            try:
                with db.session.begin():
                    existing_ps = db.session.query(ProfStandard).filter_by(code=ps_code_to_delete).first()
                    if existing_ps:
                        logger.info(f"Found existing PS (ID: {existing_ps.id}, Code: {existing_ps.code}). Deleting...")
                        deleted_success = delete_prof_standard(existing_ps.id, db.session) 
                        if deleted_success:
                            print(f"   - Professional Standard '{ps_code_to_delete}' deleted successfully.")
                        else:
                            print(f"   - Failed to delete Professional Standard '{ps_code_to_delete}'.")
                            logger.error(f"Failed to delete PS {ps_code_to_delete} via logic.")
                    else:
                        print(f"   - Professional Standard '{ps_code_to_delete}' not found in DB. Nothing to delete.")
                        logger.warning(f"PS {ps_code_to_delete} not found for deletion.")
            except Exception as e:
                print(f"\n!!! ERROR during delete operation: {e} !!!")
                logger.error(f"Error during PS delete operation: {e}", exc_info=True)
            finally:
                logger.info("---> Professional Standard import finished (delete only mode).\n")
            return

        if not dry_run:
            print("Saving parsed structure to database...")
            try:
                with db.session.begin(): 
                    saved_ps = save_prof_standard_data( 
                        parsed_data=parsed_data,
                        filename=filename,
                        session=db.session, 
                        force_update=force
                    )

                if saved_ps:
                    print(f"   - Structure for PS '{saved_ps.code}' saved/updated successfully (ID: {saved_ps.id}).")
                    print(f"---> Professional Standard from '{filename}' processed successfully!\n")
                else:
                    print("\n!!! SAVE FAILED: Error occurred while saving parsed structure. Check logs. !!!")

            except IntegrityError as e: 
                print(f"\n!!! DATABASE INTEGRITY ERROR during save: {e.orig} !!!")
                print(f"   - Professional Standard with code '{parsed_data.get('code')}' already exists and --force was not used.")
                logger.error(f"IntegrityError during PS save for {filename}: {e.orig}", exc_info=True)
            except Exception as e: 
                print(f"\n!!! SAVE FAILED during transaction: {e} !!!")
                print("   - Database transaction rolled back.")
                logger.error(f"Error during PS save operation for {filename}: {e}", exc_info=True)
                traceback.print_exc()

        else:
            print("   - Skipping database save due to --dry-run flag.")
            print(f"---> DRY RUN for '{filename}' completed successfully (parsing passed).\n")

    except FileNotFoundError:
        print(f"\n!!! ERROR: File not found at '{filepath}' !!!")
        logger.error(f"File not found: {filepath}")
    except ImportError as e:
        print(f"\n!!! ERROR: Missing dependency for parsing: {e} !!!")
        print("   - Please ensure 'beautifulsoup4', 'lxml', 'python-docx', 'markdownify', 'chardet', 'pdfminer.six' are installed.")
        logger.error(f"Missing import for parsing: {e}")
    except Exception as e: 
        print(f"\n!!! UNEXPECTED ERROR during processing: {e} !!!")
        logger.error(f"Unexpected error during PS parsing/processing for {filepath}: {e}", exc_info=True)
        traceback.print_exc()

    finally:
         pass