# filepath: competencies_matrix/logic/uk_pk_generation.py
import logging
import io
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy.orm import Session, selectinload
from sqlalchemy import cast, Integer

from maps.models import db as local_db
from ..models import Competency, Indicator, CompetencyType, FgosVo, LaborFunction, EducationalProgram, CompetencyEducationalProgram
from .competencies_indicators import create_competency, create_indicator
from ..parsing_utils import preprocess_text_for_llm

from .. import nlp
from pdfminer.high_level import extract_text

logger = logging.getLogger(__name__)

def process_uk_indicators_disposition_file(file_bytes: bytes, filename: str, education_level: str) -> Dict[str, Any]:
    """
    Processes a PDF disposition file.
    """
    logger.info(f"Processing UK indicators disposition file: {filename} for education level: {education_level}")
    
    try:
        raw_text_content = extract_text(io.BytesIO(file_bytes))
        cleaned_text_content = preprocess_text_for_llm(raw_text_content)
        
        parsed_disposition_data = nlp.parse_uk_indicators_disposition_with_llm(cleaned_text_content, education_level=education_level)

        if not parsed_disposition_data or not parsed_disposition_data.get('disposition_metadata'):
            raise ValueError("Не удалось извлечь метаданные из файла распоряжения.")

        result: Dict[str, Any] = {
            "disposition_metadata": parsed_disposition_data['disposition_metadata'],
            "filename": filename,
            "parsed_uk_competencies": parsed_disposition_data.get('uk_competencies_with_indicators', []),
            "applicable_fgos": [],
            "existing_uk_data_for_diff": {}
        }

        session = local_db.session
        fgos_query = session.query(FgosVo).filter(
            FgosVo.education_level == education_level
        ).order_by(FgosVo.date.desc())
        
        all_fgos_records_for_level = fgos_query.all()
        
        if not all_fgos_records_for_level:
            logger.warning(f"No FGOS found in DB for education_level='{education_level}'.")
            result["fgos_not_found_warnings"] = [f"Не найдены ФГОСы для уровня образования '{education_level}'. Убедитесь, что соответствующие ФГОС ВО загружены."]
            return result
        result["applicable_fgos"] = [fgos.to_dict() for fgos in all_fgos_records_for_level]

        uk_type = session.query(CompetencyType).filter_by(code='УК').first()
        if not uk_type:
            logger.warning("CompetencyType 'УК' not found. Cannot perform diff.")
            return result

        for fgos_record in all_fgos_records_for_level:
            existing_uk_competencies = session.query(Competency).options(
                selectinload(Competency.indicators)
            ).filter(
                Competency.fgos_vo_id == fgos_record.id,
                Competency.competency_type_id == uk_type.id
            ).all()

            uk_data_for_this_fgos = {}
            for uk_comp in existing_uk_competencies:
                uk_comp_dict = uk_comp.to_dict(rules=['-indicators'])
                uk_comp_dict['indicators'] = {ind.code: ind.to_dict() for ind in uk_comp.indicators}
                uk_data_for_this_fgos[uk_comp.code] = uk_comp_dict
            
            result["existing_uk_data_for_diff"][fgos_record.id] = uk_data_for_this_fgos

        logger.info(f"Found {len(all_fgos_records_for_level)} FGOS records for education_level='{education_level}'.")
        return result

    except ValueError as e:
        logger.error(f"Data validation or parsing error for disposition {filename}: {e}", exc_info=True)
        raise ValueError(f"Ошибка парсинга распоряжения: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке файла распоряжения: {e}", exc_info=True)
        raise Exception(f"Неожиданная ошибка при обработке файла распоряжения: {e}")

