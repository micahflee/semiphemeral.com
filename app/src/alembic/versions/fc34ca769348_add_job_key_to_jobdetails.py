"""add job_key to jobdetails

Revision ID: fc34ca769348
Revises: 6bb8ad401c81
Create Date: 2022-05-03 18:17:33.810476

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fc34ca769348"
down_revision = "6bb8ad401c81"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_details", sa.Column("job_key", sa.String))


def downgrade():
    op.drop_column("job_details", "job_key")
