# filepath: cli_commands/import_aup.py
"""
Flask CLI команда для импорта данных Академического Учебного Плана (АУП)
из Excel-файла (.xlsx), созданного выгрузкой из 1С.

Эта команда читает данные из указанного Excel-файла (с листами 'Лист1' и 'Лист2'),
проверяет их на соответствие ожидаемой структуре и базовым правилам
(наличие заголовков, отсутствие пустых ячеек, целочисленность ZET и т.д.),
и, если проверка прошла успешно, сохраняет данные в базу данных,
создавая или обновляя записи в таблицах AupInfo, AupData и связанных справочниках.

Основные возможности:
- Чтение Excel-файлов с двумя листами ('Лист1', 'Лист2').
- Валидация структуры и данных перед сохранением.
- Возможность принудительной перезаписи существующего АУП (--force).
- Опция попытки заполнения пустых модулей на основе использования дисциплин (--fill-null-modules).
- Опция пропуска проверок целочисленности ZET и общей суммы ZET (--skip-integrity-check, --skip-sum-check).
- Режим "пробного запуска" (`--dry-run`), который выполняет чтение и валидацию, но не сохраняет данные в БД.

Пример использования:
    # Простой импорт
    flask import-aup "path/to/aup.xlsx"

    # Импорт с перезаписью существующего АУП
    flask import-aup "path/to/aup.xlsx" --force

    # Пробный запуск (чтение и валидация без сохранения)
    flask import-aup "path/to/aup.xlsx" --dry-run

    # Импорт с пропуском проверки суммы ZET
    flask import-aup "path/to/aup.xlsx" --skip-sum-check --force
"""
import click
from flask.cli import with_appcontext
import os
import traceback

# --- Импортируем необходимые компоненты ---
from maps.logic.read_excel import read_excel
from maps.logic.excel_check import ExcelValidator
from maps.logic.save_excel_data import save_excel_data, delete_aup_by_num
from maps.models import db
import logging

logger = logging.getLogger(__name__)


@click.command(name='import-aup')
@click.argument('filepath', type=click.Path(exists=True, dir_okay=False))
@click.option('--force', is_flag=True, default=False,
              help='Force import even if AUP with the same number exists (will replace).')
@click.option('--fill-null-modules', is_flag=True, default=False,
              help='Try to fill null modules based on common discipline usage.')
@click.option('--skip-integrity-check', is_flag=True, default=False,
              help='Skip ZET integrity check.')
@click.option('--skip-sum-check', is_flag=True, default=False,
              help='Skip total ZET sum check.')
@click.option('--dry-run', is_flag=True, default=False,
              help='Perform read and validation without saving to the database.')
@with_appcontext
def import_aup_command(filepath, force, fill_null_modules, skip_integrity_check, skip_sum_check, dry_run):
    """
    Импортирует данные Академического Учебного Плана (АУП) из Excel-файла (.xlsx).

    FILEPATH: Путь к файлу Excel для импорта.
    """
    print(f"\n---> Starting AUP import from: {filepath}")
    if dry_run:
        print("   >>> DRY RUN MODE ENABLED: No changes will be saved to the database. <<<")
    filename = os.path.basename(filepath)

    # Формируем словарь опций для валидатора и сохранения
    options = {
        "forced_upload": force, # Принудительная загрузка
        "checkboxIntegralityModel": not skip_integrity_check,
        "checkboxSumModel": not skip_sum_check,
        "checkboxFillNullModulesModel": fill_null_modules
    }

    try:
        # 1. Чтение Excel файла
        print(f"Reading Excel file: {filename}...")
        with open(filepath, 'rb') as f:
            header_df, data_df = read_excel(f)
        print("   - Excel file read successfully.")

        # 2. Валидация данных
        print("Validating data...")
        errors = ExcelValidator.validate(options, header_df, data_df)

        if errors:
            print("\n!!! VALIDATION FAILED !!!")
            for error in errors:
                print(f"  - Error: {error.get('message', 'Unknown validation error')}")
                if 'cells' in error:
                    print(f"    Affected cells: {', '.join(error['cells'])}")
                if 'aup' in error and error['message'].startswith("Учебный план №"):
                    print(f"    Tip: Use the --force flag to overwrite existing AUP '{error['aup']}'.")
            print("\nImport aborted due to validation errors.")
            return

        print("   - Validation successful.")

        if force and not dry_run:
            # Get AUP number from header DataFrame
            aup_num = None
            for idx, row in header_df.iterrows():
                if row['Наименование'] == 'Номер АУП':
                    aup_num = row['Содержание']
                    break
                
            logger.info(f"Force flag enabled. Attempting to delete existing AUP with number: {aup_num}")
            # Передаем сессию в функцию удаления
            deleted = delete_aup_by_num(aup_num, db.session)
            if deleted:
                logger.info(f"   - Existing AUP deleted successfully.")
            else:
                # Если AUP не найден при удалении, это не ошибка, просто он не существовал
                logger.warning(f"   - AUP not found for deletion (it might not have existed).")

        # 3. Сохранение данных в БД (только если не dry-run)
        if not dry_run:
            print("Saving data to database...")
            # --- Вызов save_excel_data в рамках транзакции ---
            save_excel_data(
                filename=filename,
                header=header_df,
                data=data_df,
                use_other_modules=fill_null_modules,
                session=db.session
            )
            db.session.commit()  # Финальный коммит здесь
            print("   - Data saved successfully.")
            print(f"---> AUP from '{filename}' imported successfully!\n")
        else:
            print("   - Skipping database save due to --dry-run flag.")
            print(f"---> DRY RUN for '{filename}' completed successfully (validation passed).\n")

    except FileNotFoundError:
        print(f"\n!!! ERROR: File not found at '{filepath}' !!!")
    except ImportError as e:
        print(f"\n!!! ERROR: Missing dependency for reading Excel files: {e} !!!")
        print("   - Please ensure 'openpyxl' and potentially 'pyxlsb' or 'calamine' (for .xlsb/.xlsm) are installed.")
    except KeyError as e:
        print(f"\n!!! ERROR: Missing expected column or sheet in Excel file: {e} !!!")
        print(
            f"   - Please check the structure of '{filename}'. It must contain 'Лист1' и 'Лист2' с корректными заголовками.")
        if not dry_run:
            db.session.rollback()  # Откат при ключевой ошибке
    except Exception as e:
        if not dry_run:
            db.session.rollback()
            print("   - Database transaction rolled back.")
        print(f"\n!!! UNEXPECTED ERROR during import: {e} !!!")
        print("   - Database transaction might have been rolled back.")
        traceback.print_exc()