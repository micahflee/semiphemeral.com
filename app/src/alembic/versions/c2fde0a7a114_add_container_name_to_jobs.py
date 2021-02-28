"""add container_name to jobs

Revision ID: c2fde0a7a114
Revises: b96f9104c686
Create Date: 2021-02-27 20:46:13.537996

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c2fde0a7a114"
down_revision = "b96f9104c686"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "jobs",
        sa.Column("container_name", sa.String),
    )
    op.create_index("jobs_container_name_idx", "jobs", ["container_name"])


def downgrade():
    op.drop_column("jobs", "container_name")
    op.drop_index("jobs_container_name_idx")
