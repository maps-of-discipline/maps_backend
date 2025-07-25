"""add aup-data.user-for-report column

Revision ID: ecb163a808a2
Revises: e9995672322c
Create Date: 2024-11-17 15:53:04.982852

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ecb163a808a2'
down_revision = 'e9995672322c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('aup_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('used_for_report', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('aup_data', schema=None) as batch_op:
        batch_op.drop_column('used_for_report')

    # ### end Alembic commands ###
