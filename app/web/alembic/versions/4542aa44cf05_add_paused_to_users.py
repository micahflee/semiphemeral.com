"""add paused to users

Revision ID: 4542aa44cf05
Revises: 08f2890b3ba3
Create Date: 2020-01-24 16:19:42.381571

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4542aa44cf05"
down_revision = "08f2890b3ba3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("paused", sa.Boolean, default=True, nullable=True),
    )
    op.drop_column("job", "depends_on_job_id")


def downgrade():
    op.drop_column("users", "paused")
    op.add_column(
        "jobs", sa.Column("depends_on_job_id", sa.Integer, nullable=True),
    )
