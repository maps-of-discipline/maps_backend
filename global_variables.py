from maps.models import (
    D_Blocks, D_Part, D_ControlType, D_EdIzmereniya,
    D_Period, D_TypeRecord, D_Modules, Groups
)

# Константы для имен моделей и полей
MODEL_BLOCKS = D_Blocks
MODEL_PART = D_Part
MODEL_PERIOD = D_Period
MODEL_CONTROL_TYPE = D_ControlType
MODEL_ED_IZMERENIYA = D_EdIzmereniya
MODEL_TYPE_RECORD = D_TypeRecord
MODEL_MODULES = D_Modules
MODEL_GROUPS = Groups


def setGlobalVariables(app, blocks, blocks_r, period, period_r, control_type, control_type_r, ed_izmereniya,
                       ed_izmereniya_r, chast, chast_r, type_record, type_record_r):
    with app.app_context():

        blocks_q = MODEL_BLOCKS.query.all()
        for row in blocks_q:
            blocks[row.title] = row.id
            blocks_r[row.id] = row.title

        chast_q = MODEL_PART.query.all()
        for row in chast_q:
            chast[row.title] = row.id
            chast_r[row.id] = row.title

        period_q = MODEL_PERIOD.query.all()
        for row in period_q:
            period[row.title] = row.id
            period_r[row.id] = row.title

        control_type_q = MODEL_CONTROL_TYPE.query.all()
        for row in control_type_q:
            control_type[row.title] = row.id
            control_type_r[row.id] = row.title

        ed_izmereniya_q = MODEL_ED_IZMERENIYA.query.all()
        for row in ed_izmereniya_q:
            ed_izmereniya[row.title] = row.id
            ed_izmereniya_r[row.id] = row.title

        type_record_q = MODEL_TYPE_RECORD.query.all()
        for row in type_record_q:
            type_record[row.title] = row.id
            type_record_r[row.id] = row.title


def addGlobalVariable(db, model, value):
    row = model(title=value)
    db.session.add(row)
    db.session.commit()

    return row.id


def getModuleId(db, value):
    module = MODEL_MODULES.query.filter(MODEL_MODULES.title == value).first()
    if module is None:
        row = MODEL_MODULES(title=value)
        db.session.add(row)
        db.session.commit()

        return row.id
    return module.id


def getGroupId(db, value):
    group = MODEL_GROUPS.query.filter(MODEL_GROUPS.name_group == value).first()
    if group is None:
        row = MODEL_GROUPS(name_group=value, color='#f5f5f5')
        db.session.add(row)
        db.session.commit()

        return row.id_group
    return group.id_group
