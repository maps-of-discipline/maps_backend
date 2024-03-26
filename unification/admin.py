from flask_admin.contrib.sqla import ModelView
from maps.models import db
from unification.models import UnificationDiscipline, UnificationLoad, DisciplinePeriodAssoc

category = __package__.capitalize()


class UnificationDisciplineAdminView(ModelView):
    ...


class UnificationLoadAdminView(ModelView):
    ...


class DisciplinePeriodAssociationAdminView(ModelView):
    ...


unification_admin_views = [
    UnificationDisciplineAdminView(UnificationDiscipline, db.session, category=category),
    UnificationLoadAdminView(UnificationLoad, db.session, category=category),
    DisciplinePeriodAssociationAdminView(DisciplinePeriodAssoc, db.session, category=category),

]
