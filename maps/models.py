from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_serializer import SerializerMixin

db = SQLAlchemy()


class SprBranch(db.Model, SerializerMixin):
    __tablename__ = 'spr_branch'

    id_branch = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<Branch %r>' % self.location


class SprDegreeEducation(db.Model, SerializerMixin):
    __tablename__ = 'spr_degree_education'

    id_degree = db.Column(db.Integer, primary_key=True)
    name_deg = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<DegreeEducation %r>' % self.name_deg


class SprFaculty(db.Model, SerializerMixin):
    __tablename__ = 'spr_faculty'

    id_faculty = db.Column(db.Integer, primary_key=True)
    name_faculty = db.Column(db.String(255), nullable=False)
    id_branch = db.Column(db.Integer, db.ForeignKey(
        'spr_branch.id_branch'), nullable=False)
    dean = db.Column(db.String(255), nullable=True)
    admin_only = db.Column(db.Boolean, default=0)
    branch = db.relationship('SprBranch')

    departments = db.relationship("Department", back_populates='faculty', lazy='joined')

    def __repr__(self):
        return '<Faculty %r>' % self.name_faculty


class Department(db.Model, SerializerMixin):
    __tablename__ = 'tbl_department'

    serialize_rules = ("-faculty.departments",)

    id_department = db.Column(db.Integer, primary_key=True)
    name_department = db.Column(db.String(255), nullable=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey('spr_faculty.id_faculty'))

    faculty = db.relationship("SprFaculty", back_populates='departments')
    tbl_aups = db.relationship('AupInfo', back_populates='department', lazy='joined')

    def __repr__(self):
        return '<Department %r>' % self.name_department


class SprFormEducation(db.Model, SerializerMixin):
    __tablename__ = 'spr_form_education'

    id_form = db.Column(db.Integer, primary_key=True)
    form = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return '<FormEducation %r>' % self.form


class SprOKCO(db.Model, SerializerMixin):
    __tablename__ = 'spr_okco'

    program_code = db.Column(db.String(255), primary_key=True)
    name_okco = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return "<OKCO %r>" % self.name_okco


class SprRop(db.Model, SerializerMixin):
    __tablename__ = 'spr_rop'

    id_rop = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(255), nullable=False)
    middle_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    telephone = db.Column(db.String(255), nullable=False)

    @property
    def full_name(self):
        return " ".join([self.last_name, self.first_name, self.middle_name or ""])

    def __repr__(self):
        return "<Rop %r>" % self.full_name


class AupInfo(db.Model, SerializerMixin):
    __tablename__ = 'tbl_aup'
    serialize_rules = ('-department.tbl_aups', '-aup_data.aup')

    id_aup = db.Column(db.Integer, primary_key=True)
    file = db.Column(db.String(255), nullable=False)
    num_aup = db.Column(db.String(255), nullable=False)
    base = db.Column(db.String(255), nullable=False)
    id_faculty = db.Column(
        db.Integer,
        db.ForeignKey("spr_faculty.id_faculty", ondelete="CASCADE"),
        nullable=False,
    )
    id_rop = db.Column(db.Integer, db.ForeignKey("spr_rop.id_rop"), nullable=False)
    type_educ = db.Column(db.String(255), nullable=False)
    qualification = db.Column(db.String(255), nullable=False)
    type_standard = db.Column(db.String(255), nullable=False)
    id_department = db.Column(
        db.Integer,
        db.ForeignKey("tbl_department.id_department", ondelete="SET NULL"),
    )
    period_educ = db.Column(db.String(255), nullable=False)
    id_degree = db.Column(
        db.Integer,
        db.ForeignKey("spr_degree_education.id_degree", ondelete="CASCADE"),
        nullable=False,
    )
    id_form = db.Column(
        db.Integer,
        db.ForeignKey("spr_form_education.id_form", ondelete="CASCADE"),
        nullable=False,
    )
    years = db.Column(db.Integer, nullable=False)
    months = db.Column(db.Integer, nullable=True)
    id_spec = db.Column(
        db.Integer,
        db.ForeignKey("spr_name_op.id_spec", ondelete="SET NULL"),
    )
    year_beg = db.Column(db.Integer, nullable=False)
    year_end = db.Column(db.Integer, nullable=False)
    is_actual = db.Column(db.Boolean, nullable=False)

    degree = db.relationship("SprDegreeEducation")
    form = db.relationship("SprFormEducation")
    name_op = db.relationship("NameOP")
    faculty = db.relationship("SprFaculty")
    rop = db.relationship("SprRop")
    department = db.relationship("Department")
    aup_data = db.relationship("AupData", back_populates="aup")

    def __repr__(self):
        return "<№ AUP %r>" % self.num_aup

    def copy(self, num, file=None):
        new_aup: AupInfo = AupInfo(
            file=file if file else "",
            num_aup=num,
            base=self.base,
            id_faculty=self.id_faculty,
            id_rop=self.id_rop,
            type_educ=self.type_educ,
            qualification=self.qualification,
            type_standard=self.type_standard,
            id_department=self.id_department,
            period_educ=self.period_educ,
            id_degree=self.id_degree,
            id_form=self.id_form,
            years=self.years,
            months=self.months,
            id_spec=self.id_spec,
            year_beg=self.year_beg,
            year_end=self.year_end,
            is_actual=False,
        )
        print(new_aup, "\n")

        db.session.add(new_aup)

        aup_data_queryset = AupData.query.filter_by(id_aup=self.id_aup).all()
        db.session.add_all([el.copy(new_aup) for el in aup_data_queryset])

        db.session.commit()


