"""use strings for twitter ids

Revision ID: caba2a0b2912
Revises: 5a8952165d08
Create Date: 2021-02-01 19:16:08.197839

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "caba2a0b2912"
down_revision = "5a8952165d08"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "twitter_id", type_=sa.String, existing_type=sa.BigInteger)


def downgrade():
    op.alter_column("users", "twitter_id", type_=sa.BigInteger, existing_type=sa.String)
