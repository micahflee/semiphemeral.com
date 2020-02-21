"""add blocked to users

Revision ID: 975687104fd6
Revises: c73ef4c44359
Create Date: 2020-02-20 20:37:44.671096

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "975687104fd6"
down_revision = "c73ef4c44359"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("blocked", sa.Boolean, default=False))


def downgrade():
    op.drop_column("users", "blocked")
