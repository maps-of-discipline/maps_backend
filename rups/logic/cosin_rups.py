import json
from pprint import pprint
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict
import pandas as pd
import random

pd.set_option("display.max_colwidth", None)

# Данные для учебных планов


def get_same(aup1, aup2) -> list:
    aup1 = set(aup1)
    aup2 = set(aup2)
    return list(aup1.intersection(aup2))


def remove_same(aup1, aup2):
    same = get_same(aup1, aup2)
    aup1 = list(set(aup1).difference(same))
    aup2 = list(set(aup2).difference(same))
    return aup1, aup2


def compare_disciplines(
    plan1: List[str],
    plan2: List[str],
    credits1: Dict[str, float],
    credits2: Dict[str, float],
) -> pd.DataFrame:
    """Сопоставление дисциплин между двумя учебными планами с использованием косинусного сходства и зачетных единиц."""
    if not plan1 or not plan2:
        return pd.DataFrame(columns=["aup1", "aup2", "similarity", "zet1", "zet2"])
    vectorizer = TfidfVectorizer().fit(plan1 + plan2)
    tfidf_plan1 = vectorizer.transform(plan1)
    tfidf_plan2 = vectorizer.transform(plan2)
    similarities = cosine_similarity(tfidf_plan1, tfidf_plan2)

    results = []
    for i, discip1 in enumerate(plan1):
        max_similarity_index = similarities[i].argmax()
        max_similarity_value = similarities[i][max_similarity_index]

        # Учитываем зачетные единицы в расчете
        credit_similarity = (
            credits1[discip1] + credits2[plan2[max_similarity_index]]
        ) / 2
        combined_similarity = (
            max_similarity_value + (credit_similarity / 500)
        ) / 2  # Нормируем зачетные единицы

        results.append(
            {
                "aup1": discip1,
                "aup2": plan2[max_similarity_index],
                "similarity": combined_similarity,
                "zet1": credits1[discip1],
                "zet2": credits2[plan2[max_similarity_index]],
            }
        )

    df = pd.DataFrame(results)

    if len(plan2) > len(plan1):
        additional_rows = [
            {
                "aup1": "",
                "aup2": plan2[i],
                "similarity": 0.0,
                "zet1": 0,
                "zet2": credits2[plan2[i]],
            }
            for i in range(len(plan1), len(plan2))
        ]
        df = pd.concat([df, pd.DataFrame(additional_rows)], ignore_index=True)

    if len(plan1) > len(plan2):
        additional_rows = [
            {
                "aup1": plan1[i],
                "aup2": "",
                "similarity": 0.0,
                "zet1": credits1[plan1[i]],
                "zet2": 0,
            }
            for i in range(len(plan2), len(plan1))
        ]
        df = pd.concat([df, pd.DataFrame(additional_rows)], ignore_index=True)
    df = df.sort_values(by="similarity", ascending=False)
    df = df.round(
        {
            "similarity": 3,
            "zet1": 1,
            "zet2": 1,
        }
    )
    return df


