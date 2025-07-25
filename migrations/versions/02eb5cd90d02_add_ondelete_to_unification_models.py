"""add ondelete to unification models

Revision ID: 02eb5cd90d02
Revises: dd5751bdeae8
Create Date: 2024-05-08 01:14:18.566074

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '02eb5cd90d02'
down_revision = 'dd5751bdeae8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('aup_data', schema=None) as batch_op:
        batch_op.drop_constraint('aup_data_ibfk_16', type_='foreignkey')
        batch_op.create_foreign_key(None, 'groups', ['id_group'], ['id_group'], ondelete='SET DEFAULT')

    with op.batch_alter_table('discipline_period_assoc', schema=None) as batch_op:
        batch_op.drop_constraint('discipline_period_assoc_ibfk_2', type_='foreignkey')
        batch_op.drop_constraint('discipline_period_assoc_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'unification_discipline', ['unification_discipline_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'd_period', ['period_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('faculty_discipline_period', schema=None) as batch_op:
        batch_op.drop_constraint('faculty_discipline_period_ibfk_2', type_='foreignkey')
        batch_op.drop_constraint('faculty_discipline_period_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'discipline_period_assoc', ['discipline_period_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'spr_faculty', ['faculty_id'], ['id_faculty'], ondelete='CASCADE')

    with op.batch_alter_table('unification_discipline', schema=None) as batch_op:
        batch_op.drop_constraint('unification_discipline_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'd_ed_izmereniya', ['measure_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('unification_load', schema=None) as batch_op:
        batch_op.drop_constraint('unification_load_ibfk_2', type_='foreignkey')
        batch_op.drop_constraint('unification_load_ibfk_3', type_='foreignkey')
        batch_op.create_foreign_key(None, 'discipline_period_assoc', ['discipline_period_assoc_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'spr_form_education', ['education_form_id'], ['id_form'], ondelete='CASCADE')

    with op.batch_alter_table('unification_okso_assoc', schema=None) as batch_op:
        batch_op.drop_constraint('unification_okso_assoc_ibfk_2', type_='foreignkey')
        batch_op.drop_constraint('unification_okso_assoc_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'unification_discipline', ['unification_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'spr_okco', ['okso_id'], ['program_code'], ondelete='CASCADE')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('unification_okso_assoc', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('unification_okso_assoc_ibfk_1', 'spr_okco', ['okso_id'], ['program_code'])
        batch_op.create_foreign_key('unification_okso_assoc_ibfk_2', 'unification_discipline', ['unification_id'], ['id'])

    with op.batch_alter_table('unification_load', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('unification_load_ibfk_3', 'discipline_period_assoc', ['discipline_period_assoc_id'], ['id'])
        batch_op.create_foreign_key('unification_load_ibfk_2', 'spr_form_education', ['education_form_id'], ['id_form'])

    with op.batch_alter_table('unification_discipline', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('unification_discipline_ibfk_1', 'd_ed_izmereniya', ['measure_id'], ['id'])

    with op.batch_alter_table('faculty_discipline_period', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('faculty_discipline_period_ibfk_1', 'discipline_period_assoc', ['discipline_period_id'], ['id'])
        batch_op.create_foreign_key('faculty_discipline_period_ibfk_2', 'spr_faculty', ['faculty_id'], ['id_faculty'])

    with op.batch_alter_table('discipline_period_assoc', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('discipline_period_assoc_ibfk_1', 'd_period', ['period_id'], ['id'])
        batch_op.create_foreign_key('discipline_period_assoc_ibfk_2', 'unification_discipline', ['unification_discipline_id'], ['id'])

    with op.batch_alter_table('aup_data', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('aup_data_ibfk_16', 'groups', ['id_group'], ['id_group'])

    # ### end Alembic commands ###