def _shift_competency_codes(
    session: Session, 
    fgos_id: int, 
    competency_type_id: int, 
    start_number: int, 
    prefix: str = 'УК-'
):
    """
    Shifts competency codes by +1, starting from the specified number.
    """
    competencies_to_shift = session.query(Competency).filter(
        Competency.fgos_vo_id == fgos_id,
        Competency.competency_type_id == competency_type_id,
        local_db.func.substring_index(Competency.code, '-', -1).cast(Integer) >= start_number
    ).order_by(
        local_db.func.substring_index(Competency.code, '-', -1).cast(Integer).desc()
    ).all()

    if not competencies_to_shift:
        logger.info(f"Сдвиг кодов для {prefix}{start_number} не требуется, т.к. компетенции не найдены.")
        return

    logger.info(f"Начинается сдвиг {len(competencies_to_shift)} компетенций, начиная с {prefix}{start_number}.")
    for comp in competencies_to_shift:
        try:
            current_num = int(comp.code.split('-')[-1])
            new_code = f"{prefix}{current_num + 1}"
            logger.info(f"Сдвиг: {comp.code} -> {new_code} (ID: {comp.id})")
            comp.code = new_code
            session.add(comp)
        except (ValueError, IndexError):
            logger.error(f"Не удалось распарсить код компетенции для сдвига: '{comp.code}'")
            continue
    session.flush()
    logger.info("Сдвиг кодов компетенций завершен.")

