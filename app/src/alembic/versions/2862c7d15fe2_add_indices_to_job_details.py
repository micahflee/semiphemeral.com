"""Add indices to job_details

Revision ID: 2862c7d15fe2
Revises: 5aeff4fa3dc4
Create Date: 2022-11-08 09:09:02.207450

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2862c7d15fe2"
down_revision = "5aeff4fa3dc4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("job_details_job_type_idx", "job_details", ["job_type"])
    op.create_index("job_details_user_id_idx", "job_details", ["user_id"])
    op.create_index("job_details_status_idx", "job_details", ["status"])
    op.create_index("job_details_redis_id_idx", "job_details", ["redis_id"])


def downgrade():
    op.drop_index("job_details_job_type_idx")
    op.drop_index("job_details_user_id_idx")
    op.drop_index("job_details_status_idx")
    op.drop_index("job_details_redis_id_idx")
