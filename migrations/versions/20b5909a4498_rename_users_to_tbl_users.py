"""rename users to tbl_users 

Revision ID: 20b5909a4498
Revises: 9a5ae7c9b890
Create Date: 2023-06-13 17:31:42.586153

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '20b5909a4498'
down_revision = '9a5ae7c9b890'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('tbl_users',
    sa.Column('id_user', sa.Integer(), nullable=False),
    sa.Column('login', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('id_faculty', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id_faculty'], ['spr_faculty.id_faculty'], ),
    sa.PrimaryKeyConstraint('id_user'),
    sa.UniqueConstraint('login'),
    sa.UniqueConstraint('password_hash')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('login')
        batch_op.drop_index('password_hash')

    op.drop_table('users')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('users',
    sa.Column('id_user', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('login', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=False),
    sa.Column('password_hash', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=200), nullable=False),
    sa.Column('id_faculty', mysql.INTEGER(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['id_faculty'], ['spr_faculty.id_faculty'], name='users_ibfk_1'),
    sa.PrimaryKeyConstraint('id_user'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('password_hash', ['password_hash'], unique=False)
        batch_op.create_index('login', ['login'], unique=False)

    op.drop_table('tbl_users')
    # ### end Alembic commands ###
