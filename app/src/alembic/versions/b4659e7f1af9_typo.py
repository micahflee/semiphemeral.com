"""typo

Revision ID: b4659e7f1af9
Revises: c023500c26fd
Create Date: 2021-04-01 18:07:50.153053

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b4659e7f1af9"
down_revision = "c023500c26fd"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("direct_message_jobs", "pririoty")
    op.add_column("direct_message_jobs", sa.Column("priority", sa.Integer, default=0))


def downgrade():
    op.drop_column("direct_message_jobs", "priority")
    op.add_column("direct_message_jobs", sa.Column("pririoty", sa.Integer))
