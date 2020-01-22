"""add tips

Revision ID: 7f33d21592f0
Revises: a76b9084018a
Create Date: 2020-01-20 21:44:48.190315

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7f33d21592f0"
down_revision = "a76b9084018a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tips",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
    )


def downgrade():
    op.drop_table("tips")
