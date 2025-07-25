"""alter unification_load table

Revision ID: d49fff2a53c7
Revises: 60304ed0a78b
Create Date: 2024-03-26 02:39:31.636143

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd49fff2a53c7'
down_revision = '60304ed0a78b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('unification_load', schema=None) as batch_op:
        batch_op.add_column(sa.Column('seminars', sa.Float(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('unification_load', schema=None) as batch_op:
        batch_op.drop_column('seminars')

    # ### end Alembic commands ###