def compare_disciplines_2(plan_1, plan_2, credits_1, credits_2):
    """Сравнение дисциплин между двумя учебными планами с использованием косинусного сходства и зачетных единиц."""
    vectorizer = TfidfVectorizer()
    all_disciplines = plan_1 + plan_2
    tfidf_matrix = vectorizer.fit_transform(all_disciplines)
    cosine_sim = cosine_similarity(tfidf_matrix)

    results = []
    used_from_plan_1 = set()
    used_from_plan_2 = set()

    for i in range(len(plan_1)):
        max_similarity = -1
        max_index = -1
        for j in range(len(plan_2)):
            if plan_2[j] not in used_from_plan_2:
                similarity = cosine_sim[i, len(plan_1) + j]
                if similarity > max_similarity:
                    max_similarity = similarity
                    max_index = j
        if max_index != -1:
            # Учитываем зачетные единицы в расчете
            credit_similarity = (
                credits_1[plan_1[i]] + credits_2[plan_2[max_index]]
            ) / 2
            combined_similarity = (
                max_similarity + (credit_similarity / 500)
            ) / 2  # Нормируем зачетные единицы

            results.append(
                [
                    plan_1[i],
                    plan_2[max_index],
                    combined_similarity,
                    credits_1[plan_1[i]],
                    credits_2[plan_2[max_index]],
                ]
            )
            used_from_plan_1.add(plan_1[i])
            used_from_plan_2.add(plan_2[max_index])

    for j in range(len(plan_2)):
        if plan_2[j] not in used_from_plan_2:
            max_similarity = -1
            max_index = -1
            for i in range(len(plan_1)):
                if plan_1[i] not in used_from_plan_1:
                    similarity = cosine_sim[i, len(plan_1) + j]
                    if similarity > max_similarity:
                        max_similarity = similarity
                        max_index = i
            if max_index != -1:
                # Учитываем зачетные единицы в расчете
                credit_similarity = (
                    credits_1[plan_1[max_index]] + credits_2[plan_2[j]]
                ) / 2
                combined_similarity = (
                    max_similarity + (credit_similarity / 500)
                ) / 2  # Нормируем зачетные единицы

                results.append(
                    [
                        plan_1[max_index],
                        plan_2[j],
                        combined_similarity,
                        credits_1[plan_1[max_index]],
                        credits_2[plan_2[j]],
                    ]
                )
                used_from_plan_1.add(plan_1[max_index])
                used_from_plan_2.add(plan_2[j])

    df = pd.DataFrame(
        results,
        columns=[
            "aup1",
            "aup2",
            "similarity",
            "zet1",
            "zet2",
        ],
    )
    df = df.sort_values(by="similarity", ascending=False)
    df = df.round(
        {
            "similarity": 3,
            "zet1": 1,
            "zet2": 1,
        }
    )

    max_len = max(len(plan_1), len(plan_2))
    df = df.head(max_len)

    return df


def get_rups(aup_data1: list, aup_data2: list) -> dict:
    aup1 = [item["title"] for item in aup_data1]
    aup2 = [item["title"] for item in aup_data2]

    credits_aup1 = {item["title"]: item["zet"] for item in aup_data1}
    credits_aup2 = {item["title"]: item["zet"] for item in aup_data2}

    diff1, diff2 = remove_same(aup1, aup2)
    
    result = compare_disciplines_extended(diff1, diff2, credits_aup1, credits_aup2)
    return {"academic_difference": result}


def compare_disciplines_extended(
    plan1: List[str],
    plan2: List[str],
    credits1: Dict[str, float],
    credits2: Dict[str, float],
    threshold: float = 0.2
) -> List[Dict]:
    """Сопоставление дисциплин с возвратом всех вариантов выше порога схожести."""
    if not plan1 or not plan2:
        return []
    
    vectorizer = TfidfVectorizer().fit(plan1 + plan2)
    tfidf_plan1 = vectorizer.transform(plan1)
    tfidf_plan2 = vectorizer.transform(plan2)
    similarities = cosine_similarity(tfidf_plan1, tfidf_plan2)

    results = []
    for i, discip1 in enumerate(plan1):
        options = []
        for j, discip2 in enumerate(plan2):
            similarity = similarities[i][j]
            
            credit_similarity = (credits1[discip1] + credits2[discip2]) / 2
            combined_similarity = (similarity + (credit_similarity / 500)) / 2
            
            if combined_similarity > threshold:
                options.append({
                    "disc_title": discip2,
                    "disc_id": j + 1,
                    "sim": round(combined_similarity, 3),
                    "zet": credits2[discip2]
                })
        
        options.sort(key=lambda x: x["sim"], reverse=True)
        
        results.append({
            "disc_id": i + 1,
            "disc_title": discip1,
            "options": options,
            "zet": credits1[discip1]
        })

    return results
