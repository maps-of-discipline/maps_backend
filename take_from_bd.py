from tools import check_skiplist

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

def create_json(aupInfo, aupData):
    json = dict()
    json['header'] = [aupInfo.name_op.okco.program_code + '.' + aupInfo.name_op.num_profile,
                      aupInfo.name_op.okco.name_okco, aupInfo.name_op.name_spec, aupInfo.faculty.name_faculty]
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
            d["id_group"] = item.id_group
            d["num_col"] = item.id_period
            d["num_row"] = item.num_row
            d["type"] = list()
            d["id"] = str(item.id)
            zet = dict()
            zet["control"] = control_type_r[item.id_type_control]
            zet["zet"] = item.zet / 100
            zet["id"] = item.id
            d["type"].append(zet)
        else:
            d["id"] += str(item.id)
            zet = dict()
            zet["control"] = control_type_r[item.id_type_control]
            zet["zet"] = item.zet / 100
            zet["id"] = item.id
            d["type"].append(zet)

    return json


def create_json_test(aupInfo, aupData, max_column, max_row):
    json = dict()
    json['header'] = [aupInfo.name_op.okco.program_code + '.' + aupInfo.name_op.num_profile,
                      aupInfo.name_op.okco.name_okco, aupInfo.name_op.name_spec, aupInfo.faculty.name_faculty]
    json['data'] = list()
    for i in range(1, max_column + 1):
        for j in range(max_row + 1):
            print(i, j)
            disc = aupData.filter_by(num_row=j, id_period=i).all()
            if disc == []: continue
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
            d["color"] = item.group.color
            d["num_col"] = item.id_period
            d["num_row"] = item.num_row
            d["zet"] = item.zet / 100
        else:
            d["zet"] += item.zet / 100

    return json