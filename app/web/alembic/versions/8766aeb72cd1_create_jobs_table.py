"""create jobs table

Revision ID: 8766aeb72cd1
Revises: ee74c488b840
Create Date: 2020-01-23 17:26:28.296160

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8766aeb72cd1"
down_revision = "ee74c488b840"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("job_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=True),
        sa.Column("progress", sa.String, nullable=True),
        sa.Column("added_timestamp", sa.DateTime, nullable=True),
        sa.Column("started_timestamp", sa.DateTime, nullable=True),
        sa.Column("finished_timestamp", sa.DateTime, nullable=True),
    )


def downgrade():
    op.drop_table("jobs")
