"""migration title

Revision ID: 4329a7c4808f
Revises: ecb163a808a2
Create Date: 2025-03-17 00:42:53.467622

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "4329a7c4808f"
down_revision = "d79338864d79"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("tbl_aup", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_delete", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("date_delete", sa.DateTime(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("tbl_aup", schema=None) as batch_op:
        batch_op.drop_column("date_delete")
        batch_op.drop_column("is_delete")

    # ### end Alembic commands ###
