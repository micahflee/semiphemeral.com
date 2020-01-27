"""add thread_id to tweet

Revision ID: 417fc065a82f
Revises: b9969908e048
Create Date: 2020-01-26 17:06:12.785339

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "417fc065a82f"
down_revision = "b9969908e048"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tweets", sa.Column("thread_id", sa.Integer, nullable=True),
    )


def downgrade():
    op.drop_column("tweets", "thread_id")
