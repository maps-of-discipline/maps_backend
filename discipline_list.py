from tools import check_skiplist
from models import AupData, AupInfo, Groups
from take_from_bd import (blocks, blocks_r, period, period_r, control_type, control_type_r,
                          ed_izmereniya, ed_izmereniya_r, chast, chast_r, type_record, type_record_r, create_json, create_json_test)
def dis_list(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(AupData.shifr, AupData.discipline, AupData.id_period, AupData.id_type_control).all()
    discipline = {}
    for i, item in enumerate(aupData):
        try:
            if not(item.discipline in  discipline[item.faculty.faculty]):
                discipline[item.faculty.faculty].append(item.discipline)
        except:
            # discipline[item.faculty.faculty] = [item.discipline]
            # последующие строчки удалить, это просто заглушка, пока нет нужных столбцов в БД.
            try:
                discipline[item.faculty.faculty] = [item.discipline]
            except:
                try:
                    if not(item.discipline in  discipline["unknown_faculty"]):
                        discipline["unknown_faculty"].append(item.discipline)
                except:
                    discipline["unknown_faculty"] = [item.discipline]
    return discipline

def faculty_dis(aup):
    aupInfo = AupInfo.query.filter_by(num_aup=aup).first()
    aupData = AupData.query.filter_by(id_aup=aupInfo.id_aup).order_by(AupData.shifr, AupData.discipline, AupData.id_period, AupData.id_type_control).all()
    dis = {}
    for i,item in enumerate(aupData):
        if (item.id_type_record==13 or item.id_type_record==15 or item.id_type_record==16):
            try:
                dis[item.discipline] += item.amount//100
            except:
                dis[item.discipline] = item.amount//100
    return dis
            