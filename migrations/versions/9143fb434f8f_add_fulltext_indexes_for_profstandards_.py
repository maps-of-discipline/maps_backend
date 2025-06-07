"""Add fulltext indexes for profstandards search

Revision ID: 9143fb434f8f
Revises: 4730cda46a2c
Create Date: 2025-06-07 15:30:08.880227

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9143fb434f8f'
down_revision = '4730cda46a2c'
branch_labels = None
depends_on = None


def upgrade():
    """Commands to apply the migration."""
    print("Creating FULLTEXT indexes for search optimization...")
    # Имя индекса должно быть уникальным в пределах БД
    op.create_index('ix_ps_name_fulltext', 'competencies_prof_standard', ['name'], unique=False, mysql_prefix='FULLTEXT')
    op.create_index('ix_glf_name_fulltext', 'competencies_generalized_labor_function', ['name'], unique=False, mysql_prefix='FULLTEXT')
    op.create_index('ix_lf_name_fulltext', 'competencies_labor_function', ['name'], unique=False, mysql_prefix='FULLTEXT')
    op.create_index('ix_la_desc_fulltext', 'competencies_labor_action', ['description'], unique=False, mysql_prefix='FULLTEXT')
    op.create_index('ix_rs_desc_fulltext', 'competencies_required_skill', ['description'], unique=False, mysql_prefix='FULLTEXT')
    op.create_index('ix_rk_desc_fulltext', 'competencies_required_knowledge', ['description'], unique=False, mysql_prefix='FULLTEXT')
    print("FULLTEXT indexes created successfully.")


def downgrade():
    """Commands to revert the migration."""
    print("Dropping FULLTEXT indexes...")
    op.drop_index('ix_rk_desc_fulltext', table_name='competencies_required_knowledge')
    op.drop_index('ix_rs_desc_fulltext', table_name='competencies_required_skill')
    op.drop_index('ix_la_desc_fulltext', table_name='competencies_labor_action')
    op.drop_index('ix_lf_name_fulltext', table_name='competencies_labor_function')
    op.drop_index('ix_glf_name_fulltext', table_name='competencies_generalized_labor_function')
    op.drop_index('ix_ps_name_fulltext', table_name='competencies_prof_standard')
    print("FULLTEXT indexes dropped.")
