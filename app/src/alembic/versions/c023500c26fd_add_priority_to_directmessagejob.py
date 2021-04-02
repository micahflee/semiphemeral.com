"""add priority to directmessagejob

Revision ID: c023500c26fd
Revises: c2fde0a7a114
Create Date: 2021-04-01 18:01:26.769720

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c023500c26fd"
down_revision = "c2fde0a7a114"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("direct_message_jobs", sa.Column("pririoty", sa.Integer))


def downgrade():
    op.drop_column("direct_message_jobs", "pririoty")
