from .fgos_processing import (
    parse_fgos_file,
    save_fgos_data,
    get_fgos_list,
    get_fgos_details,
    delete_fgos
)
from .prof_standards import (
    search_prof_standards,
    handle_prof_standard_upload_parsing,
    save_prof_standard_data,
    get_prof_standards_list,
    get_prof_standard_details,
    delete_prof_standard,
    generate_prof_standard_excel_export_logic
)
from .aup_external import (
    get_external_db_engine,
    get_external_aups_list,
    get_external_aup_disciplines,
    import_aup_from_external_db
)
from .educational_programs import (
    get_educational_programs_list,
    get_program_details,
    create_educational_program,
    update_educational_program,
    delete_educational_program,
    check_aup_version
)
from .competencies_indicators import (
    get_all_competencies,
    get_competency_details,
    create_competency,
    update_competency,
    delete_competency,
    get_all_indicators,
    get_indicator_details,
    create_indicator,
    update_indicator,
    delete_indicator
)
from .matrix_operations import (
    get_matrix_for_aup,
    update_matrix_link
)
from .uk_pk_generation import (
    process_uk_indicators_disposition_file,
    save_uk_indicators_from_disposition,
    handle_pk_name_correction,
    handle_pk_ipk_generation,
    batch_create_pk_and_ipk
)