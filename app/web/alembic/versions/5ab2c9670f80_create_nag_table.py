"""create nag table

Revision ID: 5ab2c9670f80
Revises: 4542aa44cf05
Create Date: 2020-01-25 20:31:01.532695

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5ab2c9670f80"
down_revision = "4542aa44cf05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "nags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("timestamp", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("nags")
