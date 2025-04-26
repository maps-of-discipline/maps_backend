from typing import Any

from sqlalchemy import select, func, case, and_
from dataclasses import dataclass, asdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re
import json

from maps.models import AupData, AupInfo, SprDiscipline, D_EdIzmereniya, D_ControlType
from maps.models import db


@dataclass
class Discipline:
    title: str
    period: int
    zet: float
    control: str

    @staticmethod
    def _amount_to_zet(amount: float, measure: str) -> float:
        return round(amount / (36 if measure == "Часы" else 54), 2)

    @classmethod
    def from_sqla_row(cls, row):
        return cls(
            title=row["title"],
            period=row["period"],
            zet=cls._amount_to_zet(row["amount"], row["measure"]),
            control=row["control_type"],
        )

    def __hash__(self):
        return hash((self.title, self.zet, self.control))

    def __eq__(self, value):
        return (
            self.title == value.title
            and self.control == value.control
            and self.zet == value.zet
        )


def get_aup(aup: str, sem_num: int = 20) -> list[Discipline]:
    query = (
        select(
            SprDiscipline.title.label("title"),
            AupData.id_period.label("period"),
            (func.sum(AupData.amount) / 100).label("amount"),
            D_EdIzmereniya.title.label("measure"),
            func.min(
                case(
                    (D_ControlType.title == "Экзамен", D_ControlType.title),
                    (D_ControlType.title == "Дифференцированный зачет", "Диф. зачет"),
                    (D_ControlType.title == "Зачет", D_ControlType.title),
                    else_=None,
                )
            ).label("control_type"),
        )
        .join(AupInfo)
        .join(SprDiscipline)
        .join(D_EdIzmereniya)
        .join(D_ControlType)
        .where(AupInfo.num_aup == aup)
        .group_by(
            SprDiscipline.title,
            AupData.id_period,
            AupData.id_edizm,
        )
        .order_by(AupData.id_period)
    )
    res = {}
    for el in db.session.execute(query).mappings().all():
        discipline = Discipline.from_sqla_row(el)
        title = discipline.title
        if discipline.period > sem_num:
            if title in res:
                res.pop(title)
            continue

        if discipline.title not in res:
            res.update({discipline.title: discipline})

    return list(res.values())


def remove_same(source, target):
    """Удаление одинаковых дисциплин из двух списков."""
    source_set = set(source)
    target_set = set(target)

    diff1 = list(source_set - target_set)
    diff2 = list(target_set - source_set)
    same = list(source_set.intersection(target_set))

    return diff1, diff2, same


def preprocess_text(text):
    """Preprocess text for better similarity matching"""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def couldBeCredited(target: Discipline, variant: Discipline) -> bool:
    mapper = {
        "Экзамен": ["Экзамен", "Диф. зачет"],
        "Диф. зачет": ["Экзамен", "Диф. зачет"],
        "Зачет": ["Экзамен", "Диф. зачет", "Зачет"],
    }

    return variant.control in mapper[target.control] and target.zet <= variant.zet


def calculate_similar_disciplines(
    source_plan: list[Discipline], target_plan: list[Discipline], top_n=3, threshold=0.3
):
    """
    Find similar disciplines between source and target plans based on title similarity.

    Args:
        source_plan: List of disciplines the student has already passed
        target_plan: List of disciplines in the new program
        top_n: Number of similar disciplines to return for each target
        threshold: Minimum similarity score to consider disciplines as similar
    """
    # Extract and preprocess titles
    source_titles = [preprocess_text(disc.title) for disc in source_plan]
    target_titles = [preprocess_text(disc.title) for disc in target_plan]

    # Create TF-IDF vectors
    vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2))

    # Fit and transform all titles together
    all_titles = source_titles + target_titles
    tfidf_matrix = vectorizer.fit_transform(all_titles)

    # Split the matrix back into source and target vectors
    source_vectors = tfidf_matrix[: len(source_titles)]
    target_vectors = tfidf_matrix[len(source_titles) :]

    # Calculate similarity for each target discipline
    result = []

    for i, target_disc in enumerate(target_plan):
        target_vector = target_vectors[i : i + 1]

        # Calculate similarities with all source disciplines
        similarities = cosine_similarity(target_vector, source_vectors)[0]

        # Create list of (index, similarity score) pairs
        similarity_pairs = [(idx, score) for idx, score in enumerate(similarities)]

        # Sort by similarity in descending order
        similarity_pairs.sort(key=lambda x: x[1], reverse=True)

        # Filter by threshold and take top N
        top_matches = [
            {
                **asdict(source_plan[idx]),
                "similarity": round(float(score), 2),
            }
            for idx, score in similarity_pairs
            if score >= threshold and couldBeCredited(target_plan[i], source_plan[idx])
        ][:top_n]

        result.append({**asdict(target_disc), "variants": top_matches})

    return result


def get_best_match(similar: list[dict]) -> dict:
    best_match = {}
    for target in similar:
        variants = target.get("variants", [])
        for variant in variants:
            if (
                variant["similarity"]
                > best_match.get(variant["title"], {"similarity": 0})["similarity"]
            ):
                best_match.update(
                    {
                        variant["title"]: {
                            "target": target["title"],
                            "similarity": variant["similarity"],
                        }
                    }
                )
    return best_match


def compare_two_aups(aup1: list[dict] | str, aup2: str, sem_num: int | None) -> Any:
    plan1 = aup1
    if isinstance(aup1, str):
        plan1 = get_aup(aup1, sem_num=sem_num)

    plan2 = get_aup(aup2, sem_num=sem_num)
    diff1, diff2, same = remove_same(plan1, plan2)

    similar = calculate_similar_disciplines(diff1, diff2, top_n=30, threshold=0.001)
    return {
        "source": diff1,
        "target": diff2,
        "same": same,
        "similar": similar,
        "best_match": get_best_match(similar),
    }
