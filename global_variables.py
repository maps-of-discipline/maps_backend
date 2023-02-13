from models import D_Blocks, D_Chast, D_ControlType, D_EdIzmereniya, D_Period, D_TypeRecord, D_Modules

def setGlobalVariables(app, blocks, blocks_r, period, period_r, control_type, control_type_r, ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r):
    with app.app_context():

        blocks_q = D_Blocks.query.all()
        for row in blocks_q:
            blocks[row.title] = row.id
            blocks_r[row.id] = row.title
            

        chast_q = D_Chast.query.all()
        for row in chast_q:
            chast[row.title] = row.id
            chast_r[row.id] = row.title

        period_q = D_Period.query.all()
        for row in period_q:
            period[row.title] = row.id
            period_r[row.id] = row.title

        control_type_q = D_ControlType.query.all()
        for row in control_type_q:
            control_type[row.title] = row.id
            control_type_r[row.id] = row.title
        
        ed_izmereniya_q = D_EdIzmereniya.query.all()
        for row in ed_izmereniya_q:
            ed_izmereniya[row.title] = row.id
            ed_izmereniya_r[row.id] = row.title

        type_record_q = D_TypeRecord.query.all()
        for row in type_record_q:
            type_record[row.title] = row.id
            type_record_r[row.id] = row.title


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
