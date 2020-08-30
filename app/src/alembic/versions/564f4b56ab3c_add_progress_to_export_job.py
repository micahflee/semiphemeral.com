"""add progress to export job

Revision ID: 564f4b56ab3c
Revises: a41bc63bf1dd
Create Date: 2020-08-29 21:44:39.941297

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "564f4b56ab3c"
down_revision = "a41bc63bf1dd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "export_jobs",
        sa.Column("progress", sa.String),
    )


def downgrade():
    op.drop_column("export_jobs", "progress")