class NameOP(db.Model, SerializerMixin):
    __tablename__ = "spr_name_op"

    id_spec = db.Column(db.Integer, primary_key=True)
    program_code = db.Column(
        db.String(255),
        db.ForeignKey("spr_okco.program_code", ondelete="CASCADE"),
        nullable=False,
    )
    num_profile = db.Column(db.String(255), nullable=False)
    name_spec = db.Column(db.String(255), nullable=False)

    okco = db.relationship("SprOKCO")

    def __repr__(self):
        return "<NameOP %r>" % self.id_spec


class SprVolumeDegreeZET(db.Model):
    __tablename__ = "spr_volume_degree_zet"

    id_volume_deg = db.Column(db.Integer, primary_key=True)
    program_code = db.Column(
        db.String(255),
        db.ForeignKey("spr_okco.program_code", ondelete="CASCADE"),
        nullable=False,
    )
    id_standard = db.Column(db.Integer, nullable=False)
    zet = db.Column(db.Integer, nullable=False)
    effective_date = db.Column(db.Date, nullable=True)

    progr_code = db.relationship("SprOKCO")

    @property
    def volume_degree_zet(self):
        return f"id: {self.id_volume_deg}, program_code: {self.program_code}, \
        type_standard: {self.id_standard}, ZET: {self.zet}, effective date: \
        {self.effective_date}"

    def __repr__(self):
        return "<SprVolumeDegreeZET %r>" % self.volume_degree_zet


class SprStandard(db.Model, SerializerMixin):
    __tablename__ = 'spr_standard_zet'

    id_standard = db.Column(db.Integer, primary_key=True)
    type_standard = db.Column(db.String(255), nullable=False)

    @property
    def standard_date(self):
        return "id: {}, type_standard: {}".format(self.id_standard, self.type_standard)

    def __repr__(self):
        return "<SprStandardZET %r>" % self.standard_date


class D_Blocks(db.Model, SerializerMixin):
    __tablename__ = 'd_blocks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return "<D_Blocks %r>" % self.title


class D_Period(db.Model, SerializerMixin):
    __tablename__ = 'd_period'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return "<D_Period %r>" % self.title


class D_ControlType(db.Model, SerializerMixin):
    __tablename__ = 'd_control_type'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    shortname = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return "<D_ControlType %r>" % self.title


class D_EdIzmereniya(db.Model, SerializerMixin):
    __tablename__ = 'd_ed_izmereniya'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return "<D_EdIzmereniya %r>" % self.title


class D_Part(db.Model, SerializerMixin):
    __tablename__ = 'd_part'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return "<D_Part %r>" % self.title


class D_TypeRecord(db.Model, SerializerMixin):
    __tablename__ = 'd_type_record'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return "<D_TypeRecord %r>" % self.title


class D_Modules(db.Model, SerializerMixin):
    __tablename__ = 'd_modules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    color = db.Column(db.String(8), nullable=False, default="#5f60ec")

    def __repr__(self):
        return "<D_Modules %r>" % self.title


class Groups(db.Model, SerializerMixin):
    __tablename__ = 'groups'
    id_group = db.Column(db.Integer, primary_key=True)
    name_group = db.Column(db.String(255), nullable=False)
    color = db.Column(db.String(8), nullable=False)
    weight = db.Column(db.Integer, nullable=False, default=5)

    def __repr__(self):
        return '<Groups %r>' % self.name_group


