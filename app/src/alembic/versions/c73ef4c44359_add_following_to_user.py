"""add following to user

Revision ID: c73ef4c44359
Revises: 3a1dae769419
Create Date: 2020-02-20 18:42:25.643928

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c73ef4c44359"
down_revision = "3a1dae769419"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("following", sa.Boolean))


def downgrade():
    op.drop_column("users", "following")
