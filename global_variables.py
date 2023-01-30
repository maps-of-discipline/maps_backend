from models import D_Blocks, D_Chast, D_ControlType, D_EdIzmereniya, D_Period, D_TypeRecord, D_Modules

def setGlobalVariables(app, blocks, period, control_type, ed_izmereniya, chast, type_record):
    with app.app_context():

        blocks_q = D_Blocks.query.all()
        for row in blocks_q:
            blocks[row.title] = row.id

        chast_q = D_Chast.query.all()
        for row in chast_q:
            chast[row.title] = row.id

        period_q = D_Period.query.all()
        for row in period_q:
            period[row.title] = row.id

        control_type_q = D_ControlType.query.all()
        for row in control_type_q:
            control_type[row.title] = row.id
        
        ed_izmereniya_q = D_EdIzmereniya.query.all()
        for row in ed_izmereniya_q:
            ed_izmereniya[row.title] = row.id

        type_record_q = D_TypeRecord.query.all()
        for row in type_record_q:
            type_record[row.title] = row.id


def addGlobalVariable(db, type, value):
    
    row = type(title=value)
    db.session.add(row)
    db.session.commit()
    
    return row.id

def getModuleId(db, value):
    module = D_Modules.query.filter(D_Modules.title == value).first()
    if module == None:
        row = D_Modules(title=value)
        db.session.add(row)
        db.session.commit()

        return row.id
    return module.id

    