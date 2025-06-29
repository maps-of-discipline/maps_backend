import logging
import io
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy.orm import Session, selectinload
from sqlalchemy import cast, Integer

from maps.models import db as local_db
from ..models import Competency, Indicator, CompetencyType, FgosVo, LaborFunction, EducationalProgram
from .competencies_indicators import create_competency, create_indicator

from .. import nlp
from pdfminer.high_level import extract_text

logger = logging.getLogger(__name__)

def process_uk_indicators_disposition_file(file_bytes: bytes, filename: str, education_level: str) -> Dict[str, Any]:
    """
    Обрабатывает PDF-файл распоряжения.
    Принимает education_level для фильтрации запроса к NLP и поиска ФГОС.
    """
    logger.info(f"Processing UK indicators disposition file: {filename} for education level: {education_level}")
    
    try:
        text_content = extract_text(io.BytesIO(file_bytes))
        parsed_disposition_data = nlp.parse_uk_indicators_disposition_with_llm(text_content, education_level=education_level)

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
    Сдвигает номера кодов компетенций на +1, начиная с указанного номера.
    Например, при вставке новой УК-7, старая УК-7 -> УК-8, УК-8 -> УК-9 и т.д.
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
    Сохраняет/обновляет индикаторы УК из распоряжения.
    1. Уважает 'resolutions' для выбора "старой" формулировки.
    2. Использует отредактированные коды из 'resolutions'.
    3. Выполняет сдвиг кодов существующих УК/ИУК при необходимости.
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
    Обрабатывает запрос на коррекцию имени ПК с использованием NLP.
    """
    if not raw_phrase or not isinstance(raw_phrase, str):
        raise ValueError("Некорректная сырая фраза для коррекции.")
    
    try:
        corrected_name = nlp.correct_pk_name_with_llm(raw_phrase)
        return corrected_name
    except RuntimeError as e:
        logger.error(f"NLP correction failed: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка NLP при коррекции названия ПК: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_pk_name_correction: {e}", exc_info=True)
        raise RuntimeError(f"Неизвестная ошибка при коррекции названия ПК: {e}")

def handle_pk_ipk_generation(
    selected_tfs_data: List[Dict],
    selected_zun_elements: Dict[str, List[Dict]]
) -> Dict[str, Any]:
    """
    Обрабатывает запрос на генерацию ПК и ИПК с использованием NLP.
    """
    if not selected_tfs_data and not selected_zun_elements:
        raise ValueError("Необходимо выбрать Трудовые Функции или их элементы для генерации.")
    
    try:
        generated_data = nlp.generate_pk_ipk_with_llm(selected_tfs_data, selected_zun_elements)
        return generated_data
    except RuntimeError as e:
        logger.error(f"NLP generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Ошибка NLP при генерации ПК/ИПК: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_pk_ipk_generation: {e}", exc_info=True)
        raise RuntimeError(f"Неизвестная ошибка при генерации ПК/ИПК: {e}")

def batch_create_pk_and_ipk(data_list: List[Dict[str, Any]], session: Session) -> Dict:
    created_count = 0
    errors = []
    for item_data in data_list:
        try:
            # Логика из create_competency
            pk_payload = {
                'code': item_data.get('pk_code'),
                'name': item_data.get('pk_name'),
                'type_code': 'ПК',
                'based_on_labor_function_id': item_data.get('tf_id')
            }
            new_pk = create_competency(pk_payload, session)
            session.flush()

            formulation = f"Знает: {item_data.get('ipk_znaet')}\\nУмеет: {item_data.get('ipk_umeet')}\\nВладеет: {item_data.get('ipk_vladeet')}"
            ipk_payload = {
                'competency_id': new_pk.id,
                'code': f"ИПК-{new_pk.code.replace('ПК-', '')}.1",
                'formulation': formulation,
                'source': f"ПС {item_data.get('ps_code')}"
            }
            create_indicator(ipk_payload, session)
            created_count += 1
        except Exception as e:
            errors.append({'pk_code': item_data.get('pk_code'), 'error': str(e)})

    if errors:
        raise Exception(f"Завершено с ошибками. Успешно: {created_count}, Ошибки: {len(errors)}. Подробности: {errors}")

    return {"success_count": created_count, "error_count": len(errors), "errors": errors}