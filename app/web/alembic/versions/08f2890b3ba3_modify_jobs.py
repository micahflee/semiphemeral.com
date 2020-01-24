"""rename job column

Revision ID: 08f2890b3ba3
Revises: 8766aeb72cd1
Create Date: 2020-01-23 18:36:47.634462

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "08f2890b3ba3"
down_revision = "8766aeb72cd1"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("jobs", "added_timestamp", new_column_name="scheduled_timestamp")
    op.add_column(
        "jobs", sa.Column("depends_on_job_id", sa.Integer, nullable=True),
    )


def downgrade():
    op.alter_column("jobs", "scheduled_timestamp", new_column_name="added_timestamp")
    op.drop_column("jobs", "depends_on_job_id")