def save_uk_indicators_from_disposition(
    parsed_disposition_data: Dict[str, Any],
    filename: str,
    session: Session,
    fgos_ids: List[int],
    force_update_uk: bool = False,
    resolutions: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Saves/updates UK indicators from a disposition.
    """
    if resolutions is None:
        resolutions = {}

    logger.info(f"Сохранение индикаторов УК из {filename} для ФГОС ID: {fgos_ids}. Перезапись: {force_update_uk}. Решения: {resolutions}")

    summary = {
        "saved_uk": 0, "updated_uk": 0, "skipped_uk": 0,
        "saved_indicator": 0, "updated_indicator": 0, "skipped_indicator": 0,
        "shifted_uk": 0, "shifted_indicator": 0
    }

    try:
        fgos_records = session.query(FgosVo).filter(FgosVo.id.in_(fgos_ids)).all()
        if len(fgos_records) != len(fgos_ids):
            found_ids = {r.id for r in fgos_records}
            missing_ids = set(fgos_ids) - found_ids
            raise ValueError(f"Один или несколько ФГОС ВО не найдены в БД: ID={list(missing_ids)}.")

        uk_type = session.query(CompetencyType).filter_by(code='УК').first()
        if not uk_type:
            raise ValueError("Тип компетенции 'УК' не найден в БД.")

        disposition_meta = parsed_disposition_data.get('disposition_metadata', {})
        source_string = f"Распоряжение №{disposition_meta.get('number', 'N/A')} от {disposition_meta.get('date', 'N/A')}"

        for fgos_vo in fgos_records:
            logger.info(f"Обработка ФГОС ID: {fgos_vo.id} ({fgos_vo.direction_code})")

            if force_update_uk:
                logger.info(f"Принудительное обновление для ФГОС {fgos_vo.id}. Удаление существующих УК.")
                session.query(Competency).filter(
                    Competency.fgos_vo_id == fgos_vo.id,
                    Competency.competency_type_id == uk_type.id
                ).delete(synchronize_session='fetch')
                session.flush()

            for parsed_uk_data in parsed_disposition_data.get('uk_competencies_with_indicators', []):
                original_uk_code = parsed_uk_data.get('code')
                
                final_uk_code_resolution_key = f"uk_code_{original_uk_code}"
                final_uk_code = resolutions.get(final_uk_code_resolution_key, original_uk_code)
                
                if not final_uk_code:
                    logger.warning(f"Пропуск УК: код пустой после резолвинга для {original_uk_code}")
                    summary['skipped_uk'] += 1
                    continue
                
                use_old_name_resolution_key = f"uk_comp_{original_uk_code}_name"
                if resolutions.get(use_old_name_resolution_key) == 'use_old':
                    logger.info(f"Пропуск обновления названия для УК {original_uk_code} согласно решению пользователя.")
                    summary['skipped_uk'] += 1
                    existing_uk_comp = session.query(Competency).filter_by(code=original_uk_code, fgos_vo_id=fgos_vo.id, competency_type_id=uk_type.id).first()
                    if not existing_uk_comp:
                        logger.warning(f"Не удалось найти существующую УК {original_uk_code} для добавления индикаторов.")
                        continue
                    current_uk_comp = existing_uk_comp
                else:
                    uk_name = parsed_uk_data.get('name')
                    uk_category_name = parsed_uk_data.get('category_name')
                    if not uk_name:
                        logger.warning(f"Пропуск УК {final_uk_code}: отсутствует название.")
                        summary['skipped_uk'] += 1
                        continue

                    existing_uk_comp = session.query(Competency).filter_by(code=final_uk_code, fgos_vo_id=fgos_vo.id, competency_type_id=uk_type.id).first()
                    
                    if existing_uk_comp:
                        existing_uk_comp.name = uk_name
                        existing_uk_comp.category_name = uk_category_name
                        session.add(existing_uk_comp)
                        summary['updated_uk'] += 1
                        current_uk_comp = existing_uk_comp
                    else:
                        is_code_busy = session.query(Competency).filter_by(code=final_uk_code, fgos_vo_id=fgos_vo.id).count() > 0
                        if is_code_busy:
                            try:
                                start_num_to_shift = int(final_uk_code.split('-')[-1])
                                _shift_competency_codes(session, fgos_vo.id, uk_type.id, start_num_to_shift)
                                summary['shifted_uk'] += 1
                            except (ValueError, IndexError):
                                raise ValueError(f"Не удалось распарсить числовую часть кода '{final_uk_code}' для сдвига.")

                        current_uk_comp = Competency(
                            competency_type_id=uk_type.id, fgos_vo_id=fgos_vo.id,
                            code=final_uk_code, name=uk_name, category_name=uk_category_name
                        )
                        session.add(current_uk_comp)
                        summary['saved_uk'] += 1
                
                session.flush()

                for parsed_indicator_data in parsed_uk_data.get('indicators', []):
                    original_ind_code = parsed_indicator_data.get('code')
                    
                    final_ind_code_resolution_key = f"indicator_{original_uk_code}_{original_ind_code}_code"
                    final_ind_code = resolutions.get(final_ind_code_resolution_key, original_ind_code)
                    
                    if not final_ind_code:
                        logger.warning(f"Пропуск индикатора: код пустой для {original_ind_code}")
                        summary['skipped_indicator'] += 1
                        continue
                        
                    use_old_formulation_key = f"indicator_{original_uk_code}_{original_ind_code}_formulation"
                    if resolutions.get(use_old_formulation_key) == 'use_old':
                        logger.info(f"Пропуск обновления формулировки для индикатора {original_ind_code} согласно решению пользователя.")
                        summary['skipped_indicator'] += 1
                        continue
                        
                    indicator_formulation = parsed_indicator_data.get('formulation')
                    if not indicator_formulation:
                        summary['skipped_indicator'] += 1
                        continue
                    
                    existing_indicator = session.query(Indicator).filter_by(code=final_ind_code, competency_id=current_uk_comp.id).first()
                    
                    if existing_indicator:
                        existing_indicator.formulation = indicator_formulation
                        existing_indicator.source = source_string
                        session.add(existing_indicator)
                        summary['updated_indicator'] += 1
                    else:
                        is_ind_code_busy = session.query(Indicator).filter_by(code=final_ind_code, competency_id=current_uk_comp.id).count() > 0
                        if is_ind_code_busy:
                           logger.error(f"Код индикатора '{final_ind_code}' уже занят для компетенции {current_uk_comp.code}. Пропуск.")
                           summary['skipped_indicator'] += 1
                           continue
                           
                        new_indicator = Indicator(
                            competency_id=current_uk_comp.id, code=final_ind_code,
                            formulation=indicator_formulation, source=source_string
                        )
                        session.add(new_indicator)
                        summary['saved_indicator'] += 1

        return {"success": True, "message": "Индикаторы УК успешно обработаны.", "summary": summary}
    except Exception as e:
        logger.error(f"Error saving UK indicators from disposition: {e}", exc_info=True)
        session.rollback()
        raise e
    
def handle_pk_name_correction(raw_phrase: str) -> Dict[str, str]:
    """
    Handles PK name correction using NLP.
    """
    if not raw_phrase or not isinstance(raw_phrase, str):
        raise ValueError("Некорректная сырая фраза для коррекции.")
    
    try:
        corrected_name_data = nlp.correct_pk_name_with_llm(raw_phrase)
        return corrected_name_data
    except RuntimeError as e:
        logger.error(f"NLP correction failed: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка NLP при коррекции названия ПК: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_pk_name_correction: {e}", exc_info=True)
        raise RuntimeError(f"Неизвестная ошибка при коррекции названия ПК: {e}")

def handle_pk_ipk_generation(batch_tfs_data: List[Dict]) -> List[Dict]:
    """
    Handles batch generation of PK and IPK using NLP.
    """
    if not batch_tfs_data:
        raise ValueError("Необходимо выбрать Трудовые Функции для генерации.")
    
    try:
        generated_data = nlp.generate_pk_ipk_with_llm(batch_tfs_data)
        return generated_data
    except RuntimeError as e:
        logger.error(f"NLP generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка NLP при генерации ПК/ИПК: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_pk_ipk_generation: {e}", exc_info=True)
        raise RuntimeError(f"Неизвестная ошибка при генерации ПК/ИПК: {e}")

def batch_create_pk_and_ipk(data_list: List[Dict[str, Any]], session: Session) -> Dict:
    """
    Batch creation of PKs and their IPKs based on frontend data.
    """
    created_count = 0
    errors = []
    
    if not data_list:
        return {"success_count": 0, "error_count": 0, "errors": []}

    pk_type = session.query(CompetencyType).filter_by(code='ПК').first()
    if not pk_type:
        raise ValueError("Тип компетенции 'ПК' не найден в базе данных.")

    for item_data in data_list:
        try:
            pk_payload = {
                'code': item_data.get('pk_code'),
                'name': item_data.get('pk_name'),
                'competency_type_id': pk_type.id,
                'based_on_labor_function_id': item_data.get('tf_id')
            }
            existing_pk = session.query(Competency).filter_by(code=pk_payload['code'], competency_type_id=pk_type.id).first()
            if existing_pk:
                 raise Exception(f"Компетенция с кодом '{pk_payload['code']}' уже существует.")
                 
            new_pk = Competency(**pk_payload)
            session.add(new_pk)
            session.flush()

            educational_program_ids = item_data.get('educational_program_ids', [])
            if educational_program_ids:
                for ep_id in educational_program_ids:
                    ep = session.query(EducationalProgram).get(ep_id)
                    if ep:
                        assoc = CompetencyEducationalProgram(competency_id=new_pk.id, educational_program_id=ep_id)
                        session.add(assoc)
                    else:
                        logger.warning(f"ОП с ID {ep_id} не найдена. Пропуск привязки.")

            formulation = f"Знает: {item_data.get('ipk_znaet', 'Н/Д')}\nУмеет: {item_data.get('ipk_umeet', 'Н/Д')}\nВладеет: {item_data.get('ipk_vladeet', 'Н/Д')}"
            
            indicator_code = f"ИПК-{new_pk.code.replace('ПК-', '')}.1"
            existing_indicator = session.query(Indicator).filter_by(code=indicator_code, competency_id=new_pk.id).first()
            if existing_indicator:
                raise Exception(f"Индикатор с кодом '{indicator_code}' уже существует для этой компетенции.")

            ipk_payload = {
                'competency_id': new_pk.id,
                'code': indicator_code,
                'formulation': formulation,
                'source': f"ПС {item_data.get('ps_code', 'N/A')}",
                'selected_ps_elements_ids': item_data.get('selected_ps_elements_ids', {})
            }
            new_indicator = Indicator(**ipk_payload)
            session.add(new_indicator)
            
            created_count += 1
            
        except Exception as e:
            logger.error(f"Ошибка при пакетном создании для ПК {item_data.get('pk_code')}: {e}", exc_info=True)
            errors.append({'pk_code': item_data.get('pk_code'), 'error': str(e)})

    if errors:
        session.rollback()
        raise Exception(f"Обнаружены ошибки во время пакетного создания. Все изменения отменены. Подробности: {errors}")

    return {"success_count": created_count, "error_count": len(errors), "errors": errors}