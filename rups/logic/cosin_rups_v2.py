import dataclasses
from sqlalchemy import select, func, case
from dataclasses import dataclass, asdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re
from maps.models import AupData, AupInfo, SprDiscipline, D_EdIzmereniya, D_ControlType
from maps.models import db


@dataclass
class Discipline:
    title: str
    period: int
    zet: float
    control: str
    coursework: bool
    amount: float
    elective_group: int | None = None

    @staticmethod
    def _amount_to_zet(amount: float, measure: str) -> float:
        return round(amount / (36 if measure == "Часы" else 54), 2)

    @classmethod
    def from_sqla_row(cls, row):
        return cls(
            title=row["title"],
            period=row["period"],
            zet=cls._amount_to_zet(row["amount"], row["measure"]),
            amount=round(row["amount"], 1),
            control=row["control_type"],
            coursework=row["coursework"],
        )

    def __hash__(self):
        return hash((self.title, self.zet, self.control))

    def __eq__(self, value):
        return (
            self.title == value.title
            and self.control == value.control
            and self.zet == value.zet
        )


def parse_electives(discipline: Discipline, group: int) -> dict[str, Discipline]:
    titles = discipline.title.split(" / ")

    res = {}
    for title in titles:
        discipline_copy = dataclasses.replace(discipline)
        discipline_copy.title = title
        discipline_copy.elective_group = group
        res.update({title: discipline_copy})

        if discipline_copy.coursework:
            title += " (КР)"
            cw_discipline = dataclasses.replace(discipline)
            cw_discipline.title = title
            cw_discipline.elective_group = group
            res.update({title: discipline_copy})
    return res


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
            func.max(
                case(
                    (D_ControlType.title == "Курсовой проект", True),
                    (D_ControlType.title == "Курсовая работа", True),
                    else_=False,
                )
            ).label("coursework"),
        )
        .join(AupInfo)
        .join(SprDiscipline)
        .join(D_EdIzmereniya)
        .join(D_ControlType, AupData.id_type_control == D_ControlType.id)
        .where(AupInfo.num_aup == aup)
        .group_by(
            SprDiscipline.title,
            AupData.id_period,
            AupData.id_edizm,
        )
        .order_by(AupData.id_period)
    )

    res = {}
    elective_groups = {}
    for el in db.session.execute(query).mappings().all():
        discipline = Discipline.from_sqla_row(el)
        if "/" in discipline.title:
            if discipline.title not in elective_groups:
                elective_groups.update({discipline.title: len(elective_groups) + 1})

            disciplines = parse_electives(discipline, elective_groups[discipline.title])
            res.update(disciplines)
            continue

        title = discipline.title
        cw_title = discipline.title + " (КП)"

        if discipline.period > sem_num:
            if title in res:
                res.pop(title)
            if cw_title in res:
                res.pop(cw_title)
            continue

        if discipline.title not in res:
            res.update({discipline.title: discipline})

        if discipline.coursework and cw_title not in res:
            cw_discipline = dataclasses.replace(discipline)
            cw_discipline.title = cw_title
            cw_discipline.amount = 0
            cw_discipline.control = "Курсовая работа"
            res.update({cw_title: cw_discipline})

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
        "Курсовая работа": ["Курсовая работа", "Курсовой проект"],
        "Курсовой проект": ["Курсовая работа", "Курсовой проект"],
    }

    return (
        variant.control in mapper
        and variant.control in mapper[target.control]
        and target.zet <= variant.zet
    )


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


def compare_two_aups(aup1: list[dict] | dict, aup2: dict) -> dict:
    plan1 = aup1
    if isinstance(aup1, dict):
        plan1 = get_aup(aup1["num"], sem_num=aup1["sem"])

    plan2 = get_aup(aup2["num"], sem_num=aup2["sem"])

    diff1, diff2, same = remove_same(plan1, plan2)

    similar = calculate_similar_disciplines(diff1, diff2, top_n=30, threshold=0.001)
    return {
        "source": diff1,
        "target": diff2,
        "same": same,
        "similar": similar,
        "best_match": get_best_match(similar),
    }
