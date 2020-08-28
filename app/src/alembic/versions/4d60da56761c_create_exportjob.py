"""create exportjob

Revision ID: 4d60da56761c
Revises: 4930a8e7628f
Create Date: 2020-08-28 01:17:39.160877

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4d60da56761c"
down_revision = "4930a8e7628f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("status", sa.String),
        sa.Column("scheduled_timestamp", sa.DateTime),
        sa.Column("started_timestamp", sa.DateTime),
        sa.Column("finished_timestamp", sa.DateTime),
    )
    op.create_index("export_jobs_id_idx", "export_jobs", ["id"])
    op.create_index(
        "export_jobs_user_id_status_idx", "export_jobs", ["user_id", "status"]
    )


def downgrade():
    op.drop_table("block_jobs")
    op.drop_index("export_jobs_id_idx")
    op.drop_index("export_jobs_user_id_status_idx")
