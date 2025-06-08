from datetime import datetime

import pandas as pd
from sqlalchemy import desc, inspect

from maps.logic.tools import timeit, prepare_shifr
from maps.models import (
    AupData, 
    AupInfo, 
    NameOP, 
    SprDegreeEducation, 
    SprFormEducation, 
    SprFaculty, 
    Department, 
    db,
    Revision, 
    ChangeLog,
    D_EdIzmereniya
)


def update_field(el: AupData, field: str, value: any) -> ChangeLog | None:
    """
        Функция для записи изменений в таблицу с логом.
    """
    old_value = el.__getattribute__(field)

    if value == old_value:
        return None
    setattr(el, field, value)

    log: ChangeLog = ChangeLog()
    log.model = el.__class__.__name__
    log.field = field
    log.row_id = inspect(el).identity[0] if inspect(el).identity else None
    log.old = old_value
    log.new = value

    return log


def update_fields(aup_data: AupData, discipline: dict, load: dict) -> list[ChangeLog | None]:
    """
        Функция для обновления полей 1 записи таблицы AupData
    """
    # Get measurement unit IDs based on their names
    hour_unit = D_EdIzmereniya.query.filter_by(title="час").first().id
    zet_unit = D_EdIzmereniya.query.filter_by(title="ЗЕТ").first().id

    if load['amount_type'] == 'hour':
        zet = int((load['amount'] / 18) * 100)
        amount_type_id = hour_unit
    else:
        zet = int((load['amount'] * 1.5) * 100)
        amount_type_id = zet_unit

    return list(filter(bool, [
        update_field(aup_data, 'id_group', discipline['id_group']),
        update_field(aup_data, 'id_block', int(discipline['id_block'])),
        update_field(aup_data, 'shifr', prepare_shifr(discipline['shifr'])),
        update_field(aup_data, 'id_part', discipline['id_part']),
        update_field(aup_data, 'id_module', discipline['id_module']),
        update_field(aup_data, 'id_period', discipline['num_col'] + 1),
        update_field(aup_data, 'num_row', discipline['num_row']),
        update_field(aup_data, 'id_type_record', discipline['id_type_record']),
        update_field(aup_data, 'amount', load['amount'] * 100),
        update_field(aup_data, 'id_edizm', amount_type_id),
        update_field(aup_data, 'id_type_control', load['control_type_id']),
        update_field(aup_data, 'id_discipline', discipline['id_discipline']),
        update_field(aup_data, '_discipline', discipline['discipline']),
        update_field(aup_data, 'zet', zet),
    ]))


def create_changes_revision(user_id: int, aup_info_id: int, changes: list[ChangeLog]) -> None:
    """
        Функция для создания Ревизии изменений.
    """
    # Поиск последней ревизии по дате, где значение isActual == True
    last_revision = db.session.query(Revision).filter_by(isActual=True, aup_id=aup_info_id).first()
    if last_revision:
        # Последняя актуальная ревизия перестаёт быть актуальной  
        last_revision.isActual = False
        db.session.commit()

    revision = Revision(
        title="",
        date=datetime.now(),
        isActual=True,
        user_id=user_id,
        aup_id=aup_info_id,
    )

    db.session.add(revision)
    db.session.commit()
    for i in range(len(changes)):
        changes[i].revision_id = revision.id

    db.session.bulk_save_objects(changes)