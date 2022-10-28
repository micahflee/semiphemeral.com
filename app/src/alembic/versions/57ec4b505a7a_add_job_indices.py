"""add_job_indices

Revision ID: 57ec4b505a7a
Revises: fc34ca769348
Create Date: 2022-10-28 14:00:29.562023

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "57ec4b505a7a"
down_revision = "fc34ca769348"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("job_type_idx", "job_details", ["job_type"])
    op.create_index("user_id_idx", "job_details", ["user_id"])
    op.create_index(
        "job_details_scheduled_timestamp_idx", "job_details", ["scheduled_timestamp"]
    )
    op.create_index(
        "job_details_started_timestamp_idx", "job_details", ["started_timestamp"]
    )
    op.create_index(
        "job_details_finished_timestamp_idx", "job_details", ["finished_timestamp"]
    )
    op.create_index("redis_id_idx", "job_details", ["redis_id"])


def downgrade():
    op.drop_index("job_type_idx")
    op.drop_index("user_id_idx")
    op.drop_index("job_details_scheduled_timestamp_idx")
    op.drop_index("job_details_started_timestamp_idx")
    op.drop_index("job_details_finished_timestamp_idx")
    op.drop_index("redis_id_idx")
