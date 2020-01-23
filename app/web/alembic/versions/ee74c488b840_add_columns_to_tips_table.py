"""add columns to tips table

Revision ID: ee74c488b840
Revises: 7f33d21592f0
Create Date: 2020-01-22 19:13:46.274775

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ee74c488b840"
down_revision = "7f33d21592f0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tips", sa.Column("charge_id", sa.String, nullable=False))
    op.add_column("tips", sa.Column("receipt_url", sa.String, nullable=False))
    op.add_column("tips", sa.Column("paid", sa.Boolean, default=False, nullable=False))
    op.add_column(
        "tips", sa.Column("refunded", sa.Boolean, default=False, nullable=False)
    )
    op.drop_column("tips", "status")


def downgrade():
    op.drop_column("tips", "charge_id")
    op.drop_column("tips", "receipt_url")
    op.drop_column("tips", "paid")
    op.drop_column("tips", "refunded")
    op.add_column("tips", sa.Column("status", sa.String, nullable=True))
