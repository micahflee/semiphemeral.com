"""add JobDetails

Revision ID: 6bb8ad401c81
Revises: a7365bc7539c
Create Date: 2022-05-03 12:49:05.492506

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6bb8ad401c81"
down_revision = "a7365bc7539c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_details",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_type", sa.String),
        sa.Column("user_id", sa.Integer, default=0),
        sa.Column("status", sa.String, default="pending"),
        sa.Column("data", sa.String, default="{}"),
        sa.Column("scheduled_timestamp", sa.DateTime),
        sa.Column("started_timestamp", sa.DateTime),
        sa.Column("finished_timestamp", sa.DateTime),
    )
    op.create_index("job_details_id_idx", "job_details", ["id"])


def downgrade():
    op.drop_table("job_details")
    op.drop_index("job_details_id_idx")
