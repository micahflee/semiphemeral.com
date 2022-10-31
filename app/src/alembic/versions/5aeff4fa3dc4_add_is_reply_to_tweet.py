"""add is_reply to tweet

Revision ID: 5aeff4fa3dc4
Revises: 7294f6432f33
Create Date: 2022-10-31 14:09:24.983506

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5aeff4fa3dc4"
down_revision = "7294f6432f33"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tweets", sa.Column("is_reply", sa.Boolean))


def downgrade():
    pass