class AupData(db.Model, SerializerMixin):
    __tablename__ = 'aup_data'
    serialize_rules = ("-aup",)

    id = db.Column(db.Integer, primary_key=True)
    id_aup = db.Column(
        db.Integer, db.ForeignKey("tbl_aup.id_aup", ondelete="CASCADE"), nullable=False
    )

    id_block = db.Column(
        db.Integer, db.ForeignKey("d_blocks.id", ondelete="SET NULL")
    )

    shifr = db.Column(db.String(30), nullable=False)

    id_part = db.Column(db.Integer, db.ForeignKey("d_part.id", ondelete="SET NULL"))

    id_module = db.Column(db.Integer, db.ForeignKey("d_modules.id", ondelete="SET DEFAULT"), default=1)

    id_group = db.Column(db.Integer, db.ForeignKey("groups.id_group", ondelete='SET DEFAULT'), default=1)

    id_type_record = db.Column(
        db.Integer,
        db.ForeignKey("d_type_record.id"),
        nullable=False,
    )

    id_discipline = db.Column(
        db.Integer,
        db.ForeignKey("spr_discipline.id", ondelete="SET NULL"),
        nullable=True,
    )

    _discipline = db.Column("discipline", db.String(350), nullable=False)
    id_period = db.Column(
        db.Integer, db.ForeignKey("d_period.id"), nullable=False
    )
    num_row = db.Column(db.Integer, nullable=False)
    id_type_control = db.Column(
        db.Integer, db.ForeignKey("d_control_type.id"), nullable=False
    )
    amount = db.Column(db.Integer, nullable=False)
    id_edizm = db.Column(
        db.Integer, db.ForeignKey("d_ed_izmereniya.id"), nullable=False
    )
    zet = db.Column(db.Integer, nullable=False)

    block = db.relationship("D_Blocks", lazy="joined")
    part = db.relationship("D_Part")
    module = db.relationship("D_Modules", lazy="joined")
    type_record = db.relationship("D_TypeRecord", lazy="joined")
    type_control = db.relationship("D_ControlType", lazy="joined")
    aup = db.relationship("AupInfo", back_populates="aup_data")
    ed_izmereniya = db.relationship("D_EdIzmereniya", lazy="joined")
    group = db.relationship("Groups", lazy="joined")
    unique_discipline = db.relationship("SprDiscipline")

    @property
    def discipline(self) -> str:
        return self._discipline

    @discipline.setter
    def discipline(self, value: str):
        discipline = SprDiscipline.query.filter_by(title=value).first()

        if not discipline:
            discipline = SprDiscipline(title=value)
            db.session.add(discipline)
            db.session.commit()

        self.id_discipline = discipline.id
        self._discipline = value

    def __repr__(self):
        return "<AupData %r>" % self.aup.num_aup

    def copy(self, parent: AupInfo):
        return AupData(
            id_aup=parent.id_aup,
            id_block=self.id_block,
            shifr=self.shifr,
            id_part=self.id_part,
            id_module=self.id_module,
            id_group=self.id_group,
            id_type_record=self.id_type_record,
            discipline=self.discipline,
            id_period=self.id_period,
            num_row=self.num_row,
            id_type_control=self.id_type_control,
            amount=self.amount,
            id_edizm=self.id_edizm,
            zet=self.zet,
        )


class SprDiscipline(db.Model, SerializerMixin):
    __tablename__ = "spr_discipline"

    serialize_only = ('id', 'title')

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))


class Revision(db.Model):
    __tablename__ = "Revision"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    date = db.Column(db.DateTime)
    isActual = db.Column(db.Boolean)
    user_id = db.Column(db.Integer, db.ForeignKey("tbl_users.id_user"), nullable=False)
    aup_id = db.Column(db.Integer, db.ForeignKey("tbl_aup.id_aup"), nullable=False)


    logs = db.relationship("ChangeLog", lazy="joined")


class ChangeLog(db.Model):
    __tablename__ = "ChangeLog"
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(45))
    row_id = db.Column(db.Integer)
    field = db.Column(db.String(45))
    old = db.Column(db.String(500))
    new = db.Column(db.String(500))
    revision_id = db.Column(db.Integer, db.ForeignKey("Revision.id", ondelete='CASCADE'), nullable=False)

