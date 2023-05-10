from tools import check_skiplist
from models import AupData, AupInfo, Groups
blocks = {}
blocks_r = {}
period = {}
period_r = {}
control_type = {}
control_type_r = {}
ed_izmereniya = {}
ed_izmereniya_r = {}
chast = {}
chast_r = {}
type_record = {}
type_record_r = {}

def getType(id):
    l = [1, 5, 9]
    if id in l:
        return "control"
    return "load"

def create_json(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(AupData.shifr).all()

    json = dict()
    json['header'] = [aupInfo.name_op.okco.program_code + '.' + aupInfo.name_op.num_profile,
                      aupInfo.name_op.okco.name_okco, aupInfo.name_op.name_spec, aupInfo.faculty.name_faculty]
    json['year'] = aupInfo.year_beg
    json['data'] = list()
    flag = ""
    session = list()
    value = list()

    for i, item in enumerate(aupData):
        if item.id == 42969:
            print(123)
        if 'Выполнение и защита выпускной квалификационной работы' in item.discipline:
            print()
        # if i+1==len(aupData):
        #     d['type']['session'] = session
        #     d['type']['value'] = value
        #     json['data'].append(d)
        if check_skiplist(item.zet, item.discipline, item.type_record.title, item.block.title) == False:
            continue
        if flag != item.discipline + str(item.id_period):
            if i != 0 and 'd' in locals():
                # print('!DEBUG!', i)
                # if 'd' not in locals(): d = dict()
                d['type']['session'] = session
                d['type']['value'] = value
                session = list()
                value = list()
                json['data'].append(d)
            flag = item.discipline + str(item.id_period)
            d = dict()
            d["discipline"] = item.discipline
            d["id_group"] = item.id_group
            d["id_block"] = item.id_block
            d["shifr"] = item.shifr
            d["id_part"] = item.id_part
            d["id_module"] = item.id_module
            d["num_col"] = item.id_period - 1 
            d["num_row"] = item.num_row
            d["type"] = dict()
            d["id"] = str(item.id)
            zet = dict()
            zet["amount"] = item.amount / 100
            zet["id_edizm"] = item.ed_izmereniya.id
            zet["id"] = item.id
            zet["control_type_id"] = item.id_type_control
            zet["type"] = getType(item.id_type_control)
            if item.id_type_control == control_type['Экзамен'] or item.id_type_control == control_type['Зачет'] or item.id_type_control == control_type['Дифференцированный зачет']:
                session.append(zet)
            else:
                value.append(zet)
            if i+1==len(aupData):
                d['type']['session'] = session
                d['type']['value'] = value
                json['data'].append(d)
        else:
            d["id"] += str(item.id)
            zet = dict()
            zet["amount"] = item.amount / 100
            zet["id_edizm"] = item.ed_izmereniya.id
            zet["id"] = item.id
            zet["control_type_id"] = item.id_type_control
            zet["type"] = getType(item.id_type_control)
            if item.id_type_control == control_type['Экзамен'] or item.id_type_control == control_type['Зачет'] or item.id_type_control == control_type['Дифференцированный зачет']:
                session.append(zet)
            else:
                value.append(zet)            
            if i+1==len(aupData):
                json['data'].append(d)

    return json


def create_json_test(aupInfo, aupData, max_column, max_row):
    json = dict()
    json['header'] = [aupInfo.name_op.okco.program_code + '.' + aupInfo.name_op.num_profile,
                      aupInfo.name_op.okco.name_okco, aupInfo.name_op.name_spec, aupInfo.faculty.name_faculty]
    json['year'] = aupInfo.year_beg
    json['data'] = list()
    for i in range(1, max_column + 1):
        for j in range(max_row + 1):
            print(i, j)
            disc = aupData.filter_by(num_row=j, id_period=i).all()
            if disc == []: continue
            if check_skiplist(disc[0].zet, disc[0].discipline, disc[0].type_record.title, disc[0].block.title) == False:
                continue
            d = dict()
            d["discipline"] = disc[0].discipline
            d["id_group"] = disc[0].id_group
            d["num_col"] = disc[0].id_period
            d["num_row"] = disc[0].num_row
            d["type"] = list()
            d["id"] = ""
            for item in disc:
                zet = dict()
                zet["control"] = control_type_r[item.id_type_control]
                zet["zet"] = item.zet / 100
                zet["id"] = item.id
                d["type"].append(zet)
                d["id"] += str(item.id)
            json['data'].append(d)
    return json

def create_json_print(aupData):
    json = dict()
    json['data'] = list()
    flag = ""
    for i, item in enumerate(aupData):
        if check_skiplist(item.zet, item.discipline, item.type_record.title, item.block.title) == False:
            continue
        if flag != item.discipline + str(item.id_period):
            if i != 0:
                json['data'].append(d)
            flag = item.discipline + str(item.id_period)
            d = dict()
            d["discipline"] = item.discipline
            group = Groups.query.filter(Groups.id_group == item.id_group).first()
            d["color"] = group.color
            d["id_group"] = group.id_group
            d["num_col"] = item.id_period
            d["num_row"] = item.num_row
            d["zet"] = item.zet / 100
            if i+1==len(aupData):
                json['data'].append(d)
        else:
            d["zet"] += item.zet / 100
            if i+1==len(aupData):
                json['data'].append(d)
    return json